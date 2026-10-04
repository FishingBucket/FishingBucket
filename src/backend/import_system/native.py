import json
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, AnyHttpUrl, NonNegativeInt

from . import Exporter
from .common import Importer
from ..database.user import UserID
from ..models import ProxyTag, FullProxy, ID


class NativeTag(BaseModel):
    name: str
    description: str
    creation_date: datetime
    tag: str


class NativeProxy(BaseModel):
    name: str
    description: str
    avatar_url: AnyHttpUrl | Literal[""]
    triggers: list[str]
    times_used: NonNegativeInt
    creation_date: datetime
    nickname: str
    forms: dict[str, AnyHttpUrl | Literal[""]]
    current_form: str
    pronouns: str
    tags: list[str]


class NativeRoot(BaseModel):
    proxies: list[NativeProxy]
    tags: dict[str, NativeTag]


class NativeImporter(Importer):
    def import_data(self, data: bytes, owner: UserID):
        root = NativeRoot(**json.loads(data.decode("utf-8")))

        parsed_tags: dict[str, ID] = {}
        for i, (idx, tag) in enumerate(root.tags.items()):
            t = ProxyTag(
                ID(i),
                tag.name,
                tag.description,
                owner,
                tag.creation_date.timestamp(),
                tag.tag
            )
            self.tags.append(t)
            parsed_tags[idx] = ID(i)

        for i, proxy in enumerate(root.proxies):
            tags = [parsed_tags[idx] for idx in proxy.tags]

            p = FullProxy(
                ID(i),
                proxy.name,
                proxy.description,
                str(proxy.avatar_url),
                proxy.triggers,
                owner,
                proxy.creation_date.timestamp(),
                proxy.nickname,
                {
                    k: str(v)
                    for k, v in proxy.forms.items()
                },
                proxy.current_form,
                proxy.pronouns,
                proxy.times_used,
            )
            self.proxies.append(p)
            if tags:
                self.relationships[p.id] = tags


class NativeExporter(Exporter):
    def export_data(self) -> bytes:
        tags: dict[str, NativeTag] = {}
        proxies: list[NativeProxy] = []

        tag_idx_map: dict[ID, str] = {}

        for i, tag in enumerate(self.tags):
            t = NativeTag(
                name=tag.name,
                description=tag.description,
                creation_date=datetime.fromtimestamp(tag.creation_date, tz=timezone.utc),
                tag=tag.tag
            )
            idx = f"${i}"
            tag_idx_map[tag.id] = idx
            tags[idx] = t

        for proxy in self.proxies:
            p = NativeProxy(
                name=proxy.name,
                description=proxy.description,
                avatar_url=proxy.avatar_url,
                triggers=proxy.triggers,
                times_used=proxy.times_used,
                creation_date=datetime.fromtimestamp(proxy.creation_date, tz=timezone.utc),
                nickname=proxy.nickname,
                forms=proxy.forms,
                current_form=proxy.current_form,
                pronouns=proxy.pronouns,
                tags=[
                    tag_idx_map[tag] for tag in self.relationships.get(proxy.id, [])
                ]
            )
            proxies.append(p)

        root = NativeRoot(
            proxies=proxies,
            tags=tags
        )

        return root.model_dump_json().encode("utf-8")


    @property
    def filename(self) -> str:
        return "fishing_bucket.json"