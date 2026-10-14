import random
import time
from dataclasses import dataclass, field
import json
from enum import Enum, auto
from sqlite3 import Row
from typing import TYPE_CHECKING, Callable, Awaitable

if TYPE_CHECKING:
    from .database.user import UserID


class ID(int):
    def __str__(self):
        return hex(self)


@dataclass(slots=True)
class ProxyTag:
    id: ID
    name: str
    description: str
    owner: UserID
    creation_date: float
    tag: str

    def to_primitive_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "owner": self.owner,
            "creation_date": self.creation_date,
            "tag": self.tag
        }

    @classmethod
    def from_database(cls, row: Row) -> ProxyTag:
        return cls(
            ID(row["id"]),
            row["name"] or "",
            row["description"] or "",
            row["owner"],
            row["creation_date"] or time.time(),
            row["tag"] or "",
        )

    def make_template_object(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "creation_date": self.creation_date,
            "marker": self.tag
        }

    def __repr__(self) -> str:
        return f"ProxyTag({self.id}, ...)"


@dataclass(slots=True)
class Proxy:
    id: ID
    name: str
    description: str
    avatar_url: str
    triggers: list[str]
    owner: UserID
    creation_date: float
    nickname: str
    forms: dict[str, str]
    current_form: str
    pronouns: str

    cached_effective_name: str | None = field(init=False, default=None)


    @classmethod
    def from_full(cls, proxy: FullProxy) -> Proxy:
        return cls(
            proxy.id, proxy.name, proxy.description, proxy.avatar_url, proxy.triggers,
            proxy.owner, proxy.creation_date, proxy.nickname, proxy.forms, proxy.current_form,
            proxy.pronouns
        )


    def effective_name(self, proxy_tags: list[ProxyTag]) -> str:
        if self.cached_effective_name: return self.cached_effective_name

        from .template_utils import Template # i've sinned
        n = self.nickname or self.name

        tagged = [t for t in proxy_tags if t.tag]
        effective_tag = tagged[0] if tagged else None
        if effective_tag:
            n = Template.from_string(
                effective_tag.tag # type: ignore
            ).compute({
                "name": n,
                "proxy": {
                    "id": self.id,
                    "name": self.name,
                    "description": self.description,
                    "triggers": self.triggers,
                    "tags": [t.make_template_object() for t in proxy_tags],
                    "nickname": self.nickname,
                    "form": self.current_form,
                    "pronouns": self.pronouns or ""
                },
                "id": self.id,
                "description": self.description,
                "triggers": self.triggers,
                "tags": [t.make_template_object() for t in proxy_tags],
                "nickname": self.nickname,
                "form": self.current_form,
                "pronouns": self.pronouns or "",
                "tag": effective_tag.make_template_object()
            }, n)

        self.cached_effective_name = n
        return n


    @property
    def effective_avatar(self) -> str:
        return self.forms.get(self.current_form, self.avatar_url)


    @staticmethod
    def random_avatar() -> str:
        return f"https://fluxerstatic.com/avatars/avatars/{random.randint(0, 5)}.png"


    def __repr__(self) -> str:
        return f"Proxy({self.id}, ...)"


@dataclass(slots=True)
class FullProxy(Proxy):
    times_used: int

    def to_primitive_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "avatar_url": self.avatar_url,
            "triggers": "\n".join(self.triggers),
            "owner": self.owner,
            "times_used": self.times_used,
            "creation_date": self.creation_date,
            "nickname": self.nickname,
            "forms": json.dumps(self.forms),
            "current_form": self.current_form,
            "pronouns": self.pronouns
        }

    @classmethod
    def from_database(cls, row: Row) -> FullProxy:
        return cls(
            ID(row["id"]),
            row["name"],
            row["description"],
            row["avatar_url"],
            row["triggers"].split("\n"),
            row["owner"],
            row["creation_date"] or time.time(),
            row["nickname"] or "",
            json.loads(row["proxy_forms"] or "{}"),
            row["current_form"] or "",
            row["pronouns"] or "",
            row["times_used"] or 0,
        )


    def __repr__(self) -> str:
        return f"FullProxy({self.id}, ...)"



class Platform(Enum):
    Fluxer = auto()
    Discord = auto()

    def get(self) -> int:
        if self == Platform.Fluxer:
            return 0
        else:
            return 1

    @classmethod
    def from_(cls, id_: int) -> Platform:
        return [Platform.Fluxer, Platform.Discord][id_]


@dataclass(slots=True, frozen=True)
class MessageDat:
    message_id: int
    channel_id: int
    platform: Platform

    def __hash__(self):
        return hash((self.message_id, self.channel_id, self.platform))


@dataclass(slots=True, frozen=True)
class GuildDat:
    guild_id: int
    platform: Platform

    def __hash__(self):
        return hash((self.guild_id, self.platform))
