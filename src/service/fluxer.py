import json
from dataclasses import dataclass, replace
from datetime import datetime
from io import BytesIO
from types import EllipsisType
from typing import Literal, Any, Unpack, Sequence

import aiohttp
import fluxer
import fluxer.http as fhttp
from aiohttp import ClientSession

from . import common as c
from .common import Embed, File, RawEmbed, AllowedMention, SendMessageKwargs, MentionPreference, SendMessageArgs
from ..backend.models import Platform
from ..interaction import Interactions, Interaction


class _FluxerRawEmbed(fluxer.Embed):
    def __init__(self, data: dict):
        self.data = data

    def to_dict(self) -> dict[str, Any]:
        return self.data


def from_embed(embed: Embed) -> fluxer.Embed:
    if isinstance(embed, RawEmbed): return _FluxerRawEmbed(embed.data)
    return fluxer.Embed(embed.title, embed.description, footer={"text": embed.footer} if embed.footer else None, thumbnail={"url": embed.thumbnail_url} if embed.thumbnail_url else None)


def from_file(file: File) -> fluxer.File:
    return fluxer.File(BytesIO(file.data), filename=file.filename, description=file.alt, flags=(1 << 3) if file.spoiler else 0)

def as_mp_file(file: File) -> dict:
    d = from_file(file).to_dict()
    d.pop("data")
    return d

FluxerAllowedMentions = fluxer.models.message.AllowedMentions

def to_allowed_mentions(allowed_mentions: AllowedMention | None) -> FluxerAllowedMentions:
    if allowed_mentions is None:
        return FluxerAllowedMentions(True, True, True, True) # type: ignore
    return FluxerAllowedMentions(
        everyone=allowed_mentions.everyone,
        users=allowed_mentions.users, # type: ignore
        roles=allowed_mentions.roles, # type: ignore
        replied_user=allowed_mentions.replied_user
    )

@dataclass
class SendMessageData:
    content: str
    embeds: list[Embed]
    files: list[File]
    allowed_mentions: AllowedMention | None

    def to_kwargs(self) -> SendMessageKwargs:
        return {
            "content": self.content,
            "embeds": self.embeds,
            "files": self.files,
            "allowed_mentions": self.allowed_mentions
        }


def to_send_kwargs(dat: SendMessageData) -> dict:
    return {
        "content": dat.content,
        "embeds": [from_embed(e).to_dict() for e in dat.embeds],
        "files": [from_file(f) for f in dat.files],
        "allowed_mentions": to_allowed_mentions(dat.allowed_mentions)
    }

def edit_kwargs(kwargs: dict) -> dict:
    return {
        "content": kwargs["content"],
        "embeds": kwargs["embeds"]
    }

def collect_args_kwargs(args: Sequence[SendMessageArgs], kwargs: SendMessageKwargs) -> SendMessageData:
    content = args[0] if len(args) > 0 else kwargs.get("content", "")
    assert isinstance(content, str)
    embeds = args[1] if len(args) > 1 else kwargs.get("embeds", [])
    assert isinstance(embeds, list)
    return SendMessageData(content, embeds, kwargs.get("files", []), kwargs.get("allowed_mentions"))


class Attachment(c.Attachment[fluxer.models.Attachment, fluxer.Bot]):
    @property
    def filename(self) -> str:
        return self.raw.filename

    @property
    def url(self) -> str:
        return self.raw.url

    @property
    def alt(self) -> str:
        return self.raw.description or ""

    @property
    def spoiler(self) -> bool:
        return bool(self.raw.flags & (1 << 3))

    async def read(self) -> bytes:
        async with ClientSession() as session:
            async with session.get(self.raw.url) as res:
                return await res.read()


class User(c.User[fluxer.User, fluxer.Bot]):
    @property
    def is_bot(self) -> bool:
        return self.raw.bot

    @property
    def id(self) -> int:
        return self.raw.id

    @property
    def full_tag(self) -> str:
        return f"{self.raw.username}#{self.raw.discriminator}"

    @property
    def display_name(self) -> str:
        return self.raw.display_name

    @property
    def mention(self) -> str:
        return f"<@{self.id}>"

    @property
    def mention_preference(self) -> MentionPreference:
        return MentionPreference(self.raw.mention_flags.value)

    async def get_dm(self) -> c.Channel | None:
        try:
            return Channel(await self.raw.create_dm(), self.bot)
        except fluxer.HTTPException:
            return None


async def _compute_base_permissions(member_id: int, roles: list[c.Role], guild: fluxer.Guild) -> int:
    ALL = 0xFFFF_FFFF_FFFF_FFFF
    if guild.owner_id == member_id:
        return ALL


    all_roles: list[fluxer.models.Role] = await guild.fetch_roles()

    permissions = [r for r in all_roles if r.id == guild.id][0].permissions

    for role in roles:
        permissions |= role.permissions.raw

    if permissions & 0x8 == 0x8:
        return ALL

    return permissions

async def _compute_overwrites(base_permissions: int, bot: fluxer.Bot, member: fluxer.models.GuildMember, channel: fluxer.Channel):
    ALL = 0xFFFF_FFFF_FFFF_FFFF
    # ADMINISTRATOR overrides any potential permission overwrites, so there is nothing to do here.
    if base_permissions & 0x8 == 0x8:
        return ALL

    permissions = base_permissions
    overwrites: list[dict] = (await bot._http.request(fhttp.Route("GET", "/channels/{cid}", cid=str(channel.id))))["permission_overwrites"] or [] # type: ignore
    overwrite_everyone = [r for r in overwrites if int(r["id"]) == channel.guild_id]  # Find (@everyone) role overwrite and apply it.
    if overwrite_everyone:
        permissions &= ~int(overwrite_everyone[0]["deny"])
        permissions |= int(overwrite_everyone[0]["allow"])

    # Apply role specific overwrites.
    allow = 0x0
    deny = 0x0
    for role_id in member.roles:
        overwrite_role = [r for r in overwrites if int(r["id"]) == role_id]
        if overwrite_role:
            allow |= int(overwrite_role[0]["allow"])
            deny |= int(overwrite_role[0]["deny"])

    permissions &= ~deny
    permissions |= allow

    # Apply member specific overwrite if it exists.
    overwrite_member = [r for r in overwrites if int(r["id"]) == member.user.id]
    if overwrite_member:
        permissions &= ~int(overwrite_member[0]["deny"])
        permissions |= int(overwrite_member[0]["allow"])

    return permissions


class Channel(c.Channel[fluxer.Channel, fluxer.Bot]):
    @property
    def id(self) -> int:
        return self.raw.id

    @property
    def parent_id(self) -> int | None:
        return self.raw.parent_id

    @property
    def is_thread(self) -> bool:
        return self.raw.is_thread

    @property
    def dm(self) -> bool:
        return self.raw.type == fluxer.ChannelType.DM

    @property
    def name(self) -> str:
        return self.raw.name or ""

    @property
    def guild(self) -> c.Guild | None:
        if self.raw.guild is None:
            return None

        return Guild(self.raw.guild, self.bot)

    @property
    def guild_id(self) -> int:
        return self.raw.guild_id or 0

    @property
    def mention(self) -> str:
        return f"<#{self.id}>"

    async def send(self, *args: SendMessageArgs, **kwargs: Unpack[SendMessageKwargs]) -> c.Context:
        message = await self.raw.send(**to_send_kwargs(collect_args_kwargs(args, kwargs)))
        return Message(message, self.bot).context

    async def get_message(self, message_id: int) -> c.Message | None:
        try:
            return Message(await self.raw.fetch_message(message_id), self.bot)
        except fluxer.NotFound:
            return None

    async def delete_message(self, message_id: int):
        await self.raw.delete_messages([message_id])

    async def create_webhook(self, name: str) -> c.Webhook:
        return Webhook(await self.bot.create_webhook(str(self.id), name=name), self.bot)

    async def permissions_for(self, member: c.Member) -> c.Permissions:
        base_permissions = await _compute_base_permissions(member.user.id, await member.roles(), await self.bot.fetch_guild(str(self.raw.guild_id)))
        return Permissions(await _compute_overwrites(base_permissions, self.bot, member.raw, self.raw), self.bot)


class Guild(c.Guild[fluxer.Guild, fluxer.Bot]):
    @property
    def id(self) -> int:
        return self.raw.id

    @property
    def name(self) -> str:
        return self.raw.name or ""

    async def get_channel(self, channel_id: int) -> c.Channel | None:
        try:
            return Channel(await self.bot.fetch_channel(str(channel_id)), self.bot)
        except fluxer.NotFound:
            return None

    async def get_roles(self) -> list[c.Role]:
        return [Role(role, self.bot) for role in await self.raw.fetch_roles()]

    async def get_role(self, role_id: int) -> c.Role | None:
        roles = await self.get_roles()
        for role in roles:
            if role.id == role_id:
                return role
        return None

    async def get_member(self, user_id: int) -> c.Member | None:
        try:
            fetched = await self.raw.fetch_member(user_id)
            return Member(fetched, self.bot)
        except fluxer.NotFound:
            return None


class Member(c.Member[fluxer.GuildMember, fluxer.Bot]):
    @property
    def user(self) -> User:
        return User(self.raw.user, self.bot)

    @property
    def nick(self) -> str:
        return self.raw.nick or self.display_name

    @property
    def display_name(self) -> str:
        return self.raw.display_name

    @property
    def mention_preference(self) -> MentionPreference:
        return MentionPreference(self.raw.mention_flags)

    async def roles(self) -> list[c.Role]:
        guild = await self.bot.fetch_guild(str(self.raw.guild_id))
        roles = await guild.fetch_roles()
        return [Role([r for r in roles if r.id == role][0], self.bot) for role in self.raw.roles]


class Role(c.Role[fluxer.Role, fluxer.Bot]):
    @property
    def id(self) -> int:
        return self.raw.id

    @property
    def name(self) -> str:
        return self.raw.name

    @property
    def permissions(self) -> c.Permissions:
        return Permissions(self.raw.permissions, self.bot)

    @property
    def is_everyone(self) -> bool:
        return self.raw.is_default

    @property
    def mention(self) -> str:
        return f"<@&{self.id}>"


class Message(c.Message[fluxer.Message, fluxer.Bot]):
    @property
    def id(self) -> int:
        return self.raw.id

    @property
    def timestamp(self) -> datetime:
        return datetime.fromisoformat(self.raw.timestamp)

    @property
    def content(self) -> str:
        return self.raw.content

    @property
    def embeds(self) -> list[c.Embed]:
        return [Embed(
            e.get("title", ""),
            e.get("description", ""),
            e.get("footer", {}).get("text"),
            e.get("thumbnail", {}).get("url"),
            e.get("type", "rich") == "rich"
        ) for e in self.raw.embeds]

    @property
    def raw_embeds(self) -> list[RawEmbed]:
        return [RawEmbed(e) for e in self.raw.embeds]

    @property
    def is_thread_start(self) -> bool:
        return self.raw.thread is not None

    @property
    def attachments(self) -> list[c.Attachment]:
        return [Attachment(attachment, self.bot) for attachment in self.raw.attachments]

    @property
    def author(self) -> c.User:
        return User(self.raw.author, self.bot)

    async def member(self) -> c.Member | None:
        return await self.context.get_member(self.author.id)

    @property
    def channel(self) -> c.Channel:
        return Channel(self.raw.channel, self.bot) # type: ignore # fuck cache i'll fix this with a new library

    @property
    def channel_id(self) -> int:
        return self.raw.channel_id

    @property
    def guild_id(self) -> int:
        return self.raw.guild_id or 0

    @property
    def guild(self) -> c.Guild | None:
        if self.raw.guild is None:
            return None

        return Guild(self.raw.guild, self.bot)

    @property
    def text_based(self) -> bool:
        return self.raw.type in {0, 19}

    @property
    def mentions_everyone(self) -> bool:
        return self.raw.mentions_everyone

    async def mentions_original(self) -> bool:
        return bool((msg := await self.get_reference()) and msg.author.id in [user.id for user in self.raw.mentions])

    @property
    def context(self) -> c.Context:
        return Context(self, Bot(self.bot, self.bot))

    async def mention(self) -> str:
        channel = Channel(await self.bot.fetch_channel(str(self.channel_id)), self.bot)

        return f"https://web.fluxer.app/channels/{channel.guild_id or '@me'}/{channel.id}/{self.id}"

    @property
    def has_reference(self) -> bool: return self.raw.referenced_message is not None

    async def get_reference(self) -> c.Message | None:
        return Message(self.raw.referenced_message, self.bot) if self.raw.referenced_message else None

    async def delete(self):
        await self.raw.delete()

    async def reply(self, *args: SendMessageArgs, **kwargs: Unpack[SendMessageKwargs]) -> c.Context:
        message = await self.raw.reply(**to_send_kwargs(collect_args_kwargs(args, kwargs)))
        return Message(message, self.bot).context

    async def edit(self, *args: SendMessageArgs, **kwargs: Unpack[SendMessageKwargs]):
        await self.raw.edit(**edit_kwargs(to_send_kwargs(collect_args_kwargs(args, kwargs))))

    async def remove_reaction(self, emoji: str, user: int | None | EllipsisType = ...):
        try:
            if user == ...:
                await self.raw.clear_reaction(emoji)
            else:
                await self.raw.remove_reaction(emoji, user or "@me")
        except fluxer.Forbidden:
            pass

    async def add_reaction(self, emoji: str):
        await self.raw.add_reaction(emoji)


class Webhook(c.Webhook[fluxer.Webhook, fluxer.Bot]):
    @property
    def id(self) -> int:
        return self.raw.id

    @property
    def token(self) -> str:
        return self.raw.token

    @property
    def name(self) -> str:
        return self.raw.name

    async def send(self, username: str = "", avatar_url: str = "", *args: SendMessageArgs, thread_id: int | None = None, initial_payload: dict | None = None, **kwargs: Unpack[SendMessageKwargs]) -> c.Context:
        if not self.raw._http:
            raise RuntimeError("Cannot send with webhook without HTTPClient")

        dat = collect_args_kwargs(args, kwargs)

        files = dat.files

        route = self.raw._http._route(
            "POST",
            "/webhooks/{webhook_id}/{token}",
            webhook_id=self.id,
            token=self.token,
        )
        payload = initial_payload or {}
        payload["content"] = dat.content
        if dat.embeds:
            payload["embeds"] = [from_embed(embed).to_dict() for embed in dat.embeds]
        if username is not None:
            payload["username"] = username
        if avatar_url is not None:
            payload["avatar_url"] = avatar_url
        if dat.allowed_mentions:
            payload["allowed_mentions"] = to_allowed_mentions(dat.allowed_mentions).to_json()
        params = {"wait": "true"}
        if thread_id:
            params["thread_id"] = thread_id
        if files:
            form = aiohttp.FormData()
            payload["attachments"] = [
                ({"id": i} | as_mp_file(file)) for i, file in enumerate(files)
            ]
            form.add_field(
                "payload_json",
                json.dumps(payload),
                content_type="application/json",
            )
            for i, file in enumerate(files):
                form.add_field(
                    f"files[{i}]",
                    file.data,
                    filename=file.filename,
                )
            data = await self.raw._http.request(route, data=form, params=params)
        else:
            data = await self.raw._http.request(
                route,
                json=payload,
                params=params,
            )

        return Message(fluxer.Message.from_data(data, self.raw._http), self.bot).context

    async def edit(self, context: c.Context, *args: SendMessageArgs, thread_id: int | None = None, **kwargs: Unpack[SendMessageKwargs]):
        dat = collect_args_kwargs(args, kwargs)
        content = dat.content
        if context.message.has_reference:
           content = context.content.split("\n")[0] + content

        await self.raw._http.request( # type: ignore
            fhttp.Route("PATCH", "/webhooks/{wid}/{wtk}/messages/{mid}", wid=self.id, wtk=self.token, mid=context.id),
            json={
                "content": content,
                "embeds": [from_embed(embed).to_dict() for embed in dat.embeds]
            },
            params={"thread_id": thread_id} if thread_id else None
        )

    async def reply_internal(self, context: c.Context, username: str = "", avatar_url: str = "", thread_id: int | None = None, **kwargs: Unpack[SendMessageKwargs]) -> c.Context:
        return await self.send(username, avatar_url, thread_id=thread_id, initial_payload={
            "message_reference": {
                "message_id": str(context.id)
            }
        }, **kwargs)


    async def reply(self, context: c.Context, username: str = "", avatar_url: str = "", mention_str: str | Literal[False] | None = None, *args: SendMessageArgs, thread_id: int | None = None, **kwargs: Unpack[SendMessageKwargs]) -> c.Context:
        mention_str = mention_str or context.author.mention
        dat = collect_args_kwargs(args, kwargs)
        content = dat.content
        if mention_str is not False:
            content = f"-# ↩ {mention_str}\n{content}"
        return await self.reply_internal(context, username, avatar_url, thread_id=thread_id, **replace(dat, content=content).to_kwargs())

    async def get_message_data(self, context: c.Context) -> c.Message:
        actual_contents = context.content
        if context.message.has_reference:
            actual_contents = context.content.split("\n", maxsplit=2)[1]

        class M(Message):
            @property
            def content(self) -> str:
                return actual_contents

        return M(context.message.raw, self.bot)


class Bot(c.Bot[fluxer.Bot, fluxer.Bot]):
    @property
    def id(self) -> int:
        return self.raw.user.id # type: ignore
    
    @property
    def user(self) -> c.User:
        return User(self.raw.user, self.bot) # type: ignore

    async def get_user(self, user_id: int) -> c.User | None:
        try:
            return User(await self.bot.fetch_user(str(user_id)), self.bot)
        except fluxer.NotFound:
            return None

    @property
    def guilds(self) -> list[c.Guild]:
        return [Guild(guild, self.bot) for guild in self.raw.guilds]

    async def get_webhook(self, webhook_id: int) -> c.Webhook | None:
        try:
            return Webhook(await self.bot.fetch_webhook(str(webhook_id)), self.bot)
        except fluxer.HTTPException:
            return None

    async def get_channel(self, channel_id: int) -> c.Channel | None:
        try:
            return Channel(await self.bot.fetch_channel(str(channel_id)), self.bot)
        except fluxer.HTTPException:
            return None

    async def get_guild(self, guild_id: int) -> c.Guild | None:
        try:
            return Guild(await self.bot.fetch_guild(str(guild_id)), self.bot)
        except fluxer.HTTPException:
            return None


class ReactionActionEvent(c.ReactionActionEvent[fluxer.models.RawReactionActionEvent, fluxer.Bot]):
    async def context(self) -> c.Context:
        return Message(await self.bot.fetch_message(str(self.raw.channel_id), str(self.raw.message_id)), self.bot).context

    async def user(self) -> User:
        return User(await self.bot.fetch_user(str(self.raw.user_id)), self.bot)

    @property
    def emoji(self) -> str:
        return self.raw.emoji.unicode or self.raw.emoji.name or str(self.raw.emoji.id)

    @property
    def action(self) -> Literal["ADD"] | Literal["REMOVE"]:
        return "ADD" if self.raw.event_type == "REACTION_ADD" else "REMOVE"


class Permissions(c.Permissions[int, fluxer.Bot]):
    @property
    def manage_messages(self) -> bool:
        return self.raw & 0x8 == 0x8 or self.raw & 0x2000 == 0x2000

    @property
    def manage_guild(self) -> bool:
        return self.raw & 0x8 == 0x8 or self.raw & 0x20 == 0x20


class Context(c.Context[Message, Bot]):
    def __init__(self, message: Message, bot: Bot):
        super().__init__(Platform.Fluxer, bot, message)
        self.bot = bot

    async def interact_to_delete(self, event: ReactionActionEvent) -> bool:
        if event.emoji == "❌":
            context = await event.context()
            await context.message.delete()
            Interactions.instance.delete_interaction(context)
            return True
        return False

    async def reply(self, *args: SendMessageArgs, user_id_override: int | None = None, **kwargs: Unpack[SendMessageKwargs]) -> c.Context:
        data = collect_args_kwargs(args, kwargs)
        try:
            ctx = await self.message.reply(*args, **kwargs)
        except fluxer.HTTPException:
            ctx = await self.channel.send(**replace(data, content=(f"<@{self.author.id}>\n" if not self.is_bot else "") + data.content).to_kwargs())

        Interactions.instance.add_interaction(ctx, Interaction(user_id_override or self.author.id, self.interact_to_delete))
        return ctx

    @property
    def author(self) -> c.User:
        return self.message.author

    @property
    def channel(self) -> c.Channel:
        return self.message.channel

    @property
    def guild(self) -> c.Guild | None:
        return self.message.guild

    @property
    def is_bot(self) -> bool:
        return self.author.is_bot

    @property
    def id(self) -> int:
        return self.message.id

    @property
    def content(self) -> str:
        return self.message.content

    async def get_member(self, user_id: int) -> c.Member | None:
        if guild := self.guild:
            return await guild.get_member(user_id)
        channel = await self.get_this_channel()
        if channel.guild_id and (guild := await self.bot.get_guild(channel.guild_id)):
            return await guild.get_member(user_id)
        return None

    async def get_user(self, user_id: int) -> c.User | None:
        return await self.bot.get_user(user_id)

    async def get_channel(self, channel_id: int) -> c.Channel | None:
        return await self.bot.get_channel(channel_id)

    async def get_this_channel(self) -> c.Channel:
        return await self.get_channel(self.message.channel_id) # type: ignore # pretty much a guarantee

    async def get_this_guild(self) -> c.Guild | None:
        return (await self.get_this_channel()).guild

    async def get_wh_message_data(self, context: c.Context) -> c.Message:
        webhook = Webhook(None, self.bot.bot) # type: ignore # actual webhook isn't useful here
        return await webhook.get_message_data(context)
