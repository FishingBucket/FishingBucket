from dataclasses import replace
from functools import reduce
from typing import Literal, Sequence

from .generic import hook_command
from .utils import require_permissions
from ..backend.database.database import get_db
from ..backend.database.permission import GuildPermissions, AllowDenyPair, IDType, DISPLAY_GUILD_PERMISSION, \
    GUILD_PERMISSION_DISPLAY
from ..backend.models import GuildDat
from ..service import Context, Channel, Role, User, Embed


def setup():
    @hook_command("permissions set")
    async def _(
            context: Context,
            targets: list[Channel | Role | User] | Literal["community"],
            allow: bool | Literal["default"],
            permissions: list[str]
    ):
        await require_permissions(context, lambda p: p.manage_guild)
        channel = await context.get_this_channel()

        guild = GuildDat(channel.guild_id, context.platform)

        perms = reduce(
            (lambda total, p: total | p),
            (DISPLAY_GUILD_PERMISSION[perm] for perm in permissions),
            initial=GuildPermissions(0)
        )
        if allow is True:
            pair = AllowDenyPair(perms, GuildPermissions(0))
        elif allow is False:
            pair = AllowDenyPair(GuildPermissions(0), perms)

        overrides = await get_db().permissions.get_all_guild_overrides(guild)

        normalized_targets: Sequence[Channel | Role | User | Literal["community"]]
        if targets == "community":
            normalized_targets = ["community"]
        else:
            normalized_targets = targets

        items: list[str] = []

        async with get_db().transaction():
            for target in normalized_targets:
                target_id = 0
                target_id_type = IDType.BASE
                type_ = "this community"

                if isinstance(target, Channel):
                    target_id = target.id
                    target_id_type = IDType.CHANNEL
                    type_ = f"<#{target.id}>"
                elif isinstance(target, Role):
                    target_id = target.id
                    target_id_type = IDType.ROLE
                    type_ = f"<@&{target.id}>"
                elif isinstance(target, User):
                    target_id = target.id
                    target_id_type = IDType.USER
                    type_ = f"<@{target.id}>"

                previous = overrides[target_id_type].get(target_id, AllowDenyPair.default())

                if allow == "default":
                    previous.allows &= ~perms.value
                    previous.denies &= ~perms.value
                else:
                    previous.allows |= pair.allows
                    previous.denies |= pair.denies

                items.append(f"{type_}: allows {", ".join(
                    GUILD_PERMISSION_DISPLAY[t]
                    for t in previous.allows
                ) if previous.allows else "nothing"}, denies {", ".join(
                    GUILD_PERMISSION_DISPLAY[t]
                    for t in previous.denies
                ) if previous.denies else "nothing"}")

                await get_db().permissions.override(
                    target_id,
                    target_id_type,
                    guild,
                    previous
                )


        await context.reply("", [Embed(
            "Community Settings Changed!",
            f"Permissions has been changed! New changes:\n{"\n- ".join(items)}"
        )])


    @hook_command("permissions reset")
    async def _(context: Context):
        await require_permissions(context, lambda p: p.manage_guild)
        channel = await context.get_this_channel()

        guild = GuildDat(channel.guild_id, context.platform)

        async with get_db().transaction():
            await get_db().permissions.remove_all_overrides(guild)

        await context.reply("", [Embed(
            "Community Settings Changed!",
            f"All custom community proxy settings has been reset to the default."
        )])


    @hook_command("permissions list")
    async def _(context: Context):
        channel = await context.get_this_channel()

        guild = GuildDat(channel.guild_id, context.platform)

        preferences = await get_db().permissions.get_all_guild_overrides(guild)

        final_text: list[str] = []
        for id_type in (
            IDType.BASE,
            IDType.CHANNEL,
            IDType.ROLE,
            IDType.USER
        ):
            if not preferences[id_type]: continue

            prefix = "Community"

            if id_type == IDType.CHANNEL:
                prefix = "Channels"
            elif id_type == IDType.ROLE:
                prefix = "Roles"
            elif id_type == IDType.USER:
                prefix = "Users"

            texts: list[str] = []
            for id_, pair in preferences[id_type].items():
                id_display = "initially"
                if id_type == IDType.CHANNEL:
                    id_display = f"<#{id_}>"
                elif id_type == IDType.ROLE:
                    id_display = f"<@&{id_}>"
                elif id_type == IDType.USER:
                    id_display = f"<@{id_}>"

                texts.append(f"{id_display}: allows {", ".join(
                    GUILD_PERMISSION_DISPLAY[t]
                    for t in pair.allows
                ) if pair.allows else "nothing"}, denies {", ".join(
                    GUILD_PERMISSION_DISPLAY[t]
                    for t in pair.denies
                ) if pair.denies else "nothing"}")

            final_text.append(prefix + "\n" + "\n- ".join(texts))

        await context.reply("", [Embed(
            "Community Permissions",
            "\n\n".join(final_text)
        )])



    @hook_command("log set")
    async def _(context: Context, log_channel: Channel | None):
        channel = await context.get_this_channel()

        guild = GuildDat(channel.guild_id, context.platform)
        prefs = await get_db().guilds.get_guild_preferences(guild)

        async with get_db().transaction():
            await get_db().guilds.set_guild_preferences(
                replace(prefs, logging_channel=log_channel.id if log_channel else 0)
            )

        if log_channel is None:
            await context.reply("", [Embed(
                "Community Settings Changed!",
                "Logging is now disabled for this community!"
            )])
        else:
            await context.reply("", [Embed(
                "Community Settings Changed!",
                f"Proxied messages will be logged to <#{log_channel.id}>."
            )])


    @hook_command("log view")
    async def _(context: Context):
        channel = await context.get_this_channel()

        guild = GuildDat(channel.guild_id, context.platform)
        prefs = await get_db().guilds.get_guild_preferences(guild)

        log_channel = prefs.logging_channel

        await context.reply("", [Embed(
            "Community Settings",
            f"The community logging channel is set to <#{log_channel}>." if log_channel else "There is no logging channel set in this community."
        )])

