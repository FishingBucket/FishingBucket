from datetime import datetime
from io import BytesIO
import re
from types import EllipsisType
from typing import Literal, Unpack, cast

import discord

from . import common as c
from .common import Embed, File, RawEmbed, AllowedMention, SendMessageKwargs, MentionPreference
from ..backend.models import Platform
from ..interaction import Interactions, Interaction


def to_embed(embed: Embed) -> discord.Embed:
    if isinstance(embed, RawEmbed): return discord.Embed.from_dict(embed.data)
    return discord.Embed(title=embed.title, description=embed.description, footer=discord.EmbedFooter(embed.footer) if embed.footer else None, thumbnail=embed.thumbnail_url)


def to_file(file: File) -> discord.File:
    return discord.File(BytesIO(file.data), filename=file.filename)


class _Snowflake(discord.abc.Snowflake):
    def __init__(self, id_: int):
        self.id = id_


def to_allowed_mentions(allowed_mentions: AllowedMention | None) -> discord.AllowedMentions:
    if allowed_mentions is None:
        return discord.AllowedMentions.all()
    return discord.AllowedMentions(
        everyone=allowed_mentions.everyone,
        users=[_Snowflake(user) for user in allowed_mentions.users],
        roles=[_Snowflake(role) for role in allowed_mentions.roles],
        replied_user=allowed_mentions.replied_user
    )


def to_send_kwargs(kwargs: SendMessageKwargs) -> dict:
    return {
        "content": kwargs["content"],
        "embeds": [to_embed(e) for e in kwargs.get("embeds") or []],
        "files": [to_file(f) for f in kwargs.get("files") or []],
        "allowed_mentions": to_allowed_mentions(kwargs.get("allowed_mentions"))
    }


class Attachment(c.Attachment[discord.Attachment, discord.Bot]):
    @property
    def filename(self) -> str:
        return self.raw.filename

    @property
    def url(self) -> str:
        return self.raw.url

    async def read(self) -> bytes:
        return await self.raw.read()


class User(c.User[discord.User, discord.Bot]):
    @property
    def is_bot(self) -> bool:
        return self.raw.bot

    @property
    def id(self) -> int:
        return self.raw.id

    @property
    def full_tag(self) -> str:
        return self.raw.name if self.raw.discriminator == "0" else (self.raw.name + "#" + self.raw.discriminator)

    @property
    def display_name(self) -> str:
        return self.raw.display_name

    @property
    def mention(self) -> str:
        return f"<@{self.id}>"

    @property
    def mention_preference(self) -> MentionPreference:
        return MentionPreference.NO_PREFERENCE

    async def get_dm(self) -> c.Channel | None:
        try:
            return Channel(await self.raw.create_dm(), self.bot)
        except discord.HTTPException:
            return None

type DiscordChannels = (
        discord.TextChannel |
        discord.VoiceChannel |
        discord.StageChannel |
        discord.ForumChannel |
        discord.CategoryChannel |
        discord.DMChannel |
        discord.GroupChannel |
        discord.Thread
)

class Channel(c.Channel[DiscordChannels, discord.Bot]):
    @property
    def id(self) -> int:
        return self.raw.id

    @property
    def parent_id(self) -> int | None:
        if isinstance(self.raw, discord.Thread):
            return self.raw.parent_id
        if isinstance(self.raw, (discord.DMChannel, discord.GroupChannel)):
            return None
        return self.raw.category_id

    @property
    def is_thread(self) -> bool:
        return isinstance(self.raw, discord.Thread)

    @property
    def dm(self) -> bool:
        return isinstance(self.raw, discord.DMChannel)

    @property
    def name(self) -> str:
        if isinstance(self.raw, discord.abc.GuildChannel):
            return self.raw.name
        return ""

    @property
    def guild(self) -> c.Guild | None:
        if isinstance(self.raw, discord.abc.GuildChannel):
            return Guild(self.raw.guild, self.bot)
        return None

    @property
    def guild_id(self) -> int:
        if isinstance(self.raw, discord.abc.GuildChannel):
            return self.raw.guild.id
        return 0

    @property
    def mention(self) -> str:
        return f"<#{self.id}>"

    async def send(self, **kwargs: Unpack[SendMessageKwargs]) -> c.Context:
        assert not isinstance(self.raw, (discord.ForumChannel, discord.CategoryChannel))
        message = await self.raw.send(**to_send_kwargs(kwargs))
        return Message(message, self.bot).context

    async def get_message(self, message_id: int) -> c.Message | None:
        try:
            if isinstance(self.raw, (discord.ForumChannel, discord.CategoryChannel)):
                return None

            return Message(await self.raw.fetch_message(message_id), self.bot)
        except discord.HTTPException:
            return None

    async def delete_message(self, message_id: int):
        if not isinstance(self.raw, (discord.CategoryChannel, discord.DMChannel, discord.GroupChannel)):
            await self.raw.delete_messages([_Snowflake(message_id)])

    async def create_webhook(self, name: str) -> c.Webhook | None:
        if isinstance(self.raw, discord.Thread):
            parent = self.raw.parent
            if parent is None:
                return None

            webhook = await parent.create_webhook(name=name)
        else:
            if isinstance(self.raw, (discord.CategoryChannel, discord.DMChannel, discord.GroupChannel)):
                return None

            webhook = await self.raw.create_webhook(name=name)
        return Webhook(webhook, self.bot)

    async def permissions_for(self, member: Member) -> c.Permissions:  # type: ignore # variance rule not applicable
        return Permissions((self.raw.permissions_for(member.raw)).value, self.bot)


class Guild(c.Guild[discord.Guild, discord.Bot]):
    @property
    def id(self) -> int:
        return self.raw.id

    @property
    def name(self) -> str:
        return self.raw.name

    async def get_channel(self, channel_id: int) -> c.Channel | None:
        try:
            channel = await self.raw.fetch_channel(channel_id)
            return Channel(channel, self.bot)
        except discord.HTTPException:
            return None

    async def get_roles(self) -> list[c.Role]:
        return [Role(role, self.bot) for role in await self.raw.fetch_roles()]

    async def get_role(self, role_id: int) -> c.Role | None:
        try:
            return Role(await self.raw.fetch_role(role_id), self.bot)
        except discord.HTTPException:
            return None

    async def get_member(self, user_id: int) -> c.Member | None:
        try:
            return Member(await self.raw.fetch_member(user_id), self.bot)
        except discord.HTTPException:
            return None


class Member(c.Member[discord.Member, discord.Bot]):
    @property
    def user(self) -> c.User:
        return User(self.raw._user, self.bot)

    @property
    def nick(self) -> str:
        return self.raw.nick or self.raw.name

    @property
    def display_name(self) -> str:
        return self.raw.display_name

    @property
    def mention_preferences(self) -> MentionPreference:
        return MentionPreference.NO_PREFERENCE

    async def roles(self) -> list[c.Role]:
        return [Role(role, self.bot) for role in self.raw.roles]


class Role(c.Role[discord.Role, discord.Bot]):
    @property
    def id(self) -> int:
        return self.raw.id

    @property
    def name(self) -> str:
        return self.raw.name

    @property
    def permissions(self) -> c.Permissions:
        return Permissions(self.raw.permissions.value, self.bot)

    @property
    def is_everyone(self) -> bool:
        return self.raw.is_default()

    @property
    def mention(self) -> str:
        return f"<@&{self.id}>"


class Message(c.Message[discord.Message, discord.Bot]):
    @property
    def id(self) -> int:
        return self.raw.id

    @property
    def timestamp(self) -> datetime:
        return self.raw.created_at

    @property
    def content(self) -> str:
        return self.raw.content

    @property
    def embeds(self) -> list[c.Embed]:
        return [Embed(
            str(embed.title or ""),
            str(embed.description or ""),
            str(footer.text) if (footer := embed.footer) is not None else "",
            str(thumbnail.url) if (thumbnail := embed.thumbnail) is not None else "",
            embed.type == "rich"
        ) for embed in self.raw.embeds]

    @property
    def raw_embeds(self) -> list[c.RawEmbed]:
        return [RawEmbed(embed.to_dict()) for embed in self.raw.embeds] # type: ignore # .to_dict() returns a dict

    @property
    def attachments(self) -> list[c.Attachment]:
        return [Attachment(attachment, self.bot) for attachment in self.raw.attachments]

    @property
    def author(self) -> c.User:
        return User(self.raw.author if isinstance(self.raw.author, discord.User) else self.raw.author._user, self.bot)

    @property
    def member(self) -> c.Member:
        assert isinstance(self.raw.author, discord.Member) # fingers crossed
        return Member(self.raw.author, self.bot)

    @property
    def channel(self) -> c.Channel:
        return Channel(self.raw.channel, self.bot) # type: ignore # can't be assed to make sure all channels are ok

    @property
    def channel_id(self) -> int:
        return self.raw.channel.id

    @property
    def guild_id(self) -> int:
        if isinstance(self.raw, discord.abc.GuildChannel):
            return self.raw.guild.id
        return 0

    @property
    def guild(self) -> c.Guild | None:
        if self.raw.guild is None:
            return None

        return Guild(self.raw.guild, self.bot)

    @property
    def thread_start(self) -> bool:
        return self.raw.type == discord.MessageType.thread_starter_message

    async def try_guess_allowed_mentions(self) -> AllowedMention:
        mentions = self.raw.mentions
        users = [mention.id for mention in mentions]
        mention_roles = self.raw.role_mentions
        roles = [role.id for role in mention_roles]
        ref = await self.get_reference()
        return AllowedMention(users, roles, self.raw.mention_everyone, ref.author.id in users if ref else False)

    @property
    def context(self) -> c.Context:
        return Context(self, Bot(self.bot, self.bot))

    async def mention(self) -> str:
        return f"https://discord.com/channels/{self.guild_id or '@me'}/{self.channel_id}/{self.id}"

    @property
    def has_reference(self) -> bool: return self.raw.reference is not None

    async def get_reference(self) -> c.Message | None:
        d = None
        if self.raw.reference:
            if self.raw.reference.cached_message:
                d = self.raw.reference.cached_message
            else:
                try:
                    channel = await self.bot.fetch_channel(self.raw.reference.channel_id)
                    if channel and isinstance(channel, discord.abc.Messageable) and self.raw.reference.message_id:
                        d = await channel.fetch_message(self.raw.reference.message_id)
                except discord.HTTPException:
                    pass

        return Message(d, self.bot) if d else None

    async def delete(self):
        await self.raw.delete()

    async def reply(self, **kwargs: Unpack[SendMessageKwargs]) -> c.Context:
        message = await self.raw.reply(**to_send_kwargs(kwargs))
        return Message(message, self.bot).context

    async def edit(self, **kwargs: Unpack[SendMessageKwargs]):
        await self.raw.edit(**to_send_kwargs(kwargs))

    async def remove_reaction(self, emoji: str, user: int | None | EllipsisType = ...):
        try:
            if user == ...:
                await self.raw.clear_reaction(emoji)
            else:
                assert self.bot.user is not None
                await self.raw.remove_reaction(emoji, _Snowflake(user) if user else self.bot.user)
        except discord.Forbidden:
            pass

    async def add_reaction(self, emoji: str):
        await self.raw.add_reaction(emoji)


class Webhook(c.Webhook[discord.Webhook, discord.Bot]):
    @property
    def id(self) -> int:
        return self.raw.id

    @property
    def token(self) -> str:
        return self.raw.token or ""

    @property
    def name(self) -> str:
        return cast(str, self.raw.name or "")

    async def send(self, username: str = "", avatar_url: str = "", **kwargs: Unpack[SendMessageKwargs]) -> c.Context:
        message = await self.raw.send(
            username=username,
            avatar_url=avatar_url,
            **to_send_kwargs(kwargs)
        )
        return Message(message, self.bot).context

    async def transform_embeds(self, embeds: list[c.Embed], reference: c.Context) -> list[c.Embed]:
        trunc = reference.content[:min(250, len(reference.content))]
        if len(trunc) != len(reference.content):
            trunc += "..."

        return [Embed(
            "Reply",
            f"[Replying to]({await reference.message.mention()}) {reference.message.author.display_name}:\n{'\n'.join(('> ' + line) for line in trunc.split('\n'))}"
        )] + embeds

    REPLY_DESCRIPTION_REGEX = re.compile(r"\[Replying to]\(https://discord\.com/channels/(?:\d+?|@me)/\d+?/(\d+?)\) .+?:")


    async def reply(self, context: c.Context, username: str = "", avatar_url: str = "", mention_str: str | Literal[False] | None = None, **kwargs: Unpack[SendMessageKwargs]) -> c.Context:
        mention_str = mention_str or context.author.mention
        send_kwargs = to_send_kwargs(kwargs)
        return await self.send(
            content=f"-# ↩ {mention_str}\n{kwargs["content"]}" if mention_str is not False else kwargs["content"],
            username=username,
            avatar_url=avatar_url,
            **(send_kwargs | {"embeds": await self.transform_embeds(send_kwargs["embeds"], context)})
        )

    async def edit(self, context: c.Context, **kwargs: Unpack[SendMessageKwargs]):
        data = (await self.get_message_data(context)).context
        content = kwargs["content"]
        if data.message.has_reference:
            content = context.content.split("\n")[0] + "\n" + content
        await self.raw.edit_message(
            context.id,
            **(to_send_kwargs(kwargs) | {"content": content})
        )

    async def get_message_data(self, context: c.Context) -> c.Message:
        actual_contents = context.content
        actual_embeds = [embed for embed in context.message.embeds if embed.title != "Reply"]
        referenced_message_embeds = [embed for embed in context.message.embeds if embed.title == "Reply"]
        referenced_message = None
        if referenced_message_embeds:
            referenced_message_embed = referenced_message_embeds[0]
            match = Webhook.REPLY_DESCRIPTION_REGEX.match(referenced_message_embed.description.split("\n")[0])
            if match:
                message_id = match.group(1)
                message_id = int(message_id)
                referenced_message = await context.channel.get_message(message_id)
                actual_contents = context.content.split("\n", maxsplit=2)[1]

        class M(Message):
            @property
            def content(self) -> str:
                return actual_contents

            @property
            def embeds(self) -> list[Embed]:
                return actual_embeds

            async def get_reference(self) -> c.Message | None:
                return referenced_message

            @property
            def has_reference(self) -> bool:
                return referenced_message is not None

        return M(context.message.raw, self.bot)


class Bot(c.Bot[discord.Bot, discord.Bot]):
    @property
    def id(self) -> int:
        if user := self.raw.user:
            return user.id
        return 0

    @property
    def user(self) -> c.User:
        assert self.raw.user is not None
        return User(self.raw.user, self.bot) # type: ignore # ClientUser is User enough, right?

    async def get_user(self, user_id: int) -> c.User | None:
        try:
            return User(await self.bot.fetch_user(user_id), self.bot)
        except discord.HTTPException:
            return None

    @property
    def guilds(self) -> list[c.Guild]:
        return [Guild(guild, self.bot) for guild in self.raw.guilds]

    async def get_webhook(self, webhook_id: int) -> c.Webhook | None:
        try:
            return Webhook(await self.raw.fetch_webhook(webhook_id), self.bot)
        except discord.HTTPException:
            return None

    async def get_channel(self, channel_id: int) -> c.Channel | None:
        try:
            return Channel(await self.raw.fetch_channel(channel_id), self.bot) # type: ignore
        except discord.HTTPException:
            return None

    async def get_guild(self, guild_id: int) -> c.Guild | None:
        try:
            return Guild(await self.raw.fetch_guild(guild_id), self.bot)
        except discord.HTTPException:
            return None


class ReactionActionEvent(c.ReactionActionEvent[discord.RawReactionActionEvent, discord.Bot]):
    async def context(self) -> Context:
        return Message(await (await self.bot.fetch_channel(self.raw.channel_id)).fetch_message(self.raw.message_id), self.bot).context # type: ignore # I gie up

    async def user(self) -> User:
        return User(await self.bot.fetch_user(self.raw.user_id), self.bot)

    @property
    def emoji(self) -> str:
        return self.raw.emoji.name or str(self.raw.emoji.id)

    @property
    def action(self) -> Literal["ADD"] | Literal["REMOVE"]:
        return "ADD" if self.raw.event_type == "REACTION_ADD" else "REMOVE"


class Permissions(c.Permissions[int, discord.Bot]):
    @property
    def manage_messages(self) -> bool:
        return self.raw & 0x8 == 0x8 or self.raw & 0x2000 == 0x2000

    @property
    def manage_guild(self) -> bool:
        return self.raw & 0x8 == 0x8 or self.raw & 0x20 == 0x20


class Context(c.Context[Message, Bot]):
    def __init__(self, message: Message, bot: Bot):
        super().__init__(Platform.Discord, bot, message)
        self.bot = bot

    async def interact_to_delete(self, event: ReactionActionEvent) -> bool:
        if event.emoji == "❌":
            context = await event.context()
            await context.message.delete()
            Interactions.instance.delete_interaction(context)
            return True
        return False

    async def reply(self, *, user_id_override: int | None = None, **kwargs: Unpack[SendMessageKwargs]) -> c.Context:
        try:
            ctx = await self.message.reply(**kwargs)
        except discord.HTTPException:
            ctx = await self.channel.send(**(kwargs | {
                "content": (f"<@{self.author.id}>\n" if not self.is_bot else "") + kwargs["content"]
            }))

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