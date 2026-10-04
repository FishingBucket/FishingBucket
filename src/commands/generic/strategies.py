import random
from datetime import timedelta
from typing import Any, Literal as Lit

import humanfriendly

from .data import Strategy, CharacterStream, ParseError, SyntaxParseError, ParsingArgument, Strategible, Argument
from .misc import lorem_ipsum, escape_string
from ...backend.utils import is_valid_url
from ...service import Context, Role, Channel, User


def strategize(strategy: Strategible) -> Strategy:
    if isinstance(strategy, Strategy): return strategy
    elif isinstance(strategy, range): return RangeStrategy(strategy)
    elif strategy == int: return IntegerStrategy()
    elif strategy == float: return FloatStrategy()
    elif strategy == str: return StringStrategy()
    elif strategy == bool: return BooleanStrategy()
    elif strategy == hex: return HexadecimalStrategy()
    elif strategy == timedelta: return TimeDeltaStrategy()
    elif strategy == User: return UserStrategy()
    elif strategy == Channel: return ChannelStrategy()
    elif strategy == Role: return RoleStrategy()
    raise NotImplementedError # should be unreachable


class RangeStrategy(Strategy):
    def __init__(self, r: range):
        self.range = r

    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> int:
        num = await IntegerStrategy().parse(stream, argument, context)
        if num in self.range:
            return num
        raise ParseError(f"{num} is out of range {self.get_placeholder_text()}")

    def example(self) -> str:
        return f"{random.randrange(self.range.start, self.range.stop, self.range.step):g}"

    def get_placeholder_text(self) -> str:
        return f"{self.range.start}~{self.range.stop - self.range.step}" + (f":{self.range.step}" if self.range.step != 1 else "")


class IntegerStrategy(Strategy):
    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> int:
        num = stream.expect("1234567890-")
        radix = 10
        alphabet = "1234567890"
        if num == "0" and stream.peek() in "xbo":
            radix, alphabet = {
                "x": (16, "1234567890abcdefABCDEF"),
                "b": (2, "01"),
                "o": (8, "01234567")
            }[stream.consume()]
            num = ""

        while stream.peek() in alphabet + "_":
            num += stream.consume()
        num = num.replace("_", "")
        try:
            return int(num, radix)
        except ValueError:
            raise SyntaxParseError("cannot parse integer")

    def example(self) -> str:
        return str(random.randint(-100, 100))

    def get_placeholder_text(self) -> str:
        return "integer"


class HexadecimalStrategy(Strategy):
    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> int:
        stream.expect(*"0x")
        alphabet = "1234567890abcdef"
        num = ""
        while stream.peek() in alphabet + "_":
            num += stream.consume()
        num = num.replace("_", "")
        try:
            return int(num, 16)
        except ValueError:
            raise SyntaxParseError("cannot parse hexadecimal")

    def example(self) -> str:
        return hex(random.randint(0, 65535))

    def get_placeholder_text(self) -> str:
        return "hexadecimal"


class FloatStrategy(Strategy):
    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> float:
        num = stream.expect("1234567890.-")
        while stream.peek() in "1234567890._":
            c = stream.consume()
            if c != "_":
                num += c

        try:
            return float(num)
        except ValueError:
            raise SyntaxParseError("cannot parse float")

    def example(self) -> str:
        return str(random.random() * 200 - 100)

    def get_placeholder_text(self) -> str:
        return "float"


class StringStrategy(Strategy):
    def __init__(self, length: Lit["MINI"] | Lit["SHORT"] | Lit["MEDIUM"] | Lit["LONG"] = "SHORT"):
        self.length = length

    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> str:
        quote: None | str = None
        if stream.peek() in "'\"":
            quote = stream.consume()

        if quote is None and argument.position_end == 0:
            d = stream.data[stream.pos:]
            stream.pos = len(stream.data)
            return d

        s = ""
        while True:
            c = stream.peek()
            if c == "\\":
                stream.consume()
                s += stream.consume()
            elif quote is None and c in (" ", "\0"):
                return s
            elif c == quote:
                stream.consume()
                return s
            elif c == "\0":
                raise SyntaxParseError("unterminated string")
            else:
                s += stream.consume()

    def example(self) -> str:
        return escape_string(lorem_ipsum(self.length)())

    def get_placeholder_text(self) -> str:
        return "string"


class WordStrategy(Strategy):
    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> str:
        s = ""
        while True:
            c = stream.peek()
            if c == "\\":
                stream.consume()
                s += stream.consume()
            elif c in (" ", "\0"):
                return s
            else:
                s += stream.consume()

    def example(self) -> str:
        return lorem_ipsum("MINI")()

    def get_placeholder_text(self) -> str:
        return "word"


class BooleanStrategy(Strategy):
    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> bool:
        s = await WordStrategy().parse(stream, argument, context)
        if s.lower() in ("yes", "yea", "yeah", "yep", "yuh", "1", "on", "affirm", "affirmative", "true", "t", "y"):
            return True
        elif s.lower() in ("no", "not", "nuh", "0", "off", "deny", "neg", "negative", "negate", "false", "f", "n"):
            return False
        raise SyntaxParseError(f"cannot convert {s!r} to boolean")

    def example(self) -> str:
        return random.choice(["true", "false"])

    def get_placeholder_text(self) -> str:
        return "boolean"


class TimeDeltaStrategy(Strategy):
    def parse_section(self, section: str) -> timedelta:
        if ":" in section:
            sections = section.split(":")
            values = [float(sec.strip()) for sec in sections]

            def get_v(index: int) -> float:
                if len(values) > index:
                    return values[- index - 1]
                return 0

            return timedelta(
                seconds=get_v(0),
                minutes=get_v(1),
                hours=get_v(2),
                days=get_v(3)
            )

        else:
            return timedelta(seconds=humanfriendly.parse_timespan(section))

    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> timedelta:
        string = await StringStrategy().parse(stream, argument, context)
        try:
            if "," in string or "and" in string:
                deltas = timedelta(seconds=0)
                for section in string.replace("and", ",").split(","):
                    if section.strip():
                        deltas += self.parse_section(section.strip())
                return deltas
            return self.parse_section(string)
        except humanfriendly.InvalidTimespan:
            raise SyntaxParseError(f"cannot parse timestamp")

    def example(self) -> str:
        td = timedelta(seconds=random.randint(10, 3600 * 24 * 14))
        return escape_string(random.choice([
            humanfriendly.format_timespan(td),
            str(td)
        ]))

    def get_placeholder_text(self) -> str:
        return "duration"


class Literal(Strategy):
    def __init__(self, literal: Any, placeholder_text: str = "", strat: Strategible = None):
        self.literal = literal
        self.placeholder_text = placeholder_text or repr(str(literal))
        self.strat = strategize(strat or type(self.literal))

    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> Any:
        parse = await self.strat.parse(stream, argument, context)
        if parse != self.literal:
            raise SyntaxParseError(f"expected literal {self.literal!r}")
        return parse

    def example(self) -> str:
        return self.literal

    def get_placeholder_text(self) -> str:
        return self.placeholder_text


class URLStrategy(Strategy):
    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> str:
        s = await StringStrategy().parse(stream, argument, context)
        if is_valid_url(s):
            return s
        raise SyntaxParseError(f"{s!r} is not a valid URL.")

    def example(self) -> str:
        return "https://example.com"

    def get_placeholder_text(self) -> str:
        return "url"


class OneOf(Strategy):
    def __init__(self, *strats: Strategible, fatal: bool = False):
        self.strats = [strategize(strat) for strat in strats]
        self.fatal = fatal

    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> Any:
        start = stream.pos
        for strat in self.strats:
            try:
                return await strat.parse(stream, argument, context)
            except SyntaxParseError:
                stream.pos = start

        if self.fatal:
            raise SyntaxParseError(f"none of {len(self.strats)} alternatives matched")
        raise ParseError(f"none of {len(self.strats)} alternatives matched")

    def example(self) -> str:
        return random.choice(self.strats).example()

    def get_placeholder_text(self) -> str:
        return " OR ".join(strat.get_placeholder_text() for strat in self.strats)


class OptionList(Strategy):
    def __init__(self, options_name: str | None, options: dict[str, list[str]] | list[str], fatal = False):
        if isinstance(options, dict):
            self.options = {
                k.lower(): [i.lower() for i in v] for k, v in options.items()
            }
        else:
            self.options = {
                k.lower(): [] for k in options
            }

        self.options_name = options_name
        self.fatal = fatal

    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> str:
        s = await StringStrategy().parse(stream, argument, context)
        for k, v in self.options.items():
            if s.lower() in [k] + v:
                return k
        raise [ParseError, SyntaxParseError][int(self.fatal)](f"none of {len(self.options)} options matched")

    def example(self) -> str:
        return random.choice([*self.options.keys()])

    def get_placeholder_text(self) -> str:
        return self.options_name or " OR ".join(Literal(option).get_placeholder_text() for option in self.options.keys())


class Optional(Strategy):
    accept_end_of_stream = True
    bracket_start = "["
    bracket_end = "]"
    expect_start_another = True

    def __init__(self, strat: Strategible, default: Any):
        self.strat = strategize(strat)
        self.default = default

    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> Any:
        start = stream.pos
        if not stream.end:
            try:
                t = await self.strat.parse(stream, argument, context)
                self.expect_start_another = False # hack asf
                return t
            except SyntaxParseError:
                stream.pos = start
                return self.default
        else:
            return self.default

    def example(self) -> str:
        return random.choice([self.strat.example(), ""])

    def get_placeholder_text(self) -> str:
        return self.strat.get_placeholder_text()


class List(Strategy):
    accept_end_of_stream = True

    def __init__(self, datatype: Strategible, minimum: int = 0, fatal: bool = False):
        self.datatype = strategize(datatype)
        self.minimum = minimum
        self.fatal = fatal

    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> list[Any]:
        l = []
        before_whitespace = stream.pos
        while not stream.end:
            start = stream.pos
            try:
                l.append(await self.datatype.parse(stream, argument, context))
            except SyntaxParseError:
                stream.pos = start
                break

            before_whitespace = stream.pos
            stream.expect_argument_end()

        stream.pos = before_whitespace

        if len(l) < self.minimum:
            if self.fatal:
                raise SyntaxParseError(f"expected at least {self.minimum} elements, got {len(l)}")

            raise ParseError(f"expected at least {self.minimum} elements, got {len(l)}")

        return l

    def example(self) -> str:
        return " ".join(self.datatype.example() for _ in range(random.randint(self.minimum, 3)))

    def get_placeholder_text(self) -> str:
        return self.datatype.get_placeholder_text() + ("(s)" if self.minimum == 0 else "s")


class Sequence(Strategy):
    def __init__(self, *arguments: Argument, discriminated_fields: int = 0):
        self.arguments = arguments
        self.discriminated_fields = discriminated_fields

    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> list[Any]:
        results = []
        for idx, arg in enumerate(self.arguments):
            strat = strategize(arg.strategy)

            try:
                if not strat.accept_end_of_stream and stream.end:
                    raise ParseError(f"unexpected end of arguments while trying to parse sub-argument #{idx + 1} `{arg.name}`")

                try:
                    results.append(await strat.parse(stream, ParsingArgument(arg, idx, len(self.arguments) - idx - 1), context))
                except ParseError as e:
                    raise ParseError(f"error parsing sub-argument #{idx + 1} `{arg.name}`: {e.message}")

                if not strat.expect_start_another:
                    try:
                        stream.expect_argument_end()
                    except ParseError as e:
                        raise ParseError(f"error transitioning to sub-argument #{idx + 1}: {e.message}")
            except ParseError as e:
                if idx < self.discriminated_fields:
                    raise SyntaxParseError(e.message)
                raise e

        return results


    def example(self) -> str:
        parts = []

        for argument in self.arguments:
            parts.append(argument.get_example())

        return " ".join(parts).replace("  ", " ").strip()

    def get_placeholder_text(self) -> str:
        parts = []

        for argument in self.arguments:
            strat = strategize(argument.strategy)
            placeholder = strat.get_placeholder_text().replace("  ", " ")
            part = f"{strat.bracket_start}{argument.name}: {placeholder}{strat.bracket_end}"
            parts.append(part)

        return "( " + " ".join(parts).strip() + " )"


class _UseSnowflakeStrategy(Strategy):
    prefix: str

    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> int:
        stream.expect("<")
        stream.expect(*self.prefix)
        id_ = await IntegerStrategy().parse(stream, argument, context)
        stream.expect(">")
        return id_

    def example(self) -> str:
        return f"<{self.prefix}...>"

    def get_placeholder_text(self) -> str:
        return "snowflake"


class UserStrategy(_UseSnowflakeStrategy):
    prefix = "@"

    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> User:
        try:
            id_ = await super().parse(stream, argument, context)
            user = await context.get_user(id_)
            if user is not None:
                return user

            raise ParseError(f"cannot locate user ID {id_}")

        except SyntaxParseError:
            raise SyntaxParseError("could not parse user mention")

    def example(self) -> str:
        return "@user"

    def get_placeholder_text(self) -> str:
        return "@user"


class ChannelStrategy(_UseSnowflakeStrategy):
    prefix = "#"

    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> Channel:
        try:
            id_ = await super().parse(stream, argument, context)
            channel = await context.get_channel(id_)
            if channel is not None:
                return channel

            raise ParseError(f"cannot locate channel ID {id_}")

        except SyntaxParseError:
            raise SyntaxParseError("could not parse channel mention")

    def example(self) -> str:
        return "#channel"

    def get_placeholder_text(self) -> str:
        return "#channel"


class RoleStrategy(_UseSnowflakeStrategy):
    prefix = "@&"

    async def parse(self, stream: CharacterStream, argument: ParsingArgument, context: Context) -> Role:
        try:
            id_ = await super().parse(stream, argument, context)
            role = await context.guild.get_role(id_)
            if role is not None:
                return role

            raise ParseError(f"cannot locate role ID {id_}")

        except SyntaxParseError:
            raise SyntaxParseError("could not parse role mention")

    def example(self) -> str:
        return "@role"

    def get_placeholder_text(self) -> str:
        return "@role"