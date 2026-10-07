import json
from datetime import datetime
from io import BytesIO
from typing import Literal, Any

import aiohttp
import fluxer
import fluxer.http as fhttp
from aiohttp import ClientSession

from . import common as c
from .common import Embed, File, RawEmbed
from ..backend.models import Platform
from ..interaction import Interactions, Interaction


class _FluxerRawEmbed(fluxer.Embed):
    def __init__(self, data: dict):
        self.data = data

    def to_dict(self) -> dict[str, Any]:
        return self.data


def from_embed(embed: Embed) -> fluxer.Embed:
    if isinstance(embed, RawEmbed): return _FluxerRawEmbed(embed.data)
    return fluxer.Embed(embed.title, embed.description, footer={"text": embed.footer}, thumbnail={"url": embed.thumbnail_url})


def from_file(file: File) -> fluxer.File:
    return fluxer.File(BytesIO(file.data), filename=file.filename)


class Attachment(c.Attachment):
    raw: fluxer.models.Attachment

    @property
    def filename(self) -> str:
        return self.raw.filename

    @property
    def url(self) -> str:
        return self.raw.url

    async def read(self) -> bytes:
        async with ClientSession() as session:
            async with session.get(self.raw.proxy_url) as res:
                return await res.read()


class User(c.User):
    raw: fluxer.User
    bot: fluxer.Bot

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

    async def get_dm(self) -> Channel | None:
        try:
            return Channel(await self.raw.create_dm(), self.bot)
        except fluxer.HTTPException:
            return None


async def _compute_base_permissions(member_id: int, roles: list[Role], guild: fluxer.Guild) -> int:
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
    overwrites: list[dict] = (await bot._http.request(fhttp.Route("GET", "/channels/{cid}", cid=str(channel.id))))["permission_overwrites"] or []
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


class Channel(c.Channel):
    raw: fluxer.Channel
    bot: fluxer.Bot

    @property
    def id(self) -> int:
        return self.raw.id

    @property
    def dm(self) -> bool:
        return self.raw.type == fluxer.ChannelType.DM

    @property
    def name(self) -> str:
        return self.raw.name

    @property
    def guild(self) -> Guild:
        return Guild(self.raw.guild, self.bot)

    @property
    def guild_id(self) -> int:
        return self.raw.guild_id

    @property
    def mention(self) -> str:
        return f"<#{self.id}>"

    async def send(self, content: str, embeds: list[Embed] = None, files: list[File] = None, **kwargs) -> Context:
        message = await self.raw.send(
            content,
            embeds=[from_embed(e) for e in embeds or []],
            files=[from_file(f) for f in files or []],
            **kwargs
        )
        return Message(message, self.bot).context

    async def get_message(self, message_id: int) -> Message | None:
        try:
            return Message(await self.raw.fetch_message(message_id), self.bot)
        except fluxer.NotFound:
            return None

    async def delete_message(self, message_id: int):
        await self.raw.delete_messages([message_id])

    async def create_webhook(self, name: str) -> Webhook:
        return Webhook(await self.bot.create_webhook(str(self.id), name=name), self.bot)

    async def permissions_for(self, member: Member) -> Permissions:
        base_permissions = await _compute_base_permissions(member.user.id, await member.roles(), await self.bot.fetch_guild(str(self.raw.guild_id)))
        return Permissions(await _compute_overwrites(base_permissions, self.bot, member.raw, self.raw), self.bot)


class Guild(c.Guild):
    raw: fluxer.Guild
    bot: fluxer.Bot

    @property
    def id(self) -> int:
        return self.raw.id

    @property
    def name(self) -> str:
        return self.raw.name

    async def get_channel(self, channel_id: int) -> Channel | None:
        try:
            return await self.bot.fetch_channel(str(channel_id))
        except fluxer.NotFound:
            return None

    async def get_roles(self) -> list[Role]:
        return [Role(role, self.bot) for role in await self.raw.fetch_roles()]

    async def get_role(self, role_id: int) -> Role | None:
        roles = await self.get_roles()
        for role in roles:
            if role.id == role_id:
                return role
        return None

    async def get_member(self, user_id: int) -> Member | None:
        try:
            return Member(await self.raw.fetch_member(user_id), self.bot)
        except fluxer.NotFound:
            return None


class Member(c.Member):
    raw: fluxer.GuildMember
    bot: fluxer.Bot

    @property
    def user(self) -> User:
        return User(self.raw.user, self.bot)

    @property
    def nick(self) -> str:
        return self.raw.nick

    @property
    def display_name(self) -> str:
        return self.raw.display_name

    async def roles(self) -> list[Role]:
        guild = await self.bot.fetch_guild(str(self.raw.guild_id))
        roles = await guild.fetch_roles()
        return [Role([r for r in roles if r.id == role][0], self.bot) for role in self.raw.roles]


class Role(c.Role):
    raw: fluxer.Role
    bot: fluxer.Bot

    @property
    def id(self) -> int:
        return self.raw.id

    @property
    def name(self) -> str:
        return self.raw.name

    @property
    def permissions(self) -> Permissions:
        return Permissions(self.raw.permissions, self.bot)

    @property
    def is_everyone(self) -> bool:
        return self.raw.is_default

    @property
    def mention(self) -> str:
        return f"<@&{self.id}>"


class Message(c.Message):
    raw: fluxer.Message
    bot: fluxer.Bot

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
    def embeds(self) -> list[Embed]:
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
    def attachments(self) -> list[Attachment]:
        return [Attachment(attachment, self.bot) for attachment in self.raw.attachments]

    @property
    def author(self) -> User:
        return User(self.raw.author, self.bot)

    @property
    def channel(self) -> Channel:
        return Channel(self.raw.channel, self.bot)

    @property
    def channel_id(self) -> int:
        return self.raw.channel_id

    @property
    def guild_id(self) -> int:
        return self.raw.guild_id

    @property
    def guild(self) -> Guild:
        return Guild(self.raw.guild, self.bot)

    @property
    def context(self) -> Context:
        return Context(self, self.bot)

    async def mention(self) -> str:
        channel = Channel(await self.bot.fetch_channel(str(self.channel_id)), self.bot)

        return f"https://web.fluxer.app/channels/{channel.guild_id if not channel.dm else '@me'}/{channel.id}/{self.id}"

    @property
    def has_reference(self) -> bool: return self.raw.referenced_message is not None

    async def get_reference(self) -> Message | None:
        return Message(self.raw.referenced_message, self.bot) if self.raw.referenced_message else None

    async def delete(self):
        await self.raw.delete()

    async def reply(self, content: str, embeds: list[Embed] = None, files: list[File] = None, **kwargs) -> Context:
        message = await self.raw.reply(
            content,
            embeds=[from_embed(e) for e in embeds or []],
            files=[from_file(f) for f in files or []],
            **kwargs
        )
        return Message(message, self.bot).context

    async def edit(self, content: str, embeds: list[Embed] = None, **kwargs):
        await self.raw.edit(
            content,
            embeds=[from_embed(e).to_dict() for e in embeds or []],
            **kwargs
        )

    async def remove_reaction(self, emoji: str | int, user: int | None | type(...) = ...):
        try:
            if user == ...:
                await self.raw.clear_reaction(emoji)
            else:
                await self.raw.remove_reaction(emoji, user or "@me")
        except fluxer.Forbidden:
            pass

    async def add_reaction(self, emoji: str | int):
        await self.raw.add_reaction(emoji)


class Webhook(c.Webhook):
    raw: fluxer.Webhook
    bot: fluxer.Bot

    @property
    def id(self) -> int:
        return self.raw.id

    @property
    def token(self) -> str:
        return self.raw.token

    @property
    def name(self) -> str:
        return self.raw.name

    async def send(self, content: str, username: str = None, avatar_url: str = None, mention: bool = False, embeds: list[Embed] = None, files: list[File] = None, **kwargs) -> Context:
        if not self.raw._http:
            raise RuntimeError("Cannot send with webhook without HTTPClient")

        files = files or []

        route = self.raw._http._route(
            "POST",
            "/webhooks/{webhook_id}/{token}",
            webhook_id=self.id,
            token=self.token,
        )
        payload = {}
        if content is not None:
            payload["content"] = content
        if embeds is not None:
            payload["embeds"] = [from_embed(embed).to_dict() for embed in embeds]
        if username is not None:
            payload["username"] = username
        if avatar_url is not None:
            payload["avatar_url"] = avatar_url
        if mention:
            payload["allowed_mentions"] = {
                "parse": ["users"]
            }
        params = {"wait": "true"}
        if files:
            form = aiohttp.FormData()
            payload["attachments"] = [
                {"id": i, "filename": file.filename} for i, file in enumerate(files)
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

    async def edit(self, context: Context, content: str, embeds: list[Embed] = None, **kwargs):
        if context.message.has_reference:
           content = context.content.split("\n")[0] + content

        await self.raw._http.request(
            fhttp.Route("PATCH", "/webhooks/{wid}/{wtk}/messages/{mid}", wid=self.id, wtk=self.token, mid=context.id),
            json={
                "content": content,
                "embeds": [from_embed(embed).to_dict() for embed in embeds or []]
            }
        )

    async def reply_internal(self, context: Context, content: str, username: str = None, avatar_url: str = None, mention: bool = False, embeds: list[Embed] = None, files: list[File] = None) -> Context:
        if not self.raw._http:
            raise RuntimeError("Cannot send with webhook without HTTPClient")

        files = files or []

        route = self.raw._http._route(
            "POST",
            "/webhooks/{webhook_id}/{token}",
            webhook_id=self.id,
            token=self.token,
        )
        payload = {}
        if content is not None:
            payload["content"] = content
        if embeds is not None:
            payload["embeds"] = [from_embed(embed).to_dict() for embed in embeds]
        if username is not None:
            payload["username"] = username
        if avatar_url is not None:
            payload["avatar_url"] = avatar_url
        if mention:
            payload["allowed_mentions"] = {
                "parse": ["users"]
            }
        payload["message_reference"] = {
            "message_id": str(context.id)
        }
        params = {"wait": "true"}
        if files:
            form = aiohttp.FormData()
            payload["attachments"] = [
                {"id": i, "filename": file.filename} for i, file in enumerate(files)
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

    async def reply(self, context: Context, content: str, username: str = None, avatar_url: str = None, mention: bool = False, embeds: list[Embed] = None, files: list[File] = None, mention_str: str | Literal[False] = None) -> Context:
        mention_str = mention_str or context.author.mention
        return await self.reply_internal(context, f"-# ↩ {mention_str}\n{content}" if mention_str is not False else content, username, avatar_url, mention, embeds, files)

    async def get_message_data(self, context: Context) -> Message:
        actual_contents = context.content
        if context.message.has_reference:
            actual_contents = context.content.split("\n", maxsplit=2)[1]

        class M(Message):
            @property
            def content(self) -> str:
                return actual_contents

        return M(context.message.raw, self.bot)


class Bot(c.Bot):
    raw: fluxer.Bot
    bot: fluxer.Bot
    
    @property
    def id(self) -> int:
        return self.raw.user.id
    
    @property
    def user(self) -> User:
        return User(self.raw.user, self.bot)

    async def get_user(self, user_id: int) -> User | None:
        try:
            return User(await self.bot.fetch_user(str(user_id)), self.bot)
        except fluxer.NotFound:
            return None

    @property
    def guilds(self) -> list[Guild]:
        return [Guild(guild, self.bot) for guild in self.raw.guilds]

    async def get_webhook(self, webhook_id: int) -> Webhook | None:
        try:
            return Webhook(await self.bot.fetch_webhook(str(webhook_id)), self.bot)
        except fluxer.HTTPException:
            return None


class ReactionActionEvent(c.ReactionActionEvent):
    raw: fluxer.models.RawReactionActionEvent
    bot: fluxer.Bot

    async def context(self) -> Context:
        return Message(await self.bot.fetch_message(str(self.raw.channel_id), str(self.raw.message_id)), self.bot).context

    async def user(self) -> User:
        return User(await self.bot.fetch_user(str(self.raw.user_id)), self.bot)

    @property
    def emoji(self) -> str | int:
        return self.raw.emoji.name or self.raw.emoji.id

    @property
    def action(self) -> Literal["ADD"] | Literal["REMOVE"]:
        return "ADD" if self.raw.event_type == "REACTION_ADD" else "REMOVE"


class Permissions(c.Permissions):
    raw: int
    bot: fluxer.Bot

    @property
    def manage_messages(self) -> bool:
        return self.raw & 0x8 == 0x8 or self.raw & 0x2000 == 0x2000

    @property
    def manage_guild(self) -> bool:
        return self.raw & 0x8 == 0x8 or self.raw & 0x20 == 0x20


class Context(c.Context):
    def __init__(self, message: Message, bot: fluxer.Bot):
        super().__init__(Platform.Fluxer, bot, message)
        self.bot = bot

    async def interact_to_delete(self, event: ReactionActionEvent) -> bool:
        if event.emoji == "❌":
            context = await event.context()
            await context.message.delete()
            Interactions.instance.delete_interaction(context)
            return True
        return False

    async def reply(self, content: str, embeds: list[Embed] = None, files: list[File] = None, **kwargs) -> Context:
        try:
            ctx = await self.message.reply(content, embeds, files)
        except fluxer.NotFound:
            ctx = await self.channel.send(
                (f"<@{self.author.id}>\n" if not self.is_bot else "") + content,
                embeds, files)

        Interactions.instance.add_interaction(ctx, Interaction(kwargs.get("user_id_override", self.author.id), self.interact_to_delete))
        return ctx

    @property
    def author(self) -> User:
        return self.message.author

    @property
    def channel(self) -> Channel:
        return self.message.channel

    @property
    def guild(self) -> Guild:
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

    async def get_member(self, user_id: int) -> Member | None:
        return await self.guild.get_member(user_id)

    async def get_user(self, user_id: int) -> User | None:
        try:
            return User(await self.bot.fetch_user(str(user_id)), self.bot)
        except fluxer.NotFound:
            return None

    async def get_channel(self, channel_id: int) -> Channel | None:
        try:
            return Channel(await self.bot.fetch_channel(str(channel_id)), self.bot)
        except fluxer.NotFound:
            return None

    async def get_this_channel(self) -> Channel:
        return await self.get_channel(self.message.channel_id)

    @property
    def get_bot(self) -> Bot:
        return Bot(self.bot, self.bot)

    async def get_wh_message_data(self, context: Context) -> Message:
        webhook = Webhook(None, self.bot)
        return await webhook.get_message_data(context)
