"""Turns the Markdown trafilatura extracts from a web page into the shared format of utils.passage_utils, so an ordinary page keeps the headings, table
rows, and list items that passage selection chooses between, as a Wikipedia article does.

trafilatura writes a table as "| a | b |" rows with a "|---|---|" row under the header, marks emphasis with asterisks, passes some inline tags such as
<sub> through, and keeps the "[edit]" links that wikis put after their headings. The separator rows, the outer pipes, the emphasis marks, the inline
tags, the edit links, and empty headings are dropped; each run of headings, table rows, list items, or prose lines becomes its own block, and a
paragraph's lines are joined into one.
"""

import re
from collections.abc import Callable
from itertools import groupby

from utils.passage_utils import BLOCK_SEPARATOR, CELL_SEPARATOR, HEADING_MARK, LIST_ITEM_PREFIX, is_heading

TABLE_EDGE = "|"
LIST_MARKER = re.compile(r"^(?:[-*+]|\d+[.)])\s+")
SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")
STRONG_EMPHASIS = re.compile(r"\*\*(\S(?:.*?\S)?)\*\*")
EMPHASIS = re.compile(r"(?<![*\w])\*(?=\S)([^*]*?\S)\*(?![*\w])")  # an opening mark before a word and a closing one after it, never a bullet's lone "*"
EDIT_LINK = re.compile(r"\s*\[edit\]", re.IGNORECASE)
INLINE_TAG = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*\s*/?>")


def to_passage_format(markdown: str) -> str:
    blocks = [block for chunk in markdown.split(BLOCK_SEPARATOR) for block in chunk_blocks(chunk)]
    return BLOCK_SEPARATOR.join(block for block in blocks if block)


def chunk_blocks(chunk: str) -> list[str]:
    lines = [" ".join(line.split()) for line in chunk.split("\n") if line.strip()]
    return [BLOCK_RENDERERS[kind](list(run)) for kind, run in groupby(lines, key=line_kind)]


def line_kind(line: str) -> str:
    if is_heading(line):
        return "heading"
    if line.startswith(TABLE_EDGE):
        return "table"
    return "list" if LIST_MARKER.match(line) else "prose"


def heading_blocks(lines: list[str]) -> str:
    """Each heading is a block of its own, as the shared format expects."""
    headings = (EDIT_LINK.sub("", plain_text(line)) for line in lines)
    return BLOCK_SEPARATOR.join(heading for heading in headings if heading.lstrip(HEADING_MARK).strip())


def table_block(lines: list[str]) -> str:
    rows = (table_row(line) for line in lines)
    return "\n".join(row for row in rows if row)


def table_row(line: str) -> str:
    """A separator row comes back empty; trailing empty cells are dropped, as in a Wikipedia row."""
    cells = [plain_text(cell.strip()) for cell in line.strip().strip(TABLE_EDGE).split(TABLE_EDGE)]
    if all(SEPARATOR_CELL.match(cell) or not cell for cell in cells):
        return ""
    return CELL_SEPARATOR.join(cells).rstrip(" |")


def list_block(lines: list[str]) -> str:
    return "\n".join(LIST_ITEM_PREFIX + plain_text(LIST_MARKER.sub("", line)) for line in lines)


def prose_block(lines: list[str]) -> str:
    return plain_text(" ".join(lines))


def plain_text(text: str) -> str:
    return EMPHASIS.sub(r"\1", STRONG_EMPHASIS.sub(r"\1", INLINE_TAG.sub("", text)))


BLOCK_RENDERERS: dict[str, Callable[[list[str]], str]] = {"heading": heading_blocks, "table": table_block, "list": list_block, "prose": prose_block}
