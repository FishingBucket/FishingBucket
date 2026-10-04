from collections import namedtuple
from typing import Literal, Type, Generator

from .models import BatchEdit, ModifiedItemResponse, ModifiedItem, ProxyTag, Proxy, Edit, DeleteProxyEdit, \
    DeleteProxyTagEdit, ItemDeleteResponse, NewProxyEdit, NewProxyTagEdit, EphemeralID, EditProxyTagField, \
    EditProxyField, ItemNewResponse, ItemUpdateResponse
from ..backend import models as source

class ID(namedtuple("ID", "id type")):
    id: int
    type: Literal["PROXY"] | Literal["PROXY_TAG"]

def filter_edit_type[T](edits: list[Edit], cls: Type[T]) -> Generator[T, None, None]:
    return (edit.edit for edit in edits if isinstance(edit.edit, cls))

async def handle_batch_edit(batch_edit: BatchEdit, owner: int, database: Database) -> ModifiedItemResponse | None:
    async def ensure_proxy(proxy: int | source.Proxy):
        if isinstance(proxy, int):
            prox = await database.get_proxy(proxy)
        else:
            prox = proxy
        if prox and prox.owner != owner:
            raise ValueError("Proxy owner does not match the authenticated user.")

    async def ensure_tag(tag: int | source.ProxyTag):
        if isinstance(tag, int):
            tg = await database.get_tag(tag)
        else:
            tg = tag
        if tg and tg.owner != owner:
            raise ValueError("Tag owner does not match the authenticated user.")

    def ensure_new(proxy_or_tag: Proxy | ProxyTag):
        if isinstance(proxy_or_tag.id, int):
            raise ValueError("Ephemeral ID expected.")

    async def ensure_id_exists(id_: int | EphemeralID | None, type_: Literal["PROXY"] | Literal["PROXY_TAG"]):
        if id_ is None: return
        elif isinstance(id_, int):
            if type_ == "PROXY":
                await ensure_proxy(id_)
            else:
                await ensure_tag(id_)
        else:
            if len([e_id for e_id in encountered_ephemeral_ids if e_id.type == type_ and e_id.id == id_.index]) == 0:
                raise ValueError("Unknown ID or ephemeral ID.")

    def get_id(id_: int | EphemeralID | None, type_: Literal["PROXY"] | Literal["PROXY_TAG"]) -> int | None:
        if isinstance(id_, int): return id_
        if id_ is None: return id_
        return id_map[ID(id_.index, type_)]

    id_map: dict[ID, int] = {}
    encountered_ephemeral_ids: list[ID] = []
    modified: list[ModifiedItem[Proxy | ProxyTag]] = []
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
        for tag in new_proxy_edit.proxy.tags:
            await ensure_id_exists(tag, "PROXY_TAG")
        encountered_ephemeral_ids.append(ID(new_proxy_edit.proxy.id.index, "PROXY"))

    for edit_proxy_edit in filter_edit_type(batch_edit.edits, EditProxyField):
        await ensure_id_exists(edit_proxy_edit.id, "PROXY")
        if edit_proxy_edit.edit_type == "tags":
            for tag in edit_proxy_edit.kv.value:
                await ensure_id_exists(tag, "PROXY_TAG")

    for edit_proxy_tag_edit in filter_edit_type(batch_edit.edits, EditProxyTagField):
        await ensure_id_exists(edit_proxy_tag_edit.id, "PROXY_TAG")


    # DATABASE

    for delete_proxy_edit in filter_edit_type(batch_edit.edits, DeleteProxyEdit):
        ignored_ids.append(ID(delete_proxy_edit.proxy_id, "PROXY"))
        modified.append(ModifiedItem(
            type="PROXY",
            item=ItemDeleteResponse(
                method="DELETE", id=delete_proxy_edit.proxy_id
            )
        ))
        await database.delete_proxy(delete_proxy_edit.proxy_id)

    for delete_proxy_tag_edit in filter_edit_type(batch_edit.edits, DeleteProxyTagEdit):
        ignored_ids.append(ID(delete_proxy_tag_edit.tag_id, "PROXY_TAG"))
        modified.append(ModifiedItem(
            type="PROXY_TAG",
            item=ItemDeleteResponse(
                method="DELETE", id=delete_proxy_tag_edit.tag_id
            )
        ))
        await database.delete_tag(delete_proxy_tag_edit.tag_id)

    for new_proxy_tag_edit in filter_edit_type(batch_edit.edits, NewProxyTagEdit):
        assert isinstance(new_proxy_tag_edit.tag.id, EphemeralID)
        transformed_t = new_proxy_tag_edit.tag.to_source(None, owner)
        t = await database.put_tag(transformed_t)
        assert isinstance(t.id, int)
        id_map[ID(new_proxy_tag_edit.tag.id.index, "PROXY_TAG")] = t.id
        modified.append(ModifiedItem(
            type="PROXY_TAG",
            item=ItemNewResponse(
                method="NEW", id=t.id, matching_ephemeral_id=new_proxy_tag_edit.tag.id.index, data=ProxyTag.from_source(t)
            )
        ))

    for new_proxy_edit in filter_edit_type(batch_edit.edits, NewProxyEdit):
        assert isinstance(new_proxy_edit.proxy.id, EphemeralID)

        tag_resolved_ids = [get_id(tag, "PROXY_TAG") for tag in new_proxy_edit.proxy.tags]
        resolved = [t for t in tag_resolved_ids if t]

        transformed_p = new_proxy_edit.proxy.to_source(None, await database.get_tags(resolved), owner)
        p = await database.put_proxy(transformed_p)
        assert isinstance(p.id, int)
        id_map[ID(new_proxy_edit.proxy.id.index, "PROXY")] = p.id
        modified.append(ModifiedItem(
            type="PROXY",
            item=ItemNewResponse(
                method="NEW", id=p.id, matching_ephemeral_id=new_proxy_edit.proxy.id.index, data=Proxy.from_source(p)
            )
        ))

    edited_proxy_tags: list[int] = []
    edited_proxies: list[int] = []

    for edit_proxy_tag_edit in filter_edit_type(batch_edit.edits, EditProxyTagField):
        if isinstance(edit_proxy_tag_edit.id, int) and ID(edit_proxy_tag_edit.id, "PROXY_TAG") in ignored_ids:
            continue
        tag_id = get_id(edit_proxy_tag_edit.id, "PROXY_TAG")
        assert isinstance(tag_id, int)
        edited_proxy_tags.append(tag_id)
        field_t = edit_proxy_tag_edit.kv.field
        value_t = edit_proxy_tag_edit.kv.value
        if field_t == "name":
            await database.update_tag_name(tag_id, value_t)
        elif field_t == "description":
            await database.update_tag_description(tag_id, value_t)
        elif field_t == "tag":
            await database.update_tag_tag(tag_id, value_t)

    for edit_proxy_edit in filter_edit_type(batch_edit.edits, EditProxyField):
        if isinstance(edit_proxy_edit.id, int) and ID(edit_proxy_edit.id, "PROXY") in ignored_ids:
            continue
        proxy_id = get_id(edit_proxy_edit.id, "PROXY")
        assert isinstance(proxy_id, int)
        edited_proxies.append(proxy_id)
        field_p = edit_proxy_edit.kv.field
        value_p = edit_proxy_edit.kv.value
        if field_p == "name":
            await database.update_name(proxy_id, value_p) # type: ignore
        elif field_p == "description":
            await database.update_description(proxy_id, value_p) # type: ignore
        elif field_p == "avatar_url":
            await database.update_avatar(proxy_id, value_p) # type: ignore
        elif field_p == "triggers":
            await database.update_trigger(proxy_id, value_p) # type: ignore
        elif field_p == "nickname":
            await database.update_nickname(proxy_id, value_p) # type: ignore
        elif field_p == "forms":
            await database.update_forms(proxy_id, value_p) # type: ignore
        elif field_p == "current_form":
            await database.update_current_form(proxy_id, value_p) # type: ignore
        elif field_p == "pronouns":
            await database.update_pronouns(proxy_id, value_p) # type: ignore
        elif field_p == "tags":
            tag_resolved_ids = [get_id(tag, "PROXY_TAG") for tag in value_p] # type: ignore
            resolved = [t for t in tag_resolved_ids if t]
            await database.update_tags(proxy_id, resolved)

    edited_proxy_tags = [*set(edited_proxy_tags)]
    edited_proxies = [*set(edited_proxies)]

    for edited_proxy_tag in edited_proxy_tags:
        t_ = await database.get_tag(edited_proxy_tag)
        modified.append(ModifiedItem(
            type="PROXY_TAG",
            item=ItemUpdateResponse(
                method="UPDATE", id=t_.id, data=ProxyTag.from_source(t_)
            )
        ))

    for edited_proxy in edited_proxies:
        p_ = await database.get_proxy(edited_proxy)
        modified.append(ModifiedItem(
            type="PROXY",
            item=ItemUpdateResponse(
                method="UPDATE", id=p_.id, data=Proxy.from_source(p_)
            )
        ))

    return ModifiedItemResponse(items=modified)
