from typing import Callable, Any, TYPE_CHECKING
import celpy
from dataclasses import dataclass

import re

from pydantic import BaseModel

from .cache import TTLCache
from .config import Config
from .logging import start_log

if TYPE_CHECKING:
    from ..service import Context

print, error = start_log("template", "-template")


@dataclass
class TemplatePart:
    content: str

@dataclass
class MatchedResult:
    match: bool
    content: str = ""
    new_index: int = 0

class TextPart(TemplatePart): pass
class ExprPart(TemplatePart): pass

class Cache:
    ParseCache = TTLCache(1024, 3600)
    ComputeCache = TTLCache(1024, 3600)

functions: dict[str, Callable] = {
    "size": len,
    "repr": repr,
    "str": str,
    "upper": str.upper,
    "lower": str.lower,
    "replace": str.replace,
    "contains": str.__contains__,
    "slice": lambda this, a, b: this[a:b],
    "startswith": str.startswith,
    "endswith": str.endswith,
    "split": str.split,
    "trim": str.strip,
    "strip": str.strip,
    "find": str.find,
    "_&&_": lambda a, b: a and b,
    "_||_": lambda a, b: a or b,
    "matches": lambda this, exp: re.fullmatch(exp, this, re.MULTILINE),
    "matches_insensitive": lambda this, exp: re.fullmatch(exp, this, re.IGNORECASE | re.MULTILINE)
}

class Template:
    def __init__(self, parts: list[TemplatePart], errors: list[str] = None):
        self.parts = parts
        self.errors: list[str] = errors or []


    @property
    def string(self) -> str:
        res = ""
        for part in self.parts:
            if isinstance(part, TextPart):
                res += part.content.replace("{", "\\{").replace("}", "\\}")
            else:
                res += "{" + part.content + "}"
        return res


    @classmethod
    def from_string(cls, string: str) -> Template:
        if res := Cache.ParseCache.get(string): return res
        comp_env = celpy.Environment()
        parts = []
        current_content = ""
        braces = 0
        errors = []
        string_mode = False
        prev = "\0"
        escaped = 0
        for char in string:
            if char == "\\" and escaped == 0:
                escaped = 2

            if braces != 0 and not string_mode and char in '"\'':
                string_mode = char
            elif braces != 0 and string_mode == char and prev != "\\":
                string_mode = False

            if not string_mode:
                if char == "{" and escaped == 0:
                    braces += 1
                    if braces == 1:
                        parts.append(TextPart(current_content))
                        current_content = ""
                        continue
                elif char == "}" and escaped == 0:
                    braces -= 1
                    if braces == 0:
                        c = ExprPart
                        if current_content:
                            try:
                                comp_env.compile(current_content)
                            except celpy.CELParseError as e:
                                c = TextPart
                                errors.append(f"Cannot parse part {current_content!r} due to {e.args[0]!r}.")
                        parts.append(c(current_content))
                        current_content = ""
                        continue
            if escaped != 2:
                current_content += char
            prev = char
            if escaped > 0:
                escaped -= 1

        if braces != 0:
            errors.append("Unclosed open brace.")

        parts.append(TextPart(current_content))
        simplified: list[TemplatePart] = []
        for part in parts:
            if isinstance(part, TextPart):
                if part.content:
                    part.content = part.content.replace("\\\\", "\\").replace("\\{", "{").replace("\\}", "}")
                    previous_part = simplified[-1] if len(simplified) != 0 else None
                    if isinstance(previous_part, TextPart):
                        simplified[-1].content += part.content
                    else:
                        simplified.append(part)
            else:
                simplified.append(part)

        obj = cls(simplified, errors)
        Cache.ParseCache.set(string, obj)
        return obj

    def get_expr_count(self) -> int:
        return len([part for part in self.parts if isinstance(part, ExprPart)])

    @staticmethod
    def evaluate_expr(expression: str, variables: dict, extra_functions: dict[str, Callable] = None) -> tuple[bool, str]:
        environment = celpy.Environment()
        ast = environment.compile(expression)
        try:
            program = environment.program(ast, functions=functions | (extra_functions or {}))
            result = program.evaluate(variables)
            if isinstance(result, str):
                return True, result
            return False, ""
        except Exception as e:
            print(f"{expression=}, {variables=}")
            error(e)
            return False, ""

    def _match(self, part_index: int, string: str, string_index: int, previous_match: str, parts: list[TemplatePart]) -> MatchedResult:
        if part_index >= len(parts):
            return MatchedResult(False)

        part = parts[part_index]
        cropped = string[string_index:]
        if isinstance(part, TextPart):
            if cropped.startswith(part.content):
                return MatchedResult(True, part.content, string_index + len(part.content))
            return MatchedResult(False)

        if not (len(parts) >= part_index + 1 and isinstance(part, ExprPart)):
            inside = ""
            new_string_index = string_index
            for new_string_index in range(string_index, len(string)):
                matched_result = self._match(part_index + 1, string, new_string_index, "", parts)
                if matched_result.match:
                    break
                inside += string[new_string_index]
        else:
            inside = cropped
            new_string_index = string_index

        matched, content = True, inside
        if part.content:
            def pre(this: str) -> str:
                return previous_match + this

            matched, content = self.evaluate_expr(part.content, {"text": inside}, {"pre": pre})

        return MatchedResult(matched, content, new_string_index)

    def match(self, string: str) -> MatchedResult:
        parts = self.parts[:]

        if len(parts) >= 1 and isinstance(parts[0], TextPart):
            if string.startswith(parts[0].content):
                string = string[len(parts[0].content):]
                parts.pop(0)
            else:
                return MatchedResult(False)
        if len(parts) >= 1 and isinstance(parts[-1], TextPart):
            if string.endswith(parts[-1].content):
                string = string[:-len(parts[-1].content)]
                parts.pop(-1)
            else:
                return MatchedResult(False)

        results = ""
        string_index = 0
        previous_match = ""
        for part_index in range(len(parts)):
            res = self._match(part_index, string, string_index, previous_match, parts)
            if res.match:
                previous_match = res.content
                if isinstance(parts[part_index], ExprPart):
                    results += res.content
                string_index = res.new_index
            else:
                return MatchedResult(False)
        return MatchedResult(True, results, 0)

    def make_value(self, d: Any) -> Any:
        if isinstance(d, (int, float, bool, str)):
            return d
        elif d is None: return d
        elif isinstance(d, (tuple, list)):
            return [self.make_value(v) for v in d]
        elif isinstance(d, BaseModel):
            return self.make_value(d.model_dump(mode="json"))
        elif isinstance(d, dict):
            return {k: self.make_value(v) for k, v in d.items()}
        raise Exception(f"unknown data type {d.__class__.__name__}")

    def map_variables(self, variables: dict) -> dict:
        parsed = {}
        for k, v in variables.items():
            if isinstance(v, (dict, tuple, list)):
                parsed[k] = celpy.json_to_cel(self.make_value(v))
            elif isinstance(v, (int, float, bool, str)):
                parsed[k] = v
            elif v is None:
                parsed[k] = v
            elif isinstance(v, BaseModel):
                parsed[k] = celpy.json_to_cel(v.model_dump(mode="json"))
            else:
                parsed[k] = celpy.json_to_cel(self.make_value({k_: v_ for k_, v_ in v.__dict__.items() if not (k_.startswith("_") or k_.endswith("_"))}))
        return parsed

    def compute(self, variables: dict, default: str) -> str:
        if res := Cache.ComputeCache.get((self, variables, default)): return res
        string = ""
        vars = self.map_variables(variables)
        for part in self.parts:
            if isinstance(part, TextPart):
                string += part.content
            else:
                if part.content:
                    res = self.evaluate_expr(part.content, vars)
                    if res[0]:
                        string += res[1]
                    else:
                        string += default
                else:
                    string += default

        Cache.ComputeCache.set((self, variables, default), string)
        return string


    @staticmethod
    def get_default_metatext_variables(context: Context) -> dict:
        return {
            "config": Config.instance,
            "prefix": Config.prefix(context.platform),
            "name": Config.name(),
            "context": {
                "platform": context.platform.name
            }
        }
