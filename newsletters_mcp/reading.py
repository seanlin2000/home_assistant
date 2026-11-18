"""One part of a newsletter read aloud (design doc v2/14 section 3.7): about three minutes of an issue's text, cut at a paragraph break, rewritten
for the ear, between an opening line and a closing line that says what comes next. The read cursor remembers the part read last, so "keep reading"
works after the conversation has started over."""

import re
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from newsletters_mcp.conversion import OPENING_SECTION
from newsletters_mcp.issue import Issue
from utils.snapshot_utils import write_file_atomically
from utils.spoken_reading_utils import end_of_issue_line, next_part_line, reading_opening

READ_CURSOR_FILE = "read_cursor.json"
QUOTATION_OR_ITEM_MARK = re.compile(r"^(> |- )")
FOOTNOTE_START = re.compile(r"^\[(\d+)\] ")
FOOTNOTE_MARK = re.compile(r"\[\d+\]")
ARROWS = re.compile(r"[←-⇿]\s?")  # market arrows such as "↘ Nvidia" are read out as "south east arrow"
TABLE_CELL_SEPARATOR = " | "


class PartPosition(BaseModel):
    """Parts are counted from the section the reading started at, so the same start always cuts the same parts."""

    start_section_index: int
    part_index: int


class ReadCursor(BaseModel):
    """The part read aloud last: the issue by its day and Message-ID, and where in it."""

    day: date
    message_id: str
    position: PartPosition


class Passage(BaseModel):
    """One paragraph rewritten for the ear, and whether it opens its section, where the section's name is said first."""

    section_index: int
    opens_section: bool
    text: str


def spoken_title(issue: Issue, section_index: int) -> str:
    """The text before the first heading has no name of its own, so it is read under the headline."""
    section = issue.sections[section_index]
    return issue.headline if section.title == OPENING_SECTION else section.title


def issue_parts(issue: Issue, start_section_index: int, reading_words: int) -> list[list[Passage]]:
    """The issue from the start section on, in runs of about reading_words cut at paragraph breaks. A short section shares its part with the next,
    so a two-line teaser is not a part of its own; a paragraph longer than reading_words is a part on its own."""
    parts: list[list[Passage]] = [[]]
    words_in_part = 0
    for passage in passages_from(issue, start_section_index):
        passage_words = len(passage.text.split())
        if parts[-1] and words_in_part + passage_words > reading_words:
            parts.append([])
            words_in_part = 0
        parts[-1].append(passage)
        words_in_part += passage_words
    return parts


def passages_from(issue: Issue, start_section_index: int) -> list[Passage]:
    return [
        Passage(section_index=section_index, opens_section=paragraph_index == 0, text=spoken_paragraph(paragraph))
        for section_index in range(start_section_index, len(issue.sections))
        for paragraph_index, paragraph in enumerate(issue.sections[section_index].paragraphs)
    ]


def spoken_paragraph(paragraph: str) -> str:
    """Markdown marks dropped, footnote marks dropped, a footnote announced, and a table row read as a list of its filled cells."""
    text = QUOTATION_OR_ITEM_MARK.sub("", paragraph)
    text = FOOTNOTE_START.sub(r"Footnote \1: ", text)
    text = FOOTNOTE_MARK.sub("", text)
    text = ARROWS.sub("", text)
    if TABLE_CELL_SEPARATOR.strip() not in text:
        return text
    return ", ".join(cell.strip() for cell in text.split(TABLE_CELL_SEPARATOR.strip()) if cell.strip())


def next_position(issue: Issue, position: PartPosition, reading_words: int) -> PartPosition | None:
    if position.part_index + 1 < len(issue_parts(issue, position.start_section_index, reading_words)):
        return position.model_copy(update={"part_index": position.part_index + 1})
    return None


def reading_text(issue: Issue, position: PartPosition, reading_words: int) -> str:
    parts = issue_parts(issue, position.start_section_index, reading_words)
    part = parts[position.part_index]
    following = parts[position.part_index + 1] if position.part_index + 1 < len(parts) else None
    opening = reading_opening(issue.publication, where_it_starts(issue, part[0]))
    closing = next_part_line(where_it_starts(issue, following[0])) if following else end_of_issue_line(issue.publication)
    return "\n".join([opening, *spoken_passages(issue, part), closing])


def where_it_starts(issue: Issue, passage: Passage) -> str:
    title = spoken_title(issue, passage.section_index)
    return title if passage.opens_section else f"more of {title}"


def spoken_passages(issue: Issue, part: list[Passage]) -> list[str]:
    """The part's paragraphs, with each section that starts after the first line announced by its name; the opening line names the first."""
    lines = []
    for index, passage in enumerate(part):
        if passage.opens_section and index > 0:
            lines.append(as_sentence(spoken_title(issue, passage.section_index)))
        lines.append(passage.text)
    return lines


def as_sentence(title: str) -> str:
    return title if title.endswith((".", "?", "!")) else f"{title}."


def read_cursor(root: Path) -> ReadCursor | None:
    path = root / READ_CURSOR_FILE
    return ReadCursor.model_validate_json(path.read_text()) if path.exists() else None


def write_cursor(root: Path, cursor: ReadCursor) -> None:
    write_file_atomically(root / READ_CURSOR_FILE, cursor.model_dump_json(indent=2).encode())
