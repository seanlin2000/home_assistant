"""The checks every tool call passes before it runs, and the cleaning every result gets before the model reads it (design doc v2/12 sections
3.2 to 3.5 and 3.7). The loop wraps its tool box in a GuardedToolBox for each exchange, so the benchmark measures exactly what the harness runs.

Before a call:
- the tool must be listed in config/tools.toml;
- its arguments must match the tool's schema, and no string may exceed the length limit;
- `fetch_page` may only read an address from this exchange's results or the user's own words;
- a read-public call may not carry a private term from memory the user did not say (the egress guard).
A refused call never reaches the tool server; the model reads one sentence saying why.

After a call, hidden characters are stripped, and the text of a tool written by strangers is wrapped in an <untrusted> block and marks the exchange.
"""

import re
import tomllib
from enum import StrEnum
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict

from assistant_core.egress_guard import leaked_terms
from assistant_core.models import Message, Role, ToolCall, ToolSpec
from assistant_core.tools import ToolBox

TOOLS_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "tools.toml"
FETCH_PAGE = "fetch_page"
URL = re.compile(r"https?://[^\s<>\"')\]]+")
# Zero-width characters, bidirectional controls, and Unicode tag characters: invisible on screen, read by the model.
HIDDEN_CHARACTERS = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿\U000e0000-\U000e007f]")
UNTRUSTED_TAG = re.compile(r"</?\s*untrusted", re.IGNORECASE)

UNLISTED_REFUSAL = "Refused: {name} is not a tool this assistant may use."
ARGUMENTS_REFUSAL = "Refused: the arguments for {name} are not valid ({reason}). Call it again with valid arguments, or answer without it."
PROVENANCE_REFUSAL = "Refused: I can only read an address that came up in this conversation's search results or that you said yourself."
EGRESS_REFUSAL = "Refused: the request carried private details from memory."


class Tier(StrEnum):
    LOCAL = "local"
    READ_PUBLIC = "read_public"
    READ_PRIVATE = "read_private"
    ACT = "act"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolRule(StrictModel):
    tier: Tier
    marks_untrusted: bool


class Limits(StrictModel):
    max_string_argument_chars: int


class ToolTable(StrictModel):
    limits: Limits
    tools: dict[str, ToolRule]


class ToolRefused(Exception):
    """A call the guards stopped before it ran. Its message is what the model reads in place of a result."""


@cache
def load_tool_table(path: Path = TOOLS_CONFIG_PATH) -> ToolTable:
    return ToolTable.model_validate(tomllib.loads(path.read_text()))


class GuardedToolBox:
    def __init__(self, inner: ToolBox, table: ToolTable, conversation: list[Message], private_terms: frozenset[str] = frozenset()) -> None:
        self._inner = inner
        self._table = table
        self._user_words = " ".join(message.content for message in conversation if message.role == Role.USER)
        self._question = next((message.content for message in reversed(conversation) if message.role == Role.USER), "")
        self._private_terms = private_terms
        self._specs: dict[str, ToolSpec] = {}
        self._addresses_seen: set[str] = set()
        self.untrusted = False

    async def list_tools(self) -> list[ToolSpec]:
        specs = [spec for spec in await self._inner.list_tools() if spec.name in self._table.tools]
        self._specs = {spec.name: spec for spec in specs}
        return specs

    async def call(self, call: ToolCall) -> str:
        self._refuse_if_unsafe(call)
        rule = self._table.tools[call.name]
        result = HIDDEN_CHARACTERS.sub("", await self._inner.call(call))
        self._addresses_seen.update(URL.findall(result))
        if not rule.marks_untrusted:
            return result
        self.untrusted = True
        return as_untrusted_block(call.name, result)

    def _refuse_if_unsafe(self, call: ToolCall) -> None:
        if call.name not in self._table.tools or call.name not in self._specs:
            raise ToolRefused(UNLISTED_REFUSAL.format(name=call.name))
        problem = argument_problem(self._specs[call.name], call.arguments, self._table.limits.max_string_argument_chars)
        if problem:
            raise ToolRefused(ARGUMENTS_REFUSAL.format(name=call.name, reason=problem))
        if call.name == FETCH_PAGE and not self._address_has_provenance(str(call.arguments.get("url", ""))):
            raise ToolRefused(PROVENANCE_REFUSAL)
        if self._table.tools[call.name].tier == Tier.READ_PUBLIC and leaked_terms(call.arguments, self._private_terms, self._question):
            raise ToolRefused(EGRESS_REFUSAL)

    def _address_has_provenance(self, url: str) -> bool:
        """The address came back in a result this exchange, or the user said it (as written, or by its host name)."""
        address = url.strip().rstrip("/")
        if any(seen.rstrip("/.,;") == address for seen in self._addresses_seen):
            return True
        host = re.sub(r"^https?://(www\.)?", "", address).split("/")[0].lower()
        return bool(host) and host in self._user_words.lower()


def argument_problem(spec: ToolSpec, arguments: dict, max_string_chars: int) -> str | None:
    errors = sorted(Draft202012Validator(spec.input_schema).iter_errors(arguments), key=lambda error: error.path)
    if errors:
        return errors[0].message
    too_long = [name for name, value in arguments.items() if isinstance(value, str) and len(value) > max_string_chars]
    return f"{too_long[0]} is longer than {max_string_chars} characters" if too_long else None


def as_untrusted_block(source: str, text: str) -> str:
    """Wrap a stranger's text as data. Any untrusted tag inside it is defused first, so a page cannot close the block and speak as the system."""
    return f'<untrusted source="{source}">\n{UNTRUSTED_TAG.sub("(tag removed)", text)}\n</untrusted>'
