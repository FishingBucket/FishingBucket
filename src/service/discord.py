from datetime import datetime
from io import BytesIO
import re
from typing import Literal, TYPE_CHECKING

import discord
if TYPE_CHECKING:
    from discord.raw_models import MessageableChannel

from . import common as c
from .common import Embed, File, RawEmbed
from ..backend.models import Platform
from ..interaction import Interactions, Interaction


def to_embed(embed: Embed) -> discord.Embed:
    if isinstance(embed, RawEmbed): return discord.Embed.from_dict(embed.data)
    return discord.Embed(title=embed.title, description=embed.description, footer=discord.EmbedFooter(embed.footer) if embed.footer else None, thumbnail=embed.thumbnail_url)


def to_file(file: File) -> discord.File:
    return discord.File(BytesIO(file.data), filename=file.filename)


class Attachment(c.Attachment):
    raw: discord.Attachment
    bot: discord.Bot

    @property
    def filename(self) -> str:
        return self.raw.filename

    @property
    def url(self) -> str:
        return self.raw.url

    async def read(self) -> bytes:
        return await self.raw.read()


class User(c.User):
    raw: discord.User
    bot: discord.Bot

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

    async def get_dm(self) -> Channel | None:
        try:
            return Channel(await self.raw.create_dm(), self.bot)
        except discord.HTTPException:
            return None


class Channel(c.Channel):
    raw: MessageableChannel
    bot: discord.Bot

    @property
    def id(self) -> int:
        return self.raw.id

    @property
    def dm(self) -> bool:
        return isinstance(self.raw, discord.DMChannel)

    @property
    def name(self) -> str:
        return self.raw.name

    @property
    def guild(self) -> Guild:
        return Guild(self.raw.guild, self.bot)

    @property
    def guild_id(self) -> int:
        return self.raw.guild.id

    @property
    def mention(self) -> str:
        return f"<#{self.id}>"

    async def send(self, content: str, embeds: list[Embed] = None, files: list[File] = None, **kwargs) -> Context:
        message = await self.raw.send(
            content,
            embeds=[to_embed(e) for e in embeds or []],
            files=[to_file(f) for f in files or []],
            **kwargs
        )
        return Message(message, self.bot).context

    async def get_message(self, message_id: int) -> Message | None:
        try:
            return Message(await self.raw.fetch_message(message_id), self.bot)
        except discord.HTTPException:
            return None

    async def delete_message(self, message_id: int):
        await self.raw.delete_messages([discord.Object(message_id)])

    async def create_webhook(self, name: str) -> Webhook:
        webhook = await self.raw.create_webhook(name=name)
        return Webhook(webhook, self.bot)

    async def permissions_for(self, member: Member) -> Permissions:
        return Permissions((self.raw.permissions_for(member.raw)).value, self.bot)


class Guild(c.Guild):
    raw: discord.Guild
    bot: discord.Bot

    @property
    def id(self) -> int:
        return self.raw.id

    @property
    def name(self) -> str:
        return self.raw.name

    async def get_channel(self, channel_id: int) -> Channel | None:
        try:
            return Channel(await self.raw.fetch_channel(channel_id), self.bot)
        except discord.HTTPException:
            return None

    async def get_roles(self) -> list[Role]:
        return [Role(role, self.bot) for role in await self.raw.fetch_roles()]

    async def get_role(self, role_id: int) -> Role | None:
        try:
            return Role(await self.raw.fetch_role(role_id), self.bot)
        except discord.HTTPException:
            return None

    async def get_member(self, user_id: int) -> Member | None:
        try:
            return Member(await self.raw.fetch_member(user_id), self.bot)
        except discord.HTTPException:
            return None


class Member(c.Member):
    raw: discord.Member
    bot: discord.Bot

    @property
    def user(self) -> User:
        return User(self.raw._user, self.bot)

    @property
    def nick(self) -> str:
        return self.raw.nick

    @property
    def display_name(self) -> str:
        return self.raw.display_name

    async def roles(self) -> list[Role]:
        return [Role(role, self.bot) for role in self.raw.roles]


class Role(c.Role):
    raw: discord.Role
    bot: discord.Bot

    @property
    def id(self) -> int:
        return self.raw.id

    @property
    def name(self) -> str:
        return self.raw.name

    @property
    def permissions(self) -> Permissions:
        return Permissions(self.raw.permissions.value, self.bot)

    @property
    def is_everyone(self) -> bool:
        return self.raw.is_default()

    @property
    def mention(self) -> str:
        return f"<@&{self.id}>"


class Message(c.Message):
    raw: discord.Message
    bot: discord.Bot

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
    def embeds(self) -> list[Embed]:
        return [Embed(
            embed.title,
            embed.description,
            embed.footer.text if embed.footer else None,
            embed.thumbnail.url if embed.thumbnail else None,
            embed.type == "rich"
        ) for embed in self.raw.embeds]

    @property
    def raw_embeds(self) -> list[RawEmbed]:
        return [RawEmbed(embed.to_dict()) for embed in self.raw.embeds]

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
        return self.raw.channel.id

    @property
    def guild_id(self) -> int:
        return self.raw.guild.id

    @property
    def guild(self) -> Guild:
        return Guild(self.raw.guild, self.bot)

    @property
    def context(self) -> Context:
        return Context(self, self.bot)

    async def mention(self) -> str:
        return f"https://discord.com/channels/{self.guild.id if not self.channel.dm else '@me'}/{self.channel.id}/{self.id}"

    @property
    def has_reference(self) -> bool: return self.raw.reference is not None

    async def get_reference(self) -> Message | None:
        d = None
        if self.raw.reference:
            if self.raw.reference.cached_message:
                d = self.raw.reference.cached_message
            else:
                try:
                    d = await (await self.bot.fetch_channel(self.raw.reference.channel_id)).fetch_message(self.raw.reference.message_id)
                except discord.HTTPException: pass

        return Message(d, self.bot) if d else None

    async def delete(self):
        await self.raw.delete()

    async def reply(self, content: str, embeds: list[Embed] = None, files: list[File] = None, **kwargs) -> Context:
        message = await self.raw.reply(
            content,
            embeds=[to_embed(e) for e in embeds or []],
            files=[to_file(f) for f in files or []],
            **kwargs
        )
        return Message(message, self.bot).context

    async def edit(self, content: str, embeds: list[Embed] = None, **kwargs):
        await self.raw.edit(
            content=content,
            embeds=[to_embed(e) for e in embeds or []],
            **kwargs
        )

    async def remove_reaction(self, emoji: str | int, user: int | None | type(...) = ...):
        try:
            if user == ...:
                await self.raw.clear_reaction(emoji)
            else:
                await self.raw.remove_reaction(emoji, discord.Object(user) if user else self.bot.user)
        except discord.Forbidden:
            pass

    async def add_reaction(self, emoji: str | int):
        await self.raw.add_reaction(emoji)


class Webhook(c.Webhook):
    raw: discord.Webhook
    bot: discord.Bot

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
        message = await self.raw.send(
            content,
            username=username,
            avatar_url=avatar_url,
            allowed_mentions=discord.AllowedMentions.all() if mention else None,
            embeds=[to_embed(e) for e in embeds or []],
            files=[to_file(f) for f in files or []],
            wait=True,
            **kwargs
        )
        return Message(message, self.bot).context

    async def transform_embeds(self, embeds: list[Embed], reference: Context) -> list[Embed]:
        trunc = reference.content[:min(250, len(reference.content))]
        if len(trunc) != len(reference.content):
            trunc += "..."

        return [Embed(
            "Reply",
            f"[Replying to]({await reference.message.mention()}) {reference.message.author.display_name}:\n{'\n'.join(('> ' + line) for line in trunc.split('\n'))}"
        )] + embeds

    REPLY_DESCRIPTION_REGEX = re.compile(r"\[Replying to]\(https://discord\.com/channels/(?:\d+?|@me)/\d+?/(\d+?)\) .+?:")


    async def reply(self, context: Context, content: str, username: str = None, avatar_url: str = None, mention: bool = False, embeds: list[Embed] = None, files: list[File] = None, mention_str: str | Literal[False] = None) -> Context:
        mention_str = mention_str or context.author.mention
        return await self.send(
            f"-# ↩ {mention_str}\n{content}" if mention_str is not False else content,
            username, avatar_url, mention, await self.transform_embeds(embeds, context), files
        )

    async def edit(self, context: Context, content: str, embeds: list[Embed] = None, **kwargs):
        data = (await self.get_message_data(context)).context
        if data.message.has_reference:
            content = context.content.split("\n")[0] + "\n" + content
        await self.raw.edit_message(
            context.id,
            content=content,
            embeds=[
                       to_embed(embed) for embed in context.message.embeds if embed.title == "Reply"
                   ] + ([to_embed(e) for e in embeds] or []),
            **kwargs
        )

    async def get_message_data(self, context: Context) -> Message:
        actual_contents = context.content
        actual_embeds = [embed for embed in context.message.embeds if embed.title != "Reply"]
        referenced_message_embeds = [embed for embed in context.message.embeds if embed.title == "Reply"]
        referenced_message = None
        if referenced_message_embeds:
            referenced_message_embed = referenced_message_embeds[0]
            match = Webhook.REPLY_DESCRIPTION_REGEX.match(referenced_message_embed.description.split("\n")[0])
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

            async def get_reference(self) -> Message | None:
                return referenced_message

            @property
            def has_reference(self) -> bool:
                return referenced_message is not None

        return M(context.message.raw, self.bot)


class Bot(c.Bot):
    raw: discord.Bot
    bot: discord.Bot

    @property
    def id(self) -> int:
        return self.raw.user.id

    @property
    def user(self) -> User:
        return User(self.raw.user, self.bot)

    async def get_user(self, user_id: int) -> User | None:
        try:
            return User(await self.bot.fetch_user(user_id), self.bot)
        except discord.HTTPException:
            return None

    @property
    def guilds(self) -> list[Guild]:
        return [Guild(guild, self.bot) for guild in self.raw.guilds]

    async def get_webhook(self, webhook_id: int) -> Webhook | None:
        try:
            return Webhook(await self.raw.fetch_webhook(webhook_id), self.bot)
        except discord.HTTPException:
            return None


class ReactionActionEvent(c.ReactionActionEvent):
    raw: discord.RawReactionActionEvent
    bot: discord.Bot

    async def context(self) -> Context:
        return Message(await (await self.bot.fetch_channel(self.raw.channel_id)).fetch_message(self.raw.message_id), self.bot).context

    async def user(self) -> User:
        return User(await self.bot.fetch_user(self.raw.user_id), self.bot)

    @property
    def emoji(self) -> str | int:
        return self.raw.emoji.name or self.raw.emoji.id

    @property
    def action(self) -> Literal["ADD"] | Literal["REMOVE"]:
        return "ADD" if self.raw.event_type == "REACTION_ADD" else "REMOVE"


class Permissions(c.Permissions):
    raw: int
    bot: discord.Bot

    @property
    def manage_messages(self) -> bool:
        return self.raw & 0x8 == 0x8 or self.raw & 0x2000 == 0x2000

    @property
    def manage_guild(self) -> bool:
        return self.raw & 0x8 == 0x8 or self.raw & 0x20 == 0x20


class Context(c.Context):
    def __init__(self, message: Message, bot: discord.Bot):
        super().__init__(Platform.Discord, bot, message)
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
        except discord.HTTPException:
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
            return User(await self.bot.fetch_user(user_id), self.bot)
        except discord.HTTPException:
            return None

    async def get_channel(self, channel_id: int) -> Channel | None:
        try:
            return Channel(await self.bot.fetch_channel(channel_id), self.bot)
        except discord.HTTPException:
            return None

    async def get_this_channel(self) -> Channel:
        return await self.get_channel(self.message.channel_id)


    @property
    def get_bot(self) -> Bot:
        return Bot(self.bot, self.bot)

    async def get_wh_message_data(self, context: Context) -> Message:
        webhook = Webhook(None, self.bot)
        return await webhook.get_message_data(context)