import re
import textwrap
from dataclasses import replace
from datetime import datetime

import expr_dice_roller as dice
import json5
from pydantic import BaseModel, field_validator, ValidationError

from ..backend.database.database import get_db
from ..backend.database.guild import GuildPreference
from ..backend.database.permission import GuildPermissions
from ..backend.database.user import UserID
from ..backend.dice_environments import global_functions
from ..backend.utils import roll_dice
from ..service.common import RawEmbed, Embed, Message


def is_replace(content: str) -> tuple[re.Pattern, str, bool] | None:
    if not content.startswith("\\s/"):
        return None
    content = content[len("\\s/"):]
    replacer = ""
    sub = ""
    global_ = False
    if content.endswith("/g"):
        global_ = True
        content = content[:-len("/g")]
    parsing = 0
    escape = False
    for i, char in enumerate(content):
        if not escape and char == "/" and parsing == 0:
            parsing = 1
            continue
        if char == "\\" and i < len(content) - 1 and content[i + 1] == "/":
            escape = True
            continue
        if parsing == 0:
            replacer += char
        elif parsing == 1:
            sub += char
    try:
        return re.compile(replacer, re.MULTILINE), sub, global_
    except re.PatternError:
        return None


def do_replace(replace: tuple[re.Pattern, str, bool], old_content: str) -> str:
    return replace[0].sub(replace[1], old_content, int(not replace[2]))


BLOCK_CONTENT_RE = re.compile(r"{{(.+?)}}(?!})", re.S)

class EmbedAuthor(BaseModel):
    name: str
    url: str | None = None
    icon_url: str | None = None

class EmbedImage(BaseModel):
    url: str
    description: str | None = None

class EmbedFooter(BaseModel):
    text: str
    icon_url: str | None = None

class EmbedField(BaseModel):
    name: str
    value: str
    inline: bool | None = None

class SingularEmbed(BaseModel):
    description: str
    url: str | None = None
    title: str | None = None
    color: int | None = None
    timestamp: datetime | None = None
    author: EmbedAuthor | str | None = None
    image: EmbedImage | str | None = None
    thumbnail: EmbedImage | str | None = None
    footer: EmbedFooter | str | None = None
    fields: list[EmbedField] | None = None

    @field_validator("author", mode="before")
    @classmethod
    def norm_author(cls, v: EmbedAuthor | str | None) -> EmbedAuthor | None:
        if isinstance(v, str):
            return EmbedAuthor(name=v)
        return v

    @field_validator("image", "thumbnail", mode="before")
    @classmethod
    def norm_image(cls, v: EmbedImage | str | None) -> EmbedImage | None:
        if isinstance(v, str):
            return EmbedImage(url=v)
        return v

    @field_validator("footer", mode="before")
    @classmethod
    def norm_footer(cls, v: EmbedFooter | str | None) -> EmbedFooter | None:
        if isinstance(v, str):
            return EmbedFooter(text=v)
        return v


def normalize_embed(embed: SingularEmbed) -> RawEmbed:
    return RawEmbed(embed.model_dump(exclude_defaults=True, mode="python"))

async def modify_message(user: UserID, guild_preferences: GuildPreference, permissions: GuildPermissions, message: str) -> tuple[str, list[Embed]]:
    embed_list: list[Embed] = []
    evaluator = dice.Evaluator()
    user_preferences = await get_db().user_settings.get_user_preference(user)
    fns = user_preferences.dice_functions
    if fns:
        env = dice.Environment.deserialize(evaluator, fns)
    else:
        env = dice.Environment()
    guild_fns = guild_preferences.dice_functions
    if guild_fns:
        guild_env = dice.Environment.deserialize(evaluator, guild_fns)
    else:
        guild_env = dice.Environment()

    global_environment = global_functions()
    global_environment.mutable = env
    global_environment.immutable = guild_env

    def construct(match: re.Match) -> str:
        inner = match.group(1).strip()
        if inner.startswith("```") and inner.endswith("```"):
            inner = inner[3:-3]
        inner = textwrap.dedent(inner)

        do_embed = True
        j: dict | None = None
        parse_embed_error: ValidationError | None = None

        try:
            j = json5.loads("{" + inner + "}")
        except ValueError:
            do_embed = False

        if do_embed and GuildPermissions.EMBED_BLOCKS in permissions:
            assert isinstance(j, dict)
            try:
                if "embeds" in j:
                    effective_embeds_list = [normalize_embed(SingularEmbed(**e)) for e in j["embeds"]]
                elif "embed" in j:
                    effective_embeds_list = [normalize_embed(SingularEmbed(**j["embed"]))]
                else:
                    raise ValidationError("embed blocks must either have an `embed` field or an `embeds` field.")

                embed_list.extend(effective_embeds_list)
                return ""
            except ValueError as e:
                parse_embed_error = e

        def get_global_environment(): return global_environment
        def set_global_environment(ge):
            nonlocal global_environment
            global_environment = ge

        if not do_embed:
            if GuildPermissions.DICE in permissions:
                ret, embed = roll_dice(inner, get_global_environment, set_global_environment)
                embed_list.append(embed)
                return f"`{ret}`"
            return "{{" + inner + "}}"
        else:
            embed_list.append(Embed(
                "Error parsing embed block",
                "```\n" + str(parse_embed_error) + "\n```"
            ))
            return ""

    result = BLOCK_CONTENT_RE.sub(construct, message), embed_list
    serialized = env.serialize()
    if serialized != fns:
        await get_db().user_settings.set_user_preference(user, replace(user_preferences, dice_functions=serialized))
    return result


valid_dice_roll_description_regex = re.compile(r"`.+` = (\d+(?:\.\d*)?)")

def try_reverse_engineer(message: Message) -> str:
    i = 0
    replaces: list[tuple[slice, str]] = []
    for embed in message.raw_embeds:
        if embed.data.get("footer", {}).get("text") == "dice roll":
            description = embed.data["description"]
            if description.startswith("Error:"):
                start_index = message.content.find("`error`", i)
                i = start_index + len("`error`")
            elif match := valid_dice_roll_description_regex.match(description):
                result = match.group(1)
                start_index = message.content.find(f"`{result}`", i)
                i = start_index + len(f"`{result}`")
            else:
                start_index = message.content.find("`no value`", i)
                i = start_index + len("`no value`")

            replaces.append((slice(start_index, i), "{{" + embed.data["title"] + "}}"))
        else:
            replaces.append((slice(i, i), "{{embed: " + json5.dumps(normalize_embed(SingularEmbed(**embed.data)).data, indent=4) + "}}"))

    out = message.content
    for slicing, replace in replaces[::-1]:
        out = out[:slicing.start] + replace + out[slicing.stop:]

    return out