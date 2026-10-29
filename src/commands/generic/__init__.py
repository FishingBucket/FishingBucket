import inspect
from typing import Callable, Coroutine, Any, Concatenate

from .data import Command, Argument, CharacterStream, ParsingArgument, ParseError, CommandGroup
from .strategies import strategize
from ...backend.models import Platform
from ...context import config
from ...service import Context


class EarlyExitException(Exception): pass


type CommandCallable[**P] = Callable[Concatenate[Context, P], Coroutine[Any, Any, Any]]

command_registry: dict[str, Command] = {}
command_hooks: dict[tuple[str, Platform], CommandCallable] = {}
command_groups: dict[str, CommandGroup] = {}
session_command_usages: int = 0


def get_session_command_usages() -> int:
    return session_command_usages


type with_alias = dict[str, list[str]]


def make_command(
        name: str | with_alias | dict[str, str] | dict[str, with_alias],
        brief: str,
        description: str,
        arguments: list[Argument],
) -> str:
    global command_registry

    command_id: str
    n: str
    aliases: list[str]

    if isinstance(name, dict):
        command_id = [*name.keys()][0]
        possible_aliases = name[command_id]
        if isinstance(possible_aliases, list):
            aliases = possible_aliases
            n = command_id
        else:
            if isinstance(possible_aliases, dict):
                n = [*possible_aliases.keys()][0]
                aliases = possible_aliases[n]
            else:
                n = possible_aliases
                aliases = []
    else:
        n = name
        command_id = n
        aliases = []

    command = Command(command_id, command_id, n, aliases, brief, description, arguments)
    command_registry[command_id] = command

    command_registry = dict(sorted(command_registry.items(), key=lambda kv: len(kv[0]), reverse=True))

    return command_id


def make_command_group(
        identifier: str,
        brief: str,
        description: str,
        prefix: str | dict[str, list] | None = None
) -> CommandGroup:
    pre: str | None = None
    ali: list[str] = []

    if isinstance(prefix, str):
        pre = prefix
    elif isinstance(prefix, dict):
        pre = [*prefix.keys()][0]
        ali = [*prefix.values()][0]

    group = CommandGroup(identifier, brief, description, [], pre, ali)
    command_groups[identifier] = group
    return group


def get_command_invocation(command: str, platform: Platform) -> str:
    return f"{config().cfg(platform).prefixes[0]}{command_registry[command].get_usage(strategize)}"


def get_commands() -> dict[str, Command]:
    return command_registry


def get_command_groups() -> dict[str, CommandGroup]:
    return command_groups


def hook_command[**P](name: str, platform: Platform | None = None) -> Callable[[CommandCallable[P]], None]:
    if name not in command_registry:
        raise KeyError(f"Command {name!r} not found.")

    def wrap(inner: CommandCallable[P]):
        sig = inspect.signature(inner)
        arg_count = len(sig.parameters)
        cmd = command_registry[name]
        if arg_count != len(cmd.arguments) + 1: # +1 for context
            raise KeyError(f"Hook for {name!r} for {platform.name if platform else 'all platforms'} does not have the expected number of parameters.")

        if platform is None:
            for plat in Platform:
                command_hooks[name, plat] = inner
        else:
            command_hooks[name, platform] = inner
    return wrap


async def parse_command_arguments(clean_string: str, arguments: list[Argument], context: Context) -> list[Any]:
    stream = CharacterStream(clean_string)
    results = []
    for idx, arg in enumerate(arguments):
        strat = strategize(arg.strategy)

        if not strat.accept_end_of_stream and stream.end:
            raise ParseError(f"unexpected end of arguments while trying to parse argument #{idx + 1} `{arg.name}`")

        try:
            results.append(await strat.parse(stream, ParsingArgument(arg, idx, len(arguments) - idx - 1), context))
        except ParseError as e:
            raise ParseError(f"error parsing argument #{idx + 1} `{arg.name}`: {e.message}")

        if not strat.expect_start_another:
            try:
                stream.expect_argument_end()
            except ParseError as e:
                raise ParseError(f"error transitioning to argument #{idx + 2}: {e.message}")

    return results


def strip_prefix(text: str, prefix: str, aliases: list[str], check_space: bool = True) -> tuple[str | None, str]:
    key = [prefix] + [*sorted([alias.lower() for alias in aliases], key=len, reverse=True)]
    key = [k for k in key if k]
    if any(text.lower().startswith((matched_prefix := a).lower()) for a in key):
        trimmed = text[len(matched_prefix):]
        if not check_space or trimmed == "" or trimmed[0] == " ":
            return matched_prefix, trimmed.strip()
    return None, ""


async def get_command_awaitable(context: Context, prefixes: list[str]) -> tuple[tuple[str, list], Coroutine[Any, Any, Any]] | None:
    global session_command_usages
    used_prefix, content = strip_prefix(context.content, "", prefixes, False)
    if not used_prefix:
        return None

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
        possible_commands = [cmd for cmd in command_registry if all(not group.prefix or cmd not in group.commands for group in command_groups.values())]

    for possible_command in possible_commands:
        command = command_registry[possible_command]
        matched_alias, arguments_raw = strip_prefix(content, command.name, command.aliases)
        if matched_alias:
            arguments = await parse_command_arguments(arguments_raw, command.arguments, context)
            session_command_usages += 1
            return (possible_command, arguments), command_hooks[possible_command, context.platform](context, *arguments)

    return None
