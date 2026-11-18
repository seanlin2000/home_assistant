"""The lines that open and close a part read aloud (design doc v2/14 sections 3.6 and 3.7). The newsletter tool writes them, and the harness
looks for them: a result that opens with one is spoken as it is, and a replayed reading is shortened to its opening and closing lines."""

import re

READING_OPENING = re.compile(r"^Reading [^\n]+\.$", re.MULTILINE)
READ_ALOUD_MARKER = "[read aloud]"


def reading_opening(publication: str, where_it_starts: str) -> str:
    """ "Reading Money Stuff: Oh Jensen.", or "Reading Money Stuff: more of Oh Jensen." for a part that starts inside a section."""
    return f"Reading {publication}: {where_it_starts}."


def next_part_line(where_it_starts: str) -> str:
    return f"Next is {where_it_starts}. Say continue to hear it."


def end_of_issue_line(publication: str) -> str:
    return f"That's the end of {publication}."


def is_reading(text: str) -> bool:
    """Whether the text opens with a reading's first line; a tool's failure sentence never does."""
    return READING_OPENING.match(text) is not None


def shortened_reading(text: str) -> str | None:
    """A replayed reading as its opening line, the marker, and its closing line, or None when the text holds no reading."""
    opening = READING_OPENING.search(text)
    if opening is None:
        return None
    closing = text.rstrip().rsplit("\n", 1)[-1].strip()
    before = text[: opening.start()].strip()
    return "\n".join(line for line in (before, opening.group(0), READ_ALOUD_MARKER, closing) if line)
