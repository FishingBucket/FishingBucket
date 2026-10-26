import platform
import sys
from datetime import datetime
from typing import Any

from .generic import hook_command, get_commands, get_command_groups, strategize, Command, CommandGroup, \
    get_session_command_usages, get_command_invocation, strip_prefix
from .utils import paged
from ..backend.template_utils import Template
from ..backend.models import Platform
from ..context import config, database, context as app_context
from ..service import Context, Embed


def setup():
    start_time = datetime.now()

    @hook_command("ping")
    async def _(context: Context):
        stime = context.message.timestamp
        m = await context.reply(f"Pong! Latency is calculating! :ping_pong:")
        etime = m.message.timestamp
        diff = etime - stime
        await m.message.edit(f"Pong! Latency is {int(diff.microseconds / 1000)} ms! :ping_pong:")


    @hook_command("invite")
    async def _(context: Context):
        def get_invites(plat: Platform) -> tuple[str, str]:
            return config().cfg(plat).bot_invite, config().cfg(plat).guild_invite

        bot_invite, server_invite = get_invites(context.platform)
        description = f"Use [this link]({bot_invite}) to invite me to your community!\nSupport community invite: {server_invite}."

        if len(Platform) > 1:
            description += "\n\n"
            parts = []
            for platform in Platform:
                if platform != context.platform and config().cfg(platform):
                    b, s = get_invites(platform)
                    parts.append(f"Come join us on {platform.name}! [Invite bot]({b}) and [join community]({s})!")
            description += "\n".join(parts)

        await context.reply("", embeds=[
            Embed(
                "Invite Me!",
                description
            )
        ])


    @hook_command("help")
    async def _(context: Context, topic: str | None):
        def get_description(thing: Command | CommandGroup) -> str:
            desc = thing.description.strip()
            result = []
            for line in desc.split("\n"):
                result.append(line.strip())
            return "\n".join(result)

        if topic is None:
            pages = [
                Template.from_string(app_context().data_reader["help.md"])
                .compute(Template.get_default_metatext_variables(context), "")
            ]
            for group_id, group in get_command_groups().items():
                page = f"**{group.brief}** (`{group.canonical_name}`): {group.description}\n"
                for cmd_id in group.commands:
                    cmd = get_commands()[cmd_id]
                    page += f"\n- `{get_command_invocation(cmd_id, context.platform)}` - {cmd.brief}"
                pages.append(page)

            await paged(
                context,
                "Help",
                pages,
                0
            )
            return

        groups = get_command_groups()
        if topic in groups:
            group = groups[topic]
            description = f"**{group.brief}** (`{group.canonical_name}`): {group.description}\n"
            for cmd_id in group.commands:
                cmd = get_commands()[cmd_id]
                description += f"\n- `{config().cfg(context.platform).prefixes[0]}{cmd.get_usage(strategize)}` - {cmd.brief}"

            await context.reply("", [Embed(f"Help: {group.brief}", description)])
            return

        commands = get_commands()
        command_groups = get_command_groups()

        content = topic

        possible_commands: list[str]
        for group in command_groups.values():
            if not group.prefix:
                continue
            matched_maj, subcontent = strip_prefix(content, group.prefix, group.prefix_aliases)
            if matched_maj and subcontent:
                possible_commands = group.commands
                content = subcontent
                break
        else:
            possible_commands = [cmd for cmd in commands if all(not group.prefix or cmd not in group.commands for group in command_groups.values())]

        for possible_command in possible_commands:
            command = commands[possible_command]
            matched_alias, _ = strip_prefix(content, command.name, command.aliases)
            if matched_alias:
                description = f"**Usage**: `{config().cfg(context.platform).prefixes[0]}{command.get_usage(strategize)}`\n\n{get_description(command)}\n\n**Examples**:"
                examples = []
                for _ in range(10):
                    example = command.get_example_invocation()
                    if example not in examples:
                        examples.append(example)

                    if len(examples) == 3:
                        break

                for example in sorted(examples, key=len):
                    description += f"\n- `{config().cfg(context.platform).prefixes[0]}{example}`"

                await context.reply("", [Embed(f"Help: {config().cfg(context.platform).prefixes[0]}{topic}", description)])
                return

        await context.reply(f"Error: `{topic}` is not a valid topic!")


    @hook_command("explain")
    async def _(context: Context):
        await context.reply(
            Template.from_string(app_context().data_reader["explain.md"])
            .compute(Template.get_default_metatext_variables(context), "")
        )


    @hook_command("stats")
    async def _(context: Context, stat: str | None):
        db_stats: dict[str, Any] = await database().get_global_stats()
        stats = {
            "guilds": ("Total community count", str(len(context.bot.guilds))),
            "uptime": ("Uptime", str(datetime.now() - start_time)),
            "commands": ("Total commands", str(len(get_commands()))),
            "proxy_uses": ("Total proxy uses", str(int(db_stats["proxy_uses"]))),
            "total_proxies": ("Total registered proxies", str(int(db_stats["total_proxies"]))),
            "invocations": ("Session command invocations", str(get_session_command_usages())),
            "database_version": ("Database version", str(int(db_stats["version"]))),
            "version": ("Code version", app_context().data_reader["last_commit"]),
            "system": ("System", f"{platform.system()} {platform.release()} {platform.version()} {platform.machine()}"),
            "framework": ("Framework", f"custom (using fluxer.py + py-cord) w/ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        }
        if stat:
            k, v = stats[stat]
            await context.reply("", embeds=[Embed(
                f"{config().name} Statistics",
                f"**{k}** (`{stat}`): {v}"
            )])
        else:
            await context.reply("", embeds=[Embed(
                f"{config().name} Statistics",
                "\n".join(f"**{k}** (`{stat}`): {v}" for stat, (k, v) in stats.items())
            )])


    if site := config().website:
        @hook_command("dashboard")
        async def _(context: Context):
            await context.reply(f"The link to the dashboard can be accessed [here]({site.dashboard}).")

        @hook_command("website")
        async def _(context: Context):
            await context.reply(f"Come visit the website for {config().name} [here]({site.home}).")

        @hook_command("legal")
        async def _(context: Context):
            await context.reply(f"Please view our Terms of Service [here]({site.terms}), and our Privacy Policy [here]({site.privacy}).")

        @hook_command("contact")
        async def _(context: Context):
            await context.reply(f"Contact us [here]({site.contact})!")

    if config().donation:
        @hook_command("donate")
        async def _(context: Context):
            await context.reply(f"Donate to this project [here]({config().donation})!")
