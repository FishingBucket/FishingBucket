import random

from textdistance import damerau_levenshtein as edit_distance

from ..generic import CharacterStream, ParsingArgument, EarlyExitException, get_command_invocation
from ..generic.data import Strategy, SyntaxParseError, ParseError
from ..generic.misc import escape_string
from ..generic.strategies import OneOf, HexadecimalStrategy, StringStrategy, IntegerStrategy
from ...backend.config import Config
from ...backend.database.database import get_db
from ...backend.database.user import UserID, SSOID
from ...backend.models import Proxy, ProxyTag, FullProxy, ID
from ...backend.template_utils import Template, ExprPart
from ...backend.utils import normalize_emojis
from ...service import Context


async def get_or_make_uid(context: Context) -> UserID:
    return await get_db().users.get_or_create_user_id(SSOID(context.author.id), context.platform)


async def get_uid_nullable(context: Context) -> UserID | None:
    return await get_db().users.get_user_id(SSOID(context.author.id), context.platform)


async def get_uid(context: Context) -> UserID:
    uid = await get_db().users.get_user_id(SSOID(context.author.id), context.platform)
    if uid is None:
        await context.reply(f"Error: you do not have an account! You can create one by using the `{get_command_invocation('register', context.platform)}` command.")
        raise EarlyExitException()
    return uid


class ProxyStrategy(Strategy):
    def __init__(self, enforce_ownership: bool = True):
        self.enforce_ownership = enforce_ownership

    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> FullProxy:
        owner = await get_uid(context)
        try:
            prox = await OneOf(hex, str).parse(stream, argument, context)
            if isinstance(prox, int):
                proxy = await get_db().proxies.get_full(ID(prox))

                if not proxy:
                    raise ParseError("this proxy does not exist")

                if self.enforce_ownership and proxy.owner != owner:
                    raise ParseError("you do not own this proxy")

            else:
                norm_name = normalize_emojis(prox)
                user_proxies = await get_db().proxies.full_from_user(owner)
                if not user_proxies:
                    raise ParseError("you do not own any proxies")

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
                minimum_distance = min(distances.items(), key=lambda kv: kv[1])
                if minimum_distance[1] > 5 or [*distances.values()].count(minimum_distance[1]) > 1:
                    raise ParseError(f"cannot pinpoint a proxy from its name")

                proxy = user_proxies[minimum_distance[0]]

            return proxy

        except SyntaxParseError:
            raise SyntaxParseError(f"not a valid proxy ID nor a proxy name")


    def example(self) -> str:
        return random.choice(["proxy", "\"proxy name\"", HexadecimalStrategy().example()])

    def get_placeholder_text(self) -> str:
        return "proxy"


PROXY_TAG_OPTIONS = [
    '"My Tag Name"', 'proxytag', 'helpers', 'characters', 'oc', 'fronters', 'spotlight',
    'frequent', 'webhook'
]


class ProxyTagStrategy(Strategy):
    def __init__(self, enforce_ownership: bool = True):
        self.enforce_ownership = enforce_ownership

    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> ProxyTag:
        owner = await get_uid(context)
        try:
            tg = await OneOf(hex, str).parse(stream, argument, context)
            if isinstance(tg, int):
                tag = await get_db().tags.get(ID(tg))

                if not tag:
                    raise ParseError("this proxy tag does not exist")

                if self.enforce_ownership and tag.owner != owner:
                    raise ParseError("you do not own this proxy tag")

            else:
                norm_name = normalize_emojis(tg)
                user_tags = await get_db().tags.from_user(owner)
                if not user_tags:
                    raise ParseError("you do not own any proxy tags")

                distances = {
                    i: edit_distance(
                        norm_name.lower(), candidate.name.lower()
                    )
                    for i, candidate in enumerate(user_tags)
                }
                minimum_distance = min(distances.items(), key=lambda kv: kv[1])
                if minimum_distance[1] > 5 or [*distances.values()].count(minimum_distance[1]) > 1:
                    raise ParseError(f"cannot pinpoint a proxy tag from its name")

                tag = user_tags[minimum_distance[0]]

            return tag

        except SyntaxParseError:
            raise SyntaxParseError(f"not a valid proxy tag ID nor a tag name")


    def example(self) -> str:
        return random.choice(["tag", "\"proxy tag name\"", *PROXY_TAG_OPTIONS, HexadecimalStrategy().example()])

    def get_placeholder_text(self) -> str:
        return "proxy tag"


class TemplateStrategy(Strategy):
    def __init__(self, variables: list[str], force_template: bool = True):
        self.variables = variables
        self.force_template = force_template

    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> Template:
        string = await StringStrategy().parse(stream, argument, context)
        if "text" in string and not ("{" in string and "}" in string):
            string = string.replace("text", "{}", 1)
            await context.reply(f"Note: {Config.name()} uses `{'{}'}` for placeholders instead of `text`. Your input has been auto-coerced to use `{'{}'}`.")

        template = Template.from_string(string)
        if template.errors:
            await context.reply(f"Warning: template parsing encountered errors:\n{'\n'.join(('- ' + err) for err in template.errors)}")

        if template.get_expr_count() == 0 and self.force_template:
            raise ParseError("template must contain the literal `{}`, or have an expression slot")

        for part in template.parts:
            if isinstance(part, ExprPart):
                if part.content:
                    if not any(var in part.content for var in self.variables):
                        raise ParseError(f"template, if not empty, must refer one of these variables: `{'`, `'.join(self.variables)}`")

        return template


    def example(self) -> str:
        string = random.choice(["prefix, ", ""]) + random.choice(["{}"] + ["{" + var + "}" for var in self.variables])
        for _ in range(random.randint(0, 2)):
            string += ", infix, " + random.choice(["{}"] + ["{" + var + "}" for var in self.variables])

        string += random.choice([", suffix", ""])

        return escape_string(string)

    def get_placeholder_text(self) -> str:
        return "template"


class UnknownPageNumber(IntegerStrategy):
    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> int:
        num = await super().parse(stream, argument, context)
        if num < 1:
            raise ParseError(f"{num} is out of range 1~..")

        return num - 1

    def example(self) -> str:
        return str(random.randint(1, 10))

    def get_placeholder_text(self) -> str:
        return "page"
