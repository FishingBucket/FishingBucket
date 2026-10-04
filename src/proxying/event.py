from dataclasses import replace

from .editing import is_replace, do_replace
from .executor import get_webhook, edit_proxy_message, send_proxy_message
from .matcher import get_proxied_messages
from ..backend.database.database import get_db
from ..backend.database.guild import MessageLink
from ..backend.database.permission import GuildPermissions
from ..backend.database.user import SSOID
from ..backend.logging import start_log
from ..backend.models import GuildDat, MessageDat
from ..backend.utils import quote, DelimitedString
from ..commands.specific import get_uid_nullable
from ..service import Context, Webhook, Embed

print, error = start_log("send_proxy", "-prox")

async def on_user_message(context: Context):
    channel = await context.get_this_channel()

    if channel.dm:
        return

    owner = await get_uid_nullable(context)
    if owner is None: return

    guild = GuildDat(channel.guild_id, context.platform)
    if (member := await context.get_member(context.author.id)) is None: return

    roles = await member.roles()

    permission = await get_db().permissions.compute_effective_permissions(
        guild,
        channel.id,
        context.author.id,
        [role.id for role in roles][::-1],
    )

    if GuildPermissions.PROXYING in permission:
        autoproxy_prefs = await get_db().user_settings.get_effective_autoproxy_preference(owner, guild)
        replace_dat = is_replace(context.content)

        if replace_dat:
            message_link = await get_db().guilds.latest_message_link_from_user(context.channel.id, context.platform, owner)
            if not message_link or (message := await context.channel.get_message(message_link.dat.message_id)) is None:
                return
            webhook: Webhook = await get_webhook(message.context)
            new_context = await webhook.get_message_data(message.context)
            if (proxy := await get_db().proxies.get(message_link.proxy_id)) is None:
                return

            await edit_proxy_message(
                message.context,
                do_replace(replace_dat, new_context.content),
                message_link,
                proxy.owner
            )
            await context.message.delete()
            return

        print(f"Message [{context.message.id}] trying to match")
        proxied = await get_proxied_messages(context.content, owner, permission, autoproxy_prefs)
        print(f"Message [{context.message.id}] match subroutine completed")
        if proxied:
            guild_preferences = await get_db().guilds.get_guild_preferences(guild)
            logging_channel_id = guild_preferences.logging_channel
            if logging_channel_id != 0:
                logging_channel = await context.get_channel(logging_channel_id)
            else:
                logging_channel = None

            for i, proxied_message in enumerate(proxied):
                proxy = proxied_message.proxy
                assert isinstance(proxy.id, int)

                if not (proxied_message.message or context.message.attachments):
                    return

                try:
                    ctx, proxy_effective_name = await send_proxy_message(
                        proxied_message.proxy,
                        proxied_message.message,
                        context,
                        context.message.attachments if i == 0 else [],
                        True,
                        i == 0,
                        permission
                    )
                except Exception as e:
                    error(e)
                    await context.reply(f"Messages could not be proxied! `{e}`")
                    return

                if ctx:
                    await get_db().guilds.link_message(MessageLink(
                        MessageDat(
                            ctx.id,
                            ctx.message.channel_id,
                            context.platform
                        ),
                        proxy.id,
                        SSOID(context.author.id)
                    ))

                if logging_channel and ctx:
                    ref = await context.message.get_reference()
                    reply_msg = f"**Replying To**: [message link]({await ref.mention()})\n" if ref and i == 0 else None
                    embed = Embed(
                        f"Proxied Message",
                        str(
                            DelimitedString("\n", reply_msg) +
                            f"**Proxy**: {proxy_effective_name}" +
                            f"**Owner**: {context.author.mention} (`{context.author.id}`)" +
                            f"**Channel**: {context.channel.mention} (`{context.channel.id}`)" +
                            f"**Message Link**: [jump]({await ctx.message.mention()})" +
                            f"**Message**:\n{quote(proxied_message.message)}"
                        ),
                        thumbnail_url=proxy.effective_avatar
                    )
                    await logging_channel.send("", [embed])

                await get_db().proxies.use(proxy.id)

            if proxied:
                if autoproxy_prefs:
                    autoproxy_prefs = replace(autoproxy_prefs, last_used_proxy=proxied[-1].proxy.id)
                    await get_db().user_settings.set_autoproxy_preference(owner, autoproxy_prefs)

            await context.message.delete()
