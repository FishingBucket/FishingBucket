import json
import time
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, AnyHttpUrl, PositiveInt, NonNegativeInt

from .common import Importer
from ..database.user import UserID
from ..models import ProxyTag, FullProxy, ID


class TupperboxTupper(BaseModel):
    id: PositiveInt
    name: str
    brackets: list[str]
    avatar_url: AnyHttpUrl | Literal[""] = None
    posts: NonNegativeInt | None = 0
    show_brackets: bool | None = False
    birthday: datetime | None = None
    description: str | None = None
    tag: str | None = None
    nick: str | None = None
    created_at: datetime | None = None
    group_id: PositiveInt | None = None


class TupperboxGroup(BaseModel):
    id: PositiveInt
    name: str
    description: str | None = None
    tag: str | None = None


class TupperboxRoot(BaseModel):
    tuppers: list[TupperboxTupper]
    groups: list[TupperboxGroup]


class TupperboxImporter(Importer):
    def import_data(self, data: bytes, owner: UserID):
        root = TupperboxRoot(**json.loads(data.decode("utf-8")))
        tag_mapping: dict[int, ProxyTag] = {}
        for i, group in enumerate(root.groups):
            t = ProxyTag(
                ID(i),
                group.name,
                group.description or "",
                owner,
                time.time(),
                ("{} " + group.tag) if group.tag else ""
            )
            tag_mapping[group.id] = t
            self.tags.append(t)

        for i, tupper in enumerate(root.tuppers):
            brackets = []
            for bracket_i in range(0, len(tupper.brackets), 2):
                prefix = self.sanitize_potential_template_fragment(tupper.brackets[bracket_i])
                postfix = self.sanitize_potential_template_fragment(tupper.brackets[bracket_i + 1])
                placeholder = "{}"
                if tupper.show_brackets:
                    placeholder = "{" + f"{prefix!r} + text + {postfix!r}" + "}"

                brackets.append(prefix + placeholder + postfix)

            nick = tupper.nick
            if tupper.tag:
                nick = (nick or tupper.name) + " " + tupper.tag

            p = FullProxy(
                ID(i),
                tupper.name,
                tupper.description or "",
                str(tupper.avatar_url) if tupper.avatar_url else FullProxy.random_avatar(),
                brackets,
                owner,
                tupper.created_at.timestamp() if tupper.created_at else time.time(),
                nick or "",
                {},
                "",
                "",
                tupper.posts or 0,
            )

            if tupper.group_id:
                self.relationships[p.id] = [tag_mapping[tupper.group_id].id]

            self.proxies.append(p)
