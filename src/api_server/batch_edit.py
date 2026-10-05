from collections import namedtuple
from typing import Literal, Type, Generator

from .models import Edit, BatchEdit, Proxy, ProxyTag, EphemeralID, DeleteProxyEdit, DeleteProxyTagEdit, NewProxyTagEdit, \
    NewProxyEdit, EditProxyEdit, EditProxyTagEdit, SetRelationshipEdit
from ..backend import models as source
from ..backend.database.database import Database
from ..backend.database.user import UserID
from ..backend.models import ID as ID_


class ID(namedtuple("ID", "id type")):
    id: int
    type: Literal["PROXY"] | Literal["PROXY_TAG"]

def filter_edit_type[T](edits: list[Edit], cls: Type[T]) -> Generator[T, None, None]:
    return (edit.edit for edit in edits if isinstance(edit.edit, cls))

async def handle_batch_edit(batch_edit: BatchEdit, owner: UserID, database: Database) -> None:
    async def ensure_proxy(proxy: int | source.Proxy):
        if isinstance(proxy, int):
            prox = await database.proxies.get(ID_(proxy))
        else:
            prox = proxy
        if prox and prox.owner != owner:
            raise ValueError("Proxy owner does not match the authenticated user.")

    async def ensure_tag(tag: int | source.ProxyTag):
        if isinstance(tag, int):
            tg = await database.tags.get(ID_(tag))
        else:
            tg = tag
        if tg and tg.owner != owner:
            raise ValueError("Tag owner does not match the authenticated user.")

    def ensure_new(proxy_or_tag: Proxy | ProxyTag):
        if isinstance(proxy_or_tag.id, int):
            raise ValueError("Ephemeral ID expected.")

    async def ensure_id_exists(id_: int | EphemeralID, type_: Literal["PROXY"] | Literal["PROXY_TAG"]):
        if id_ is None: return
        elif isinstance(id_, int):
            if type_ == "PROXY":
                await ensure_proxy(id_)
            else:
                await ensure_tag(id_)
        else:
            if len([e_id for e_id in encountered_ephemeral_ids if e_id.type == type_ and e_id.id == id_.index]) == 0:
                raise ValueError("Unknown ID or ephemeral ID.")

    def get_id(id_: int | EphemeralID, type_: Literal["PROXY"] | Literal["PROXY_TAG"]) -> ID_:
        if isinstance(id_, int): return ID_(id_)
        if id_ is None: return id_
        return id_map[ID(id_.index, type_)]

    id_map: dict[ID, ID_] = {}
    encountered_ephemeral_ids: list[ID] = []
    ignored_ids: list[ID] = []

    # VALIDATION

    for delete_proxy_edit in filter_edit_type(batch_edit.edits, DeleteProxyEdit):
        await ensure_proxy(delete_proxy_edit.proxy_id)

    for delete_proxy_tag_edit in filter_edit_type(batch_edit.edits, DeleteProxyTagEdit):
        await ensure_tag(delete_proxy_tag_edit.tag_id)

    for new_proxy_tag_edit in filter_edit_type(batch_edit.edits, NewProxyTagEdit):
        ensure_new(new_proxy_tag_edit.tag)
        assert isinstance(new_proxy_tag_edit.tag.id, EphemeralID)
        encountered_ephemeral_ids.append(ID(new_proxy_tag_edit.tag.id.index, "PROXY_TAG"))

    for new_proxy_edit in filter_edit_type(batch_edit.edits, NewProxyEdit):
        ensure_new(new_proxy_edit.proxy)
        assert isinstance(new_proxy_edit.proxy.id, EphemeralID)
        encountered_ephemeral_ids.append(ID(new_proxy_edit.proxy.id.index, "PROXY"))

    for edit_proxy_edit in filter_edit_type(batch_edit.edits, EditProxyEdit):
        await ensure_id_exists(edit_proxy_edit.value.id, "PROXY")

    for edit_proxy_tag_edit in filter_edit_type(batch_edit.edits, EditProxyTagEdit):
        await ensure_id_exists(edit_proxy_tag_edit.value.id, "PROXY_TAG")

    for set_relationship_edit in filter_edit_type(batch_edit.edits, SetRelationshipEdit):
        await ensure_id_exists(set_relationship_edit.value.proxy, "PROXY")
        for tag in set_relationship_edit.value.tags:
            await ensure_id_exists(tag, "PROXY_TAG")


    # DATABASE

    for delete_proxy_edit in filter_edit_type(batch_edit.edits, DeleteProxyEdit):
        ignored_ids.append(ID(delete_proxy_edit.proxy_id, "PROXY"))
        await database.proxies.delete(ID_(delete_proxy_edit.proxy_id))

    for delete_proxy_tag_edit in filter_edit_type(batch_edit.edits, DeleteProxyTagEdit):
        ignored_ids.append(ID(delete_proxy_tag_edit.tag_id, "PROXY_TAG"))
        await database.tags.delete(ID_(delete_proxy_tag_edit.tag_id))

    for new_proxy_tag_edit in filter_edit_type(batch_edit.edits, NewProxyTagEdit):
        assert isinstance(new_proxy_tag_edit.tag.id, EphemeralID)
        transformed_t = new_proxy_tag_edit.tag.to_source(ID_(0), owner)
        new_id = await database.tags.put(transformed_t)
        id_map[ID(new_proxy_tag_edit.tag.id.index, "PROXY_TAG")] = new_id

    for new_proxy_edit in filter_edit_type(batch_edit.edits, NewProxyEdit):
        assert isinstance(new_proxy_edit.proxy.id, EphemeralID)
        transformed_p = new_proxy_edit.proxy.to_source(ID_(0), owner)
        new_id = await database.proxies.put(transformed_p)
        id_map[ID(new_proxy_edit.proxy.id.index, "PROXY")] = new_id

    for edit_proxy_tag_edit in filter_edit_type(batch_edit.edits, EditProxyTagEdit):
        if isinstance(edit_proxy_tag_edit.value.id, int) and ID(edit_proxy_tag_edit.value.id, "PROXY_TAG") in ignored_ids:
            continue
        tag_id = get_id(edit_proxy_tag_edit.value.id, "PROXY_TAG")
        await database.tags.update(edit_proxy_tag_edit.value.to_source(tag_id, owner))

    for edit_proxy_edit in filter_edit_type(batch_edit.edits, EditProxyEdit):
        if isinstance(edit_proxy_edit.value.id, int) and ID(edit_proxy_edit.value.id, "PROXY") in ignored_ids:
            continue
        proxy_id = get_id(edit_proxy_edit.value.id, "PROXY")
        await database.proxies.update(edit_proxy_edit.value.to_source(proxy_id, owner))

    for set_relationship_edit in filter_edit_type(batch_edit.edits, SetRelationshipEdit):
        proxy_id = get_id(set_relationship_edit.value.proxy, "PROXY")
        tag_ids = [get_id(tag, "PROXY_TAG") for tag in set_relationship_edit.value.tags]
        await database.relationships.set_relationship(proxy_id, tag_ids)
