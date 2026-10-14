import json
import time
from datetime import datetime

from pydantic import BaseModel, NonNegativeInt, AnyHttpUrl

from . import Importer
from ..database.user import UserID
from ..models import ID, ProxyTag, FullProxy


class Group(BaseModel):
    id: NonNegativeInt
    name: str
    tag: str | None


class Tag(BaseModel):
    prefix: str
    suffix: str
    case_sensitive: bool


class Member(BaseModel):
    id: NonNegativeInt
    name: str
    pronouns: str
    bio: str
    avatar_url: AnyHttpUrl | None
    proxy_tags: list[Tag]
    group_id: NonNegativeInt


class PluRalRoot(BaseModel):
    timestamp: datetime
    groups: list[Group]
    members: list[Member]


class PluRalImporter(Importer):
    def import_data(self, data: bytes, owner: UserID):
        root = PluRalRoot(**json.loads(data.decode("utf-8")))

        tag_id_map: dict[int, ID] = {}
        for i, group in enumerate(root.groups):
            t = ProxyTag(
                ID(i),
                group.name,
                "",
                owner,
                time.time(),
                ("{} " + group.tag) if group.tag else ""
            )
            tag_id_map[group.id] = t.id
            self.tags.append(t)

        for i, member in enumerate(root.members):
            triggers: list[str] = []
            for tag in member.proxy_tags:
                if tag.case_sensitive:
                    triggers.append(tag.prefix + "{}" + tag.suffix)
                else:
                    parts = []
                    if tag.prefix:
                        parts.append(f"text.lower().startswith({tag.prefix!r})")
                    if tag.suffix:
                        parts.append(f"text.lower().endswith({tag.suffix!r})")

                    if tag.suffix:
                        parts.append(f"text.slice({len(tag.prefix)}, -{len(tag.suffix)})")
                    elif tag.prefix:
                        parts.append(f"text.slice({len(tag.prefix)}, text.size())")
                    else:
                        parts.append("text")

                    triggers.append(
                        "{" + " && ".join(parts) + "}"
                    )

            p = FullProxy(
                ID(i),
                member.name,
                member.bio,
                member.avatar_url or FullProxy.random_avatar(),
                triggers,
                owner,
                time.time(),
                "",
                {},
                "",
                member.pronouns,
                0
            )

            self.proxies.append(p)
            self.relationships[p.id] = [tag_id_map[member.group_id]]
