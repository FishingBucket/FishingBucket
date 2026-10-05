from typing import Literal

from pydantic import BaseModel, Field

from ..backend import models as source_models
from ..backend.database.user import UserID


class EphemeralID(BaseModel):
    index: int

    def __hash__(self) -> int:
        return hash(f"new {self.index}")


class ProxyTag(BaseModel):
    id: int | EphemeralID
    name: str
    description: str
    creation_date: float
    tag: str

    @classmethod
    def from_source(cls, source: source_models.ProxyTag) -> ProxyTag:
        return cls(
            id=source.id,
            name=source.name,
            description=source.description,
            creation_date=source.creation_date,
            tag=source.tag
        )

    def to_source(self, id_slot: int, owner: UserID) -> source_models.ProxyTag:
        return source_models.ProxyTag(
            source_models.ID(id_slot),
            self.name,
            self.description,
            owner,
            self.creation_date,
            self.tag
        )


class Proxy(BaseModel):
    id: int | EphemeralID
    name: str
    description: str
    avatar_url: str
    triggers: list[str]
    creation_date: float
    nickname: str
    forms: dict[str, str]
    current_form: str
    pronouns: str
    times_used: int

    @classmethod
    def from_source(cls, source: source_models.FullProxy) -> Proxy:
        return cls(
            id=source.id,
            name=source.name,
            description=source.description,
            avatar_url=source.avatar_url,
            triggers=source.triggers,
            creation_date=source.creation_date,
            nickname=source.nickname,
            forms=source.forms,
            current_form=source.current_form,
            pronouns=source.pronouns,
            times_used=source.times_used,
        )

    def to_source(self, id_slot: int, owner: UserID) -> source_models.FullProxy:
        return source_models.FullProxy(
            source_models.ID(id_slot),
            self.name,
            self.description,
            self.avatar_url,
            self.triggers,
            owner,
            self.creation_date,
            self.nickname,
            self.forms,
            self.current_form,
            self.pronouns,
            self.times_used
        )


class Relationship(BaseModel):
    proxy: int | EphemeralID
    tags: list[int | EphemeralID]




class NewProxyEdit(BaseModel):
    edit_type: Literal["NEW_PROXY"]
    proxy: Proxy

class NewProxyTagEdit(BaseModel):
    edit_type: Literal["NEW_PROXY_TAG"]
    tag: ProxyTag

class DeleteProxyEdit(BaseModel):
    edit_type: Literal["DELETE_PROXY"]
    proxy_id: int

class DeleteProxyTagEdit(BaseModel):
    edit_type: Literal["DELETE_PROXY_TAG"]
    tag_id: int

class EditProxyEdit(BaseModel):
    edit_type: Literal["EDIT_PROXY"]
    value: Proxy

class EditProxyTagEdit(BaseModel):
    edit_type: Literal["EDIT_PROXY_TAG"]
    value: ProxyTag

class SetRelationshipEdit(BaseModel):
    edit_type: Literal["SET_RELATIONSHIP"]
    value: Relationship

class Edit(BaseModel):
    edit: (
            NewProxyEdit |
            NewProxyTagEdit |
            EditProxyEdit |
            EditProxyTagEdit |
            DeleteProxyEdit |
            DeleteProxyTagEdit |
            SetRelationshipEdit
    ) = Field(discriminator="edit_type")

class BatchEdit(BaseModel):
    edits: list[Edit]

class LoginInformation(BaseModel):
    session_id: str
    user: dict
    expires: float
    platform: Literal["discord"] | Literal["fluxer"]

class RefreshLogin(BaseModel):
    expires: float


class UserData(BaseModel):
    proxies: list[Proxy]
    tags: list[ProxyTag]
    relationships: list[Relationship]
