import json
import time

from pydantic import BaseModel

from .common import Importer
from ..database.user import UserID
from ..models import ProxyTag, FullProxy, ID


class UtterProxyTag(BaseModel):
    prefix: str | None = None
    suffix: str | None = None


class UtterMember(BaseModel):
    id: str
    name: str
    displayname: str | None = None
    avatar_url: str | None = None
    proxy_tags: list[UtterProxyTag]
    keep_proxy: bool | None = None
    description: str | None = None
    pronouns: str | None = None


class UtterConfig(BaseModel):
    name_format: str | None = None


class UtterSystem(BaseModel):
    id: str
    name: str | None = None
    tag: str | None = None
    members: list[UtterMember]
    config: UtterConfig | None = None


class UtterImporter(Importer):
    def import_data(self, data: bytes, owner: UserID):
        root = UtterSystem(**json.loads(data.decode("utf-8")))
        default_tag = ProxyTag(
            ID(0),
            root.name or "New System",
            "The imported proxies from Utter!",
            owner,
            time.time(),
            (
                ((root.config or UtterConfig()).name_format or "{name} {tag}")
                .replace("{name}", "{}")
                .replace("{tag}", root.tag or "")
                .replace("{rawname}", "{proxy.name}")
                .replace("{description}", "{proxy.description}")
                .replace("{pronouns}", "{proxy.pronouns}")
            ).strip() or "",
        )
        self.tags.append(default_tag)

        members_map: dict[str, FullProxy] = {}

        for i, member in enumerate(root.members):
            triggers = []
            for tag in member.proxy_tags:
                prefix = self.sanitize_potential_template_fragment(tag.prefix or "")
                postfix = self.sanitize_potential_template_fragment(tag.suffix or "")
                if member.keep_proxy:
                    triggers.append(prefix + "{" + f"{prefix!r} + text + {postfix!r}" + "}" + postfix)
                else:
                    triggers.append(prefix + "{}" + postfix)

            p = FullProxy(
                ID(i),
                member.name,
                member.description or "",
                str(member.avatar_url) if member.avatar_url and member.avatar_url.startswith("http") else FullProxy.random_avatar(),
                triggers,
                owner,
                time.time(),
                member.displayname or "",
                {},
                "",
                member.pronouns or "",
                0
            )

            members_map[member.id] = p
            self.proxies.append(p)

            self.relationships[p.id] = [default_tag.id]
