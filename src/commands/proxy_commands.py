from datetime import datetime, timedelta
from typing import Literal

from textdistance import damerau_levenshtein as edit_distance

from .generic import hook_command, EarlyExitException
from .specific import get_uid, get_or_make_uid
from .utils import example_trigger_text, paged_proxy_list, get_proxy_text
from ..backend.database.database import get_db
from ..backend.database.guild import MessageLink
from ..backend.database.user_setting import AutoproxyType, AutoproxyPreference
from ..backend.models import ID, MessageDat, GuildDat, FullProxy
from ..backend.template_utils import Template
from ..backend.utils import normalize_emojis, quote
from ..proxying.executor import reproxy, edit_proxy_message
from ..service import Context, Embed, Message


async def require_reply(context: Context) -> tuple[MessageLink, Message]:
    uid = await get_uid(context)

    if ref := await context.message.get_reference():
        message_id = ref.id
        message_link = await get_db().guilds.get_message_link(MessageDat(
            message_id, context.channel.id, context.platform
        ))
    else:
        message_link = await get_db().guilds.latest_message_link_from_user(context.channel.id, context.platform, uid)

    if not message_link or not (message := await context.channel.get_message(message_link.dat.message_id)):
        await context.reply("Error: there are no previous proxied messages from you in this channel!")
        raise EarlyExitException()

    return message_link, message


def setup():
    @hook_command("register")
    async def _(context: Context, name: str, trigger: Template):
        name = normalize_emojis(name)

        if not context.message.attachments:
            avatar_url = FullProxy.random_avatar()
        else:
            avatar_url = context.message.attachments[0].url

        async with get_db().transaction():
            new_proxy_id = await get_db().proxies.put(
                FullProxy(
                    ID(0),
                    name,
                    "",
                    avatar_url,
                    [trigger.string],
                    await get_or_make_uid(context),
                    datetime.now().timestamp(),
                    "",
                    {},
                    "",
                    "",
                    0
                )
            )

        embed = Embed(
            f"{name} (`{new_proxy_id}`)",
            f"Proxy **{name}** is registered with an ID of `{new_proxy_id}`!\nSay hello with it by typing `{example_trigger_text(trigger)}`",
            thumbnail_url=avatar_url
        )
        await context.reply("", [embed])


    @hook_command("list")
    async def _(context: Context, page: int, detailed: bool):
        channel = await context.get_this_channel()
        uid = await get_uid(context)

        await paged_proxy_list(
            context,
            proxies := await get_db().proxies.full_from_user(uid),
            await get_db().tags.from_user(uid),
            await get_db().relationships.bulk_get_relationships([proxy.id for proxy in proxies]),
            await get_db().user_settings.get_user_preference(uid),
            f"Registered Proxies of {context.author.display_name}",
            page,
            channel.dm or detailed
        )


    @hook_command("find")
    async def _(context: Context, name: str):
        uid = await get_uid(context)

        norm_name = normalize_emojis(name)
        user_proxies = await get_db().proxies.full_from_user(uid)

        errors = []

        distances = {
            i: min(
                edit_distance(
                    norm_name.lower(), candidate.name.lower()
                ),
                edit_distance(
                    norm_name.lower(), (candidate.nickname or candidate.name).lower()
                )
            )
            for i, candidate in enumerate(user_proxies)
        }
        sorted_distances = dict(sorted(distances.items(), key=lambda kv: kv[1]))

        minimum_distance = min(distances.items(), key=lambda kv: kv[1])
        if minimum_distance[1] > 5:
            errors.append("- No name is close enough to the search term.")
        if [*distances.values()].count(minimum_distance[1]) > 1:
            errors.append("- There are two or more proxies with the same degree of similarity in name.")

        additional_embeds = []
        if errors:
            additional_embeds.append(Embed(
                "Errors",
                "\n".join(errors)
            ))

        distanced_proxies = [user_proxies[i] for i in sorted_distances if sorted_distances[i] <= 5]
        relationships = await get_db().relationships.bulk_get_relationships([proxy.id for proxy in distanced_proxies])

        await paged_proxy_list(
            context,
            distanced_proxies,
            await get_db().tags.from_user(uid),
            relationships,
            await get_db().user_settings.get_user_preference(uid),
            f"Proxy Search: **{name}**",
            0,
            False
        )


    @hook_command("info")
    async def _(context: Context, proxy: FullProxy, detailed: bool = False):
        channel = await context.get_this_channel()
        uid = await get_uid(context)

        detailed = channel.dm or detailed

        await context.reply("", [Embed(
            proxy.name,
            get_proxy_text(
                proxy,
                await get_db().tags.fetch_bulk(await get_db().relationships.get_relationships(proxy.id)),
                await get_db().user_settings.get_user_preference(uid),
                detailed
            ),
            thumbnail_url=proxy.effective_avatar
        )])


    @hook_command("reproxy")
    async def _(context: Context, proxy: FullProxy):
        uid = await get_uid(context)

        message_link, message = await require_reply(context)

        proxy_id = message_link.proxy_id
        old_proxy = await get_db().proxies.get(proxy_id)

        if not old_proxy or old_proxy.owner != uid:
            await context.reply("Error: you do not own the original proxy!")
            return

        await context.message.delete()
        await reproxy(message_link, message.context, old_proxy, proxy)


    @hook_command("autoproxy")
    async def _(
            context: Context,
            setting: FullProxy | Literal["latch"] | Literal["spotlight"] | bool,
            mode: Literal["global"] | Literal["community"] | None,
            expires: timedelta | Literal["never"]
    ):
        if setting == "latch":
            setting = True

        if expires == "never":
            expiration = None
        else:
            expiration = expires.total_seconds()

        if mode == "global" or mode is None:
            guild = GuildDat(0, context.platform)
            postfix = "globally"
        else:
            guild = GuildDat(context.guild.id, context.platform)
            postfix = "in this community"

        uid = await get_uid(context)

        if setting is True:
            async with get_db().transaction():
                await get_db().user_settings.set_autoproxy_preference(uid, AutoproxyPreference(
                    guild,
                    None,
                    None,
                    expiration,
                    AutoproxyType.NORMAL
                ))

            await context.reply(f"Autoproxy has been set to latch mode {postfix}.")

        elif setting == "spotlight":
            async with get_db().transaction():
                await get_db().user_settings.set_autoproxy_preference(uid, AutoproxyPreference(
                    guild,
                    None,
                    None,
                    expiration,
                    AutoproxyType.SPOTLIGHT
                ))

            await context.reply(f"Autoproxy has been set to first spotlight proxy {postfix}.")

        elif setting is False:
            if mode is None:
                async with get_db().transaction():
                    await get_db().user_settings.remove_all_autoproxy_preference(uid)

                await context.reply("Autoproxy has been turned off for everything.")

            else:
                async with get_db().transaction():
                    await get_db().user_settings.remove_single_autoproxy_preference(uid, guild)

                await context.reply(f"Autoproxy has been turned off {postfix}.")

        else:
            assert isinstance(setting, FullProxy)

            async with get_db().transaction():
                await get_db().user_settings.set_autoproxy_preference(uid, AutoproxyPreference(
                    guild,
                    setting.id,
                    None,
                    expiration,
                    AutoproxyType.NORMAL
                ))

            await context.reply(f"Autoproxying as **{setting.name}** {postfix}.")


    @hook_command("who")
    async def _(context: Context):
        if not (ref := await context.message.get_reference()):
            await context.reply("Error: reply to a proxied message to use this command.")
            return

        lnk = await get_db().guilds.get_message_link(MessageDat(ref.id, ref.channel_id, context.platform))
        if lnk:
            if proxy := await get_db().proxies.get(lnk.proxy_id):
                e = Embed(
                    "Proxied Message",
                    f"**Proxy**: {proxy.name}\n**Owner**: <@{lnk.platform_user}> (`{lnk.platform_user}`)\n**Message Link**: [link]({await ref.mention()})\n**Message**:\n{quote(ref.content)}"
                )
                dm = await context.author.get_dm()
                if dm:
                    await dm.send("", [e])
                    await context.message.delete()
                return

        await context.reply("Error: that message is not a proxied message!")


    @hook_command("delete")
    async def _(context: Context, bypass: bool):
        if not (ref := await context.message.get_reference()):
            await context.reply("Error: reply to a proxied message to use this command.")
            return

        message = MessageDat(ref.id, ref.channel_id, context.platform)

        lnk = await get_db().guilds.get_message_link(message)
        if lnk:
            member = await context.get_member(context.author.id)
            if not member: return

            bypasses = bypass and (await context.channel.permissions_for(member)).manage_messages

            if (proxy := await get_db().proxies.get(lnk.proxy_id)) and (bypasses or proxy.owner == await get_uid(context)):
                async with get_db().transaction():
                    await get_db().guilds.delete_link_message(message)

                await ref.delete()
                await context.message.delete()
                return

            await context.reply("Error: you do not own this proxy!")
            return

        await context.reply("Error: that message is not a proxied message!")


    @hook_command("edit")
    async def _(context: Context, message: str):
        uid = await get_uid(context)

        message_link, ref = await require_reply(context)

        proxy_id = message_link.proxy_id
        old_proxy = await get_db().proxies.get(proxy_id)

        if not old_proxy or old_proxy.owner != uid:
            await context.reply("Error: you do not own the original proxy!")
            return

        await context.message.delete()
        await edit_proxy_message(ref.context, message, message_link, uid)

