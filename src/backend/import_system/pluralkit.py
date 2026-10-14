import json
import time
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, AnyHttpUrl, NonNegativeInt

from .common import Importer
from ..database.user import UserID
from ..models import ProxyTag, FullProxy, ID


class SystemGroup(BaseModel):
    id: str
    name: str
    display_name: str | None = None
    description: str | None = None
    created: datetime | None = None
    members: list[str]


class PKProxyTag(BaseModel):
    prefix: str | None = None
    suffix: str | None = None


class SystemMember(BaseModel):
    id: str
    name: str
    display_name: str | None = None
    avatar_url: AnyHttpUrl | Literal[""] | None = None
    description: str | None = None
    created: datetime | None = None
    keep_proxy: bool | None = None
    message_count: NonNegativeInt | None = None
    proxy_tags: list[PKProxyTag]
    pronouns: str | None = None


class SystemConfig(BaseModel):
    case_sensitive_proxy_tags: bool | None = None
    name_format: str | None = None


class PluralKitRoot(BaseModel):
    version: Literal[2]
    name: str | None = None
    description: str | None = None
    tag: str | None = None
    config: SystemConfig
    members: list[SystemMember]
    groups: list[SystemGroup]


class PluralKitImporter(Importer):
    def import_data(self, data: bytes, owner: UserID):
        root = PluralKitRoot(**json.loads(data.decode("utf-8")))
        default_tag = ProxyTag(
            ID(0),
            root.name or "PluralKit System",
            root.description or "This group is used to house the imported proxies from PluralKit!",
            owner,
            time.time(),
            (
                (root.config.name_format or "{name} {tag}")
                .replace("{name}", "{}")
                .replace("{tag}", root.tag)
            ) if root.tag else ""
        )
        self.tags.append(default_tag)

        members_map: dict[str, FullProxy] = {}

        for i, member in enumerate(root.members):
            triggers = []
            for tag in member.proxy_tags:
                prefix = self.sanitize_potential_template_fragment(tag.prefix or "")
                postfix = self.sanitize_potential_template_fragment(tag.suffix or "")
                if not root.config.case_sensitive_proxy_tags:
                    parts = []
                    if prefix:
                        parts.append(f"text.lower().startswith({prefix!r})")
                    if postfix:
                        parts.append(f"text.lower().endswith({postfix!r})")

                    if member.keep_proxy:
                        parts.append("text")
                    else:
                        if postfix:
                            parts.append(f"text.slice({len(prefix)}, -{len(postfix)})")
                        elif prefix:
                            parts.append(f"text.slice({len(prefix)}, text.size())")
                        else:
                            parts.append("text")

                    triggers.append(
                        "{" + " && ".join(parts) + "}"
                    )
                else:
                    if member.keep_proxy:
                        triggers.append(prefix + "{" + f"{prefix!r} + text + {postfix!r}" + "}" + postfix)
                    else:
                        triggers.append(prefix + "{}" + postfix)

            p = FullProxy(
                ID(i),
                member.name,
                member.description or "",
                str(member.avatar_url) if member.avatar_url else FullProxy.random_avatar(),
                triggers,
                owner,
                member.created.timestamp() if member.created else time.time(),
                member.display_name or "",
                {},
                "",
                member.pronouns or "",
                member.message_count or 0,
            )

            members_map[member.id] = p
            self.proxies.append(p)
            self.relationships[p.id] = [default_tag.id]

        for i, group in enumerate(root.groups):
            t = ProxyTag(
                ID(i + 1), # this is to account for the default tag
                group.display_name or group.name,
                group.description or "",
                owner,
                group.created.timestamp() if group.created else time.time(),
                ""
            )

            for member_id in (group.members or []):
                if member_id in members_map:
                    self.relationships[members_map[member_id].id].insert(0, t.id)

            self.tags.append(t)
