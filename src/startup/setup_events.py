import asyncio
import time

import discord
import fluxer

from ..backend.database.database import get_db
from ..backend.database.user import SSOID
from ..backend.logging import start_log
from ..backend.models import Platform, MessageDat, GuildDat
from ..backend.utils import quote, DelimitedString
from ..interaction import Interactions
from ..proxying.editing import try_reverse_engineer
from ..proxying.event import on_user_message
from ..proxying.executor import edit_proxy_message
from ..service import Context, Server, FluxerServer, DiscordServer, FluxerContext, DiscordContext, \
    ReactionActionEvent, Embed, Message
from ..service.fluxer import Message as FluxerMessage, ReactionActionEvent as FluxerReactionActionEvent
from ..service.discord import Message as DiscordMessage, ReactionActionEvent as DiscordReactionActionEvent
from ..backend.config import Config
from ..commands.generic import get_command_awaitable, ParseError, EarlyExitException

print, error = start_log("bot")

editing_proxy_messages: dict[tuple[int, Platform], tuple[int, Message]] = {} # (user_id, platform) => (channel id, message)
handled_messages: dict[tuple[int, Platform, str], float] = {} # (message_id, platform, content) => timestamp


async def message_wrapper(context: Context):
    if context.is_bot: return

    content = context.content
    if (context.id, context.platform, content) in handled_messages: return

    handled_messages[context.id, context.platform, content] = time.time()
    await handle_message(context)
    await asyncio.sleep(1)
    handled_messages.pop((context.id, context.platform, content))

cmd_id = 0

async def handle_message(context: Context):
    global cmd_id

    key = (context.author.id, context.platform)
    if key in editing_proxy_messages and editing_proxy_messages[key][0] == context.message.channel_id:
        msg = editing_proxy_messages[key][1]
        editing_proxy_messages.pop(key)
        lnk = await get_db().guilds.get_message_link(MessageDat(msg.id, msg.channel_id, context.platform))
        uid = await get_db().users.get_user_id(SSOID(context.author.id), context.platform)
        if lnk and uid and (channel := await context.get_channel(lnk.dat.channel_id)) and (member := await context.get_member(context.author.id)):
            roles = await member.roles()
            perms = await get_db().permissions.compute_effective_permissions(
                GuildDat(
                    channel.guild_id,
                    context.platform
                ),
                channel.id,
                context.author.id,
                [role.id for role in roles][::-1]
            )
            await edit_proxy_message(msg.context, context.content, lnk, perms, uid)
            await context.reply(f"Message edited! {await msg.mention()}")
            return

    try:
        maybe = await get_command_awaitable(context, Config.cfg(context.platform).prefixes)
        if maybe:
            (cmd_name, args), cmd = maybe
            start_time = time.time()
            print(f"command [{cmd_id}] executed `{cmd_name}` with args {args}")
            await cmd
            print(f"command [{cmd_id}] finished executing (time {(time.time() - start_time) * 1000:.2f}ms)")
            cmd_id += 1
            return
    except ParseError as e:
        await context.reply(f"Error parsing command: {e.message}.\nUse `{Config.prefix(context.platform)}help` to see command shape.")
        return
    except EarlyExitException:
        return

    await on_user_message(context)


EMOJI_WHO = "❓"
EMOJI_DELETE = "❌"
EMOJI_EDIT = "📝"
EMOJI_PING = "🔔"
EMOJI_PING2 = "🛎️"


async def handle_reaction(context: ReactionActionEvent, server: Server):
    user = await context.user()
    if user.is_bot: return

    ctx = await context.context()
    if await Interactions.instance.interact(ctx, user.id, (context, )):
        return

    uid = await get_db().users.get_user_id(SSOID(user.id), ctx.platform)
    message = MessageDat(ctx.id, ctx.message.channel_id, ctx.platform)

    if context.emoji in (EMOJI_WHO, EMOJI_DELETE, EMOJI_EDIT, EMOJI_PING, EMOJI_PING2):
        lnk = await get_db().guilds.get_message_link(message)
        if lnk:
            proxy = await get_db().proxies.get(lnk.proxy_id)
            if not proxy: return
            await ctx.message.remove_reaction(context.emoji, user.id)

            if context.emoji == EMOJI_WHO:
                e = Embed(
                    "Proxied Message",
                    str(
                        DelimitedString("\n") +
                        f"**Proxy**: {proxy.name}" +
                        f"**Owner**: <@{lnk.platform_user}> (`{lnk.platform_user}`)" +
                        f"**Message Link**: [link]({await ctx.message.mention()})" +
                        f"**Message**:\n{quote(ctx.content)}"
                    )
                )
                dm = await user.get_dm()
                if not dm: return
                await dm.send("", [e])

            if context.emoji == EMOJI_DELETE and proxy.owner == uid:
                await get_db().guilds.delete_link_message(message)
                await ctx.message.delete()
                return

            if context.emoji == EMOJI_EDIT and proxy.owner == uid:
                channel = await user.get_dm()
                if not channel: return
                raw = await ctx.get_wh_message_data(ctx)
                await channel.send(f"Editing message:\n```\n{try_reverse_engineer(raw)}\n```")
                await channel.send("Please enter the new content of the message here:")
                editing_proxy_messages[user.id, ctx.platform] = channel.id, raw
                await asyncio.sleep(120)
                if (user.id, ctx.platform) in editing_proxy_messages:
                    await channel.send("Message edit request expired!")
                    editing_proxy_messages.pop((user.id, ctx.platform))

            if context.emoji in (EMOJI_PING, EMOJI_PING2):
                await ctx.reply(
                    f"<@{lnk.platform_user}>, {user.mention} has pinged you! Use :x: to delete this message (expires in 5 minutes).",
                    user_id_override=lnk.platform_user
                )
                return


def setup(server: Server):
    server.ready = False

    @server.event
    async def on_ready():
        server.ready = True
        print(f"Bot is online and ready for platform {server.platform.name}!")

    if server.platform is Platform.Fluxer:
        setup_fluxer(server)

    if server.platform is Platform.Discord:
        setup_discord(server)


def setup_fluxer(server: FluxerServer):
    @server.event
    async def on_message(message: fluxer.Message):
        context = FluxerContext(FluxerMessage(message, server.bot), server.bot)
        await message_wrapper(context)

    @server.event
    async def on_message_edit(message: fluxer.Message):
        context = FluxerContext(FluxerMessage(message, server.bot), server.bot)
        await message_wrapper(context)

    @server.event
    async def on_raw_reaction_add(event: fluxer.models.RawReactionActionEvent):
        context = FluxerReactionActionEvent(event, server.bot)
        await handle_reaction(context, server)

    @server.event
    async def on_message_delete(data: dict):
        channel_id, message_id = int(data["channel_id"]), int(data["id"])
        message = MessageDat(message_id, channel_id, Platform.Fluxer)
        lnk = await get_db().guilds.get_message_link(message)
        if lnk:
            await get_db().guilds.delete_link_message(message)


def setup_discord(server: DiscordServer):
    @server.event
    async def on_message(message: discord.Message):
        if message.type in (discord.MessageType.default, discord.MessageType.reply):
            context = DiscordContext(DiscordMessage(message, server.bot), server.bot)
            await message_wrapper(context)

    @server.event
    async def on_message_edit(before: discord.Message, after: discord.Message):
        context = DiscordContext(DiscordMessage(after, server.bot), server.bot)
        await message_wrapper(context)

    @server.event
    async def on_raw_reaction_add(event: discord.RawReactionActionEvent):
        context = DiscordReactionActionEvent(event, server.bot)
        await handle_reaction(context, server)

    @server.event
    async def on_message_delete(message: discord.Message):
        message = MessageDat(message.id, message.channel.id, Platform.Discord)
        lnk = await get_db().guilds.get_message_link(message)
        if lnk:
            await get_db().guilds.delete_link_message(message)
