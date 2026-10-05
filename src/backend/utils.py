import re
from collections.abc import Callable
from datetime import datetime

import expr_dice_roller as dice

from .data_reader import DataReader
from ..service import Attachment, File, Embed


def format_date(dt: datetime):
    return f"<t:{int(dt.timestamp())}:d>"

    # day = dt.day
    # if 4 <= day <= 20 or 24 <= day <= 30:
    #     suffix = "th"
    # else:
    #     suffix = ["st", "nd", "rd"][day % 10 - 1]

    # return dt.strftime(f"%b {day}{suffix} %Y")


valid_url = re.compile(r"https?://(www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_+.~#?&/=]*)")
def is_valid_url(string: str) -> bool:
    return bool(valid_url.fullmatch(string))


async def convert_attachments(message_attachments: list[Attachment]) -> list[File]:
    parsed_attachments = []
    for attachment in message_attachments:
        parsed_attachments.append(File(
            attachment.filename,
            "",
            await attachment.read()
        ))
    return parsed_attachments

def normalize_emojis(text: str) -> str:
    for key, emoji in DataReader.instance["emojis.json"]["forward_map"].items():
        text = text.replace(":" + key + ":", emoji)
    return text

def roll_dice(string: str, get_global_environment, set_global_environment) -> tuple[str, Embed]:
    try:
        rep = dice.format_expression(string)[:100]
        try:
            res = dice.evaluate(string, get_global_environment(), True)
            set_global_environment(res.environment)
            if res.value is None:
                embed = Embed(rep, f"{res.representation}", "dice roll")
                ret = "no value"
            else:
                embed = Embed(rep, f"`{res.representation[:1000]}` = {res.value:g}", "dice roll")
                ret = f"{res.value:g}"
        except ValueError as e:
            embed = Embed(rep, f"Error: {e.args[0]}", "dice roll")
            ret = "error"
    except ValueError as e:
        embed = Embed(string[:100], f"Error: {e.args[0]}", "dice roll")
        ret = "error"
    return ret, embed

def quote(text: str) -> str:
    return text and "\n".join(("> " + line) for line in text.split("\n"))


def list_to_dict[K, T](lst: list[T], criteria: Callable[[T], K]) -> dict[K, T]:
    dct: dict[K, T] = {}
    for item in lst:
        dct[criteria(item)] = item
    return dct


type DelimitedStringAcceptable = str | DelimitedString | None

class DelimitedString:
    def __init__(self, delimiter: str, *parts: DelimitedStringAcceptable):
        self.parts: list[str] = [str(part) for part in parts if part is not None]
        self.delimiter = delimiter

    def __add__(self, other: DelimitedStringAcceptable) -> DelimitedString:
        return DelimitedString(self.delimiter, *(self.parts + [str(other)]))

    def __iadd__(self, other: DelimitedStringAcceptable) -> DelimitedString:
        if other is None:
            return self

        self.parts.append(str(other))
        return self

    def __str__(self) -> str:
        return self.delimiter.join(self.parts)
