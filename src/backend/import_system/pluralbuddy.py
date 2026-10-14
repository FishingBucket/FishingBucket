import json
import time
from datetime import datetime
from enum import IntFlag

from pydantic import BaseModel, AnyHttpUrl, NonNegativeInt

from .common import Importer
from ..database.user import UserID
from ..models import ProxyTag, FullProxy, ID


class SystemInformation(BaseModel):
    associatedUserId: int
    alterIds: list[int]
    tagIds: list[str]
    createdAt: datetime
    systemName: str


class PluralBuddyProxyTag(BaseModel):
    prefix: str
    suffix: str


class AlterFlags(IntFlag):
    KEEP_PROXY = 1 << 0


class Alter(BaseModel):
    alterId: int
    username: str
    displayName: str | None
    description: str | None
    pronouns: str | None
    created: datetime
    avatarUrl: AnyHttpUrl | None
    messageCount: NonNegativeInt
    proxyTags: list[PluralBuddyProxyTag]
    tagIds: list[str]
    flags: AlterFlags


class PluralBuddyTag(BaseModel):
    tagId: str
    tagFriendlyName: str
    associatedAlters: list[str]


class PluralBuddyRoot(BaseModel):
    system: SystemInformation
    alters: list[Alter]
    tags: list[PluralBuddyTag]


class PluralBuddyImporter(Importer):
    def import_data(self, data: bytes, owner: UserID):
        root = PluralBuddyRoot(**json.loads(data.decode("utf-8")))

        default_tag = ProxyTag(
            ID(0),
            root.system.systemName,
            "Imported from PluralBuddy!",
            owner,
            root.system.createdAt.timestamp(),
            ""
        )

        self.tags.append(default_tag)

        tag_id_map: dict[str, ID] = {}
        for i, tag in enumerate(root.tags):
            t = ProxyTag(
                ID(i + 1),
                tag.tagFriendlyName,
                "",
                owner,
                time.time(),
                ""
            )
            tag_id_map[tag.tagId] = t.id
            self.tags.append(t)

        for i, alter in enumerate(root.alters):
            triggers: list[str] = []

            for proxy_tag in alter.proxyTags:
                if alter.flags & AlterFlags.KEEP_PROXY:
                    parts: list[str] = []
                    if proxy_tag.prefix:
                        parts.append(repr(proxy_tag.prefix))
                    parts.append("text")
                    if proxy_tag.suffix:
                        parts.append(repr(proxy_tag.suffix))
                    triggers.append(proxy_tag.prefix + "{" + " + ".join(parts) + "}" + proxy_tag.suffix)
                else:
                    triggers.append(proxy_tag.prefix + "{}" + proxy_tag.suffix)

            p = FullProxy(
                ID(i),
                alter.username,
                alter.description or "",
                alter.avatarUrl or FullProxy.random_avatar(),
                triggers,
                owner,
                alter.created.timestamp(),
                alter.displayName or "",
                {},
                "",
                alter.pronouns or "",
                alter.messageCount or 0,
            )
            self.proxies.append(p)
            tags = [tag_id_map[t] for t in alter.tagIds] + [default_tag.id]
            self.relationships[p.id] = tags

