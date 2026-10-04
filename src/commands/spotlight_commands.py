from dataclasses import replace
from typing import Sequence

from .generic import hook_command, EarlyExitException
from .specific import get_uid
from .utils import paged_proxy_list, cannot_view_proxy_list
from ..backend.database.database import get_db
from ..backend.database.user import UserID
from ..backend.models import Proxy, FullProxy
from ..service import Context, Embed


async def get_spotlight_proxies(uid: UserID, reformat = False) -> list[FullProxy]:
    user_settings = await get_db().user_settings.get_user_preference(uid)
    spotlights = user_settings.spotlight
    proxies: list[FullProxy] = []
    for spotlight in spotlights:
        prox = await get_db().proxies.get_full(spotlight)
        if prox:
            proxies.append(prox)

    if reformat and len(spotlights) != len(proxies):
        async with get_db().transaction():
            await get_db().user_settings.set_user_preference(uid, replace(user_settings, spotlight=[proxy.id for proxy in proxies]))

    return proxies


async def set_proxies(context: Context, uid: UserID, proxies: Sequence[Proxy]):
    async with get_db().transaction():
        await get_db().user_settings.set_user_preference(
            uid,
            replace(
                await get_db().user_settings.get_user_preference(uid),
                spotlight=[proxy.id for proxy in proxies]
            )
        )

    if proxies:
        await context.reply("", [Embed(
            "Spotlight updated!",
            f"Successfully set your spotlight to **{'**, **'.join(prox.name for prox in proxies)}**!"
        )])
    else:
        await context.reply("", [Embed(
            "Spotlight updated!",
            "Successfully cleared your spotlight!"
        )])

async def ensure_no_dup(context: Context, proxies: Sequence[Proxy]) -> list[Proxy]:
    dup_list = []
    traversed = []
    for prox in proxies:
        if prox in traversed and prox not in dup_list:
            dup_list.append(prox)
        if prox not in traversed:
            traversed.append(prox)
    if dup_list:
        await context.reply(f"Error: proxies cannot appear more than once in spotlight: **{'**, **'.join(prox.name for prox in dup_list)}**")
        raise EarlyExitException()
    return traversed


def setup():
    @hook_command("spotlight list")
    async def _(context: Context):
        uid = await get_uid(context)
        proxies = await get_spotlight_proxies(uid, True)
        channel = await context.get_this_channel()
        preferences = await get_db().user_settings.get_user_preference(uid)
        if preferences.public_spotlight or channel.dm:
            await paged_proxy_list(
                context,
                proxies,
                await get_db().tags.from_user(uid),
                await get_db().relationships.bulk_get_relationships([proxy.id for proxy in proxies]),
                preferences,
                f"Spotlight of {context.author.display_name}",
                0,
                channel.dm
            )
        else:
            await cannot_view_proxy_list(context, f"Spotlight of {context.author.display_name}")


    @hook_command("spotlight set")
    async def _(context: Context, proxies: list[FullProxy]):
        uid = await get_uid(context)
        await set_proxies(context, uid, await ensure_no_dup(context, proxies))


    @hook_command("spotlight clear")
    async def _(context: Context):
        uid = await get_uid(context)
        await set_proxies(context, uid, [])


    @hook_command("spotlight add")
    async def _(context: Context, proxy: FullProxy):
        uid = await get_uid(context)
        proxies = await get_spotlight_proxies(uid)
        proxies.append(proxy)
        await set_proxies(context, uid, await ensure_no_dup(context, proxies))


    @hook_command("spotlight pop")
    async def _(context: Context):
        uid = await get_uid(context)
        proxies = await get_spotlight_proxies(uid)
        if len(proxies) == 0:
            await context.reply("Error: you have no proxies in your spotlight!")
        proxies.pop()
        await set_proxies(context, uid, proxies)


    @hook_command("spotlight insert")
    async def _(context: Context, proxy: FullProxy, index: int):
        uid = await get_uid(context)
        proxies = await get_spotlight_proxies(uid)
        index_0 = index - 1
        if 0 <= index_0 < len(proxies):
            proxies.insert(index_0, proxy)
            await set_proxies(context, uid, await ensure_no_dup(context, proxies))
        else:
            await context.reply(f"Error: cannot insert into index {index}!")