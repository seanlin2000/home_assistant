"""The shape of a pull request description, checked so the template is followed and not only imitated.

Every change section (any "## " section other than Summary, How to verify, and Review notes) is made of bullets, and each bullet reads in
one order: the line references a reviewer should open, then a short bold phrase naming the change, then the description. The reference
checker in references.py only asks whether a range is right; this module asks whether the bullet around it has the agreed shape.
"""

import re
from typing import NamedTuple

from pr_references.references import HTML_COMMENT, SECTION_HEADING, SECTIONS_WITHOUT_CODE

REFERENCE = r"`[^`:\s]+:\d+-\d+` \((?:`[^`]+`|\"[^\"]+\")\)"
WELL_FORMED_BULLET = re.compile(rf"^- {REFERENCE}(?:, {REFERENCE})* \*\*[^*]+\.\*\* \S")
BULLET_SHAPE = "a bullet reads: one or more references, then **a short phrase ending in a period.**, then the description"
REQUIRED_SECTIONS = ("Summary", "How to verify", "Review notes")


class Problem(NamedTuple):
    line: int
    message: str

    def render(self, filename: str) -> str:
        return f"{filename}:{self.line}: {self.message}"


def lint(text: str) -> list[Problem]:
    text = blank_out_html_comments(text)
    return missing_required_sections(text) + bullet_problems(text)


def blank_out_html_comments(text: str) -> str:
    """Comments (the template's instructions) are not part of the description, but their line breaks are kept so line numbers stay true."""
    return HTML_COMMENT.sub(lambda match: "\n" * match.group().count("\n"), text)


def missing_required_sections(text: str) -> list[Problem]:
    titles = {match["title"].strip() for match in SECTION_HEADING.finditer(text)}
    return [Problem(1, f"missing section '## {title}'") for title in REQUIRED_SECTIONS if title not in titles]


def bullet_problems(text: str) -> list[Problem]:
    problems: list[Problem] = []
    for section in change_sections(text):
        problems.extend(section.problems())
    return problems


class Section(NamedTuple):
    title: str
    heading_line: int
    lines: list[tuple[int, str]]

    def problems(self) -> list[Problem]:
        bullets = [(number, line) for number, line in self.lines if line.startswith("- ")]
        if not bullets:
            return [Problem(self.heading_line, f"section '{self.title}' has no bullets")]
        return [Problem(number, BULLET_SHAPE) for number, line in bullets if not WELL_FORMED_BULLET.match(line)]


def change_sections(text: str) -> list[Section]:
    sections: list[Section] = []
    for number, line in enumerate(text.splitlines(), start=1):
        heading = SECTION_HEADING.match(line)
        if heading:
            sections.append(Section(heading["title"].strip(), number, []))
        elif sections:
            sections[-1].lines.append((number, line))
    return [section for section in sections if section.title not in SECTIONS_WITHOUT_CODE]
