import json
from abc import abstractmethod, ABC
from datetime import datetime
from enum import Enum
from types import EllipsisType
from typing import Any, Literal, TypedDict, NotRequired, Unpack

from ..backend.models import Platform


class Embed:
    def __init__(self, title: str, description: str, footer: str = "", thumbnail_url: str = "", is_rich: bool = True):
        self.title = title
        self.description = description
        self.footer = footer
        self.thumbnail_url = thumbnail_url
        self.is_rich = is_rich


class RawEmbed(Embed):
    def __init__(self, data: dict):
        super().__init__("", "")
        self.data = data


class File:
    def __init__(self, filename: str, mime_type: str, data: bytes):
        self.filename = filename
        self.mime_type = mime_type
        self.data = data


class AllowedMention:
    def __init__(self, users: list[int], roles: list[int], everyone: bool, replied_user: bool):
        self.users = users
        self.roles = roles
        self.everyone = everyone
        self.replied_user = replied_user


class MentionPreference(Enum):
    NO_PREFERENCE = 0
    PREFER_MENTION = 1
    PREFER_NO_MENTION = 2


class Attachment[Raw, Bot](ABC):
    def __init__(self, raw: Raw, bot: Bot):
        self.raw = raw
        self.bot = bot

    @property
    @abstractmethod
    def filename(self) -> str: pass

    @property
    @abstractmethod
    def url(self) -> str: pass

    @abstractmethod
    async def read(self) -> bytes: pass

    async def read_json(self) -> Any:
        return json.loads((await self.read()).decode("utf-8"))


class SendMessageKwargs(TypedDict):
    content: str
    embeds: NotRequired[list[Embed]]
    files: NotRequired[list[File]]
    allowed_mentions: NotRequired[AllowedMention]


class User[Raw, Bot](ABC):
    def __init__(self, raw: Raw, bot: Bot):
        self.raw = raw
        self.bot = bot

    @property
    @abstractmethod
    def is_bot(self) -> bool: pass

    @property
    @abstractmethod
    def id(self) -> int: pass

    @property
    @abstractmethod
    def full_tag(self) -> str: pass

    @property
    @abstractmethod
    def display_name(self) -> str: pass

    @property
    @abstractmethod
    def mention(self) -> str: pass

    @property
    @abstractmethod
    def mention_preference(self) -> MentionPreference: pass

    @abstractmethod
    async def get_dm(self) -> Channel | None: pass


class Channel[Raw, Bot](ABC):
    def __init__(self, raw: Raw, bot: Bot):
        self.raw = raw
        self.bot = bot

    @property
    @abstractmethod
    def id(self) -> int: pass

    @property
    @abstractmethod
    def parent_id(self) -> int | None: pass

    @property
    @abstractmethod
    def is_thread(self) -> bool: pass

    @property
    @abstractmethod
    def dm(self) -> bool: pass

    @property
    @abstractmethod
    def name(self) -> str: pass

    @property
    @abstractmethod
    def guild(self) -> Guild | None: pass

    @property
    @abstractmethod
    def guild_id(self) -> int: pass

    @property
    @abstractmethod
    def mention(self) -> str: pass

    @abstractmethod
    async def send(self, **kwargs: Unpack[SendMessageKwargs]) -> Context: pass

    @abstractmethod
    async def get_message(self, message_id: int) -> Message | None: pass

    @abstractmethod
    async def delete_message(self, message_id: int): pass

    @abstractmethod
    async def create_webhook(self, name: str) -> Webhook | None: pass

    @abstractmethod
    async def permissions_for(self, member: Member) -> Permissions: pass


class Guild[Raw, Bot](ABC):
    def __init__(self, raw: Raw, bot: Bot):
        self.raw = raw
        self.bot = bot

    @property
    @abstractmethod
    def id(self) -> int: pass

    @property
    @abstractmethod
    def name(self) -> str: pass

    @abstractmethod
    async def get_channel(self, channel_id: int) -> Channel | None: pass

    @abstractmethod
    async def get_roles(self) -> list[Role]: pass

    @abstractmethod
    async def get_role(self, role_id: int) -> Role | None: pass

    @abstractmethod
    async def get_member(self, user_id: int) -> Member | None: pass


class Member[Raw, Bot](ABC):
    def __init__(self, raw: Raw, bot: Bot):
        self.raw = raw
        self.bot = bot

    @property
    @abstractmethod
    def user(self) -> User: pass

    @property
    @abstractmethod
    def nick(self) -> str: pass

    @property
    @abstractmethod
    def display_name(self) -> str: pass

    @property
    @abstractmethod
    def mention_preferences(self) -> MentionPreference: pass

    @abstractmethod
    async def roles(self) -> list[Role]: pass


class Role[Raw, Bot](ABC):
    def __init__(self, raw: Raw, bot: Bot):
        self.raw = raw
        self.bot = bot

    @property
    @abstractmethod
    def id(self) -> int: pass

    @property
    @abstractmethod
    def name(self) -> str: pass

    @property
    @abstractmethod
    def permissions(self) -> Permissions: pass

    @property
    @abstractmethod
    def is_everyone(self) -> bool: pass

    @property
    @abstractmethod
    def mention(self) -> str: pass


class Message[Raw, Bot](ABC):
    def __init__(self, raw: Raw, bot: Bot):
        self.raw = raw
        self.bot = bot

    @property
    @abstractmethod
    def id(self) -> int: pass

    @property
    @abstractmethod
    def timestamp(self) -> datetime: pass

    @property
    @abstractmethod
    def content(self) -> str: pass

    @property
    @abstractmethod
    def embeds(self) -> list[Embed]: pass

    @property
    @abstractmethod
    def raw_embeds(self) -> list[RawEmbed]: pass

    @property
    @abstractmethod
    def thread_start(self) -> bool: pass

    @abstractmethod
    async def try_guess_allowed_mentions(self) -> AllowedMention: pass

    @property
    @abstractmethod
    def attachments(self) -> list[Attachment]: pass

    @property
    @abstractmethod
    def author(self) -> User: pass

    @property
    @abstractmethod
    def member(self) -> Member: pass

    @property
    @abstractmethod
    def channel(self) -> Channel: pass

    @property
    @abstractmethod
    def channel_id(self) -> int: pass

    @property
    @abstractmethod
    def guild_id(self) -> int: pass

    @property
    @abstractmethod
    def guild(self) -> Guild | None: pass

    @property
    @abstractmethod
    def context(self) -> Context: pass

    @abstractmethod
    async def mention(self) -> str: pass

    @property
    @abstractmethod
    def has_reference(self) -> bool: pass

    @abstractmethod
    async def get_reference(self) -> Message | None: pass

    @abstractmethod
    async def delete(self): pass

    @abstractmethod
    async def reply(self, **kwargs: Unpack[SendMessageKwargs]) -> Context: pass

    @abstractmethod
    async def edit(self, **kwargs: Unpack[SendMessageKwargs]): pass

    @abstractmethod
    async def remove_reaction(self, emoji: str, user: int | None | EllipsisType = ...): pass

    @abstractmethod
    async def add_reaction(self, emoji: str): pass


class Webhook[Raw, Bot](ABC):
    def __init__(self, raw: Raw, bot: Bot):
        self.raw = raw
        self.bot = bot

    @property
    @abstractmethod
    def id(self) -> int: pass

    @property
    @abstractmethod
    def token(self) -> str: pass

    @property
    @abstractmethod
    def name(self) -> str: pass

    @abstractmethod
    async def send(self, username: str = "", avatar_url: str = "", **kwargs: Unpack[SendMessageKwargs]) -> Context: pass

    @abstractmethod
    async def edit(self, context: Context, **kwargs: Unpack[SendMessageKwargs]): pass

    @abstractmethod
    async def reply(self, context: Context, username: str = "", avatar_url: str = "", mention_str: str | Literal[False] | None = None, **kwargs: Unpack[SendMessageKwargs]) -> Context: pass

    @abstractmethod
    async def get_message_data(self, context: Context) -> Message: pass


class Bot[Raw, Bot](ABC):
    def __init__(self, raw: Raw, bot: Bot):
        self.raw = raw
        self.bot = bot

    @property
    @abstractmethod
    def id(self) -> int: pass

    @property
    @abstractmethod
    def user(self) -> User: pass

    @property
    @abstractmethod
    def guilds(self) -> list[Guild]: pass

    @abstractmethod
    async def get_user(self, user_id: int) -> User | None: pass

    @abstractmethod
    async def get_webhook(self, webhook_id: int) -> Webhook | None: pass

    @abstractmethod
    async def get_channel(self, channel_id: int) -> Channel | None: pass

    @abstractmethod
    async def get_guild(self, guild_id: int) -> Guild | None: pass


class ReactionActionEvent[Raw, Bot](ABC):
    def __init__(self, raw: Raw, bot: Bot):
        self.raw = raw
        self.bot = bot

    @abstractmethod
    async def context(self) -> Context: pass

    @abstractmethod
    async def user(self) -> User: pass

    @property
    @abstractmethod
    def emoji(self) -> str | int: pass

    @property
    @abstractmethod
    def action(self) -> Literal["ADD"] | Literal["REMOVE"]: pass


class Permissions[Raw, Bot](ABC):
    def __init__(self, raw: Raw, bot: Bot):
        self.raw = raw
        self.bot = bot

    @property
    @abstractmethod
    def manage_messages(self) -> bool: pass

    @property
    @abstractmethod
    def manage_guild(self) -> bool: pass


class Context[MessageT, BotT](ABC):
    def __init__(self, platform: Platform, bot: BotT, message: MessageT):
        self.platform = platform
        self.bot = bot
        self.message = message

    @abstractmethod
    async def reply(self, *, user_id_override: int | None = None, **kwargs: Unpack[SendMessageKwargs]) -> Context: pass

    @property
    @abstractmethod
    def author(self) -> User: pass

    @property
    @abstractmethod
    def channel(self) -> Channel: pass

    @property
    @abstractmethod
    def guild(self) -> Guild | None: pass

    @property
    @abstractmethod
    def is_bot(self) -> bool: pass

    @property
    @abstractmethod
    def id(self) -> int: pass

    @property
    @abstractmethod
    def content(self) -> str: pass

    @abstractmethod
    async def get_member(self, user_id: int) -> Member | None: pass

    @abstractmethod
    async def get_user(self, user_id: int) -> User | None: pass

    @abstractmethod
    async def get_channel(self, channel_id: int) -> Channel | None: pass

    @abstractmethod
    async def get_this_channel(self) -> Channel: pass

    @abstractmethod
    async def get_this_guild(self) -> Guild | None: pass

    @abstractmethod
    async def get_wh_message_data(self, context: Context) -> Message: pass
