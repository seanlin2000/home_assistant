"""Structure checks for manual pages: required headings in order, the complexity comment, the "Where this fits" map, palette discipline, and glossary agreement."""

import re
from pathlib import Path
from typing import NamedTuple

from deslop.checks import Finding
from manual_checks.blocks import MermaidBlock, outside_fences

SECTION_HEADINGS = ("Where this fits", "Key definitions", "Packages and tools", "How it works", "Run it yourself", "Where to look in the code", "Further reading")
INTRODUCTION_HEADINGS = ("Purpose", "How to read this manual", "Key definitions", "Software and hardware", "The system map", "Where the code lives", "Before you run anything")
ENTRY_HEADINGS = ("Where this fits", "Key definitions", "Packages and tools", "What changed", "Run it yourself")
INTRODUCTION_FILE = "index.md"
CHANGES_FILE = "current_changes.md"
GLOSSARY_FILE = "glossary.md"
PALETTE_FILE = "_includes/palette.mmd"
SYSTEM_MAP_INCLUDE = "_includes/system_map.mmd"
FILES_WITHOUT_PROFILE = frozenset({GLOSSARY_FILE, "diagram_legend.md", "versions.md"})
HEADING = re.compile(r"^(?P<hashes>#{1,6}) (?P<title>\S.*?)\s*$")
COMPLEXITY = re.compile(r"^<!-- complexity: packages=(?P<packages>[123]) parts=(?P<parts>[123]) concepts=(?P<concepts>[123]) tier=(?P<tier>light|standard|deep) -->$")
TIERS = {3: "light", 4: "light", 5: "standard", 6: "standard", 7: "standard", 8: "deep", 9: "deep"}
ENTRY_TITLE = re.compile(r"^(PR #\d+|Branch [\w./-]+): \S")
ENTRY_MARKER = re.compile(r'^<!-- manual-entry branch="(?P<branch>[^"]+)" pr="(?P<pr>\d+|pending)" date="\d{4}-\d{2}-\d{2}" -->$')
DEFINITION = re.compile(r"^- \*\*(?P<term>[^*]+?)\.?\*\* ")
CLASS_LINE = re.compile(r"^\s*class\s+[\w,\s]+\s+(?P<name>\w+)\s*$")
CLASS_DEF = re.compile(r"^\s*classDef\s+(?P<name>\w+)\b")
INLINE_CLASS = re.compile(r":::(?P<name>\w+)")
HIGHLIGHT = re.compile(r"^\s*(class\s+[\w,\s]+\s+current|style\s+\w+\s+.*#f59e0b)")


class Heading(NamedTuple):
    level: int
    title: str
    line: int


class Page(NamedTuple):
    path: Path
    text: str
    headings: list[Heading]
    blocks: list[MermaidBlock]


def headings(text: str) -> list[Heading]:
    found = []
    for number, line in outside_fences(text):
        matched = HEADING.match(line)
        if matched:
            found.append(Heading(len(matched.group("hashes")), matched.group("title"), number))
    return found


def structure_findings(page: Page, glossary_terms: set[str], palette: set[str]) -> list[Finding]:
    findings = palette_findings(page.path, page.blocks, palette)
    if page.path.name in FILES_WITHOUT_PROFILE:
        return findings
    if page.path.name == INTRODUCTION_FILE:
        findings += required_in_order(page.path, page.headings, 2, INTRODUCTION_HEADINGS, 1)
    elif page.path.name == CHANGES_FILE:
        findings += entry_findings(page)
    else:
        findings += section_findings(page)
    findings += glossary_findings(page, glossary_terms)
    return sorted(findings, key=lambda finding: finding.line)


def section_findings(page: Page) -> list[Finding]:
    findings = required_in_order(page.path, page.headings, 2, SECTION_HEADINGS, 1)
    findings += complexity_findings(page)
    findings += where_this_fits_findings(page, 2)
    return findings


def required_in_order(path: Path, found: list[Heading], level: int, required: tuple[str, ...], start_line: int) -> list[Finding]:
    titles = [heading.title for heading in found if heading.level == level]
    findings = []
    previous_index = -1
    for title in required:
        if title not in titles:
            findings.append(Finding(path, start_line, f"missing heading '{'#' * level} {title}'"))
            continue
        index = titles.index(title)
        if index < previous_index:
            findings.append(Finding(path, heading_line(found, level, title), f"heading '{'#' * level} {title}' out of order (expected after '{'#' * level} {titles[previous_index]}')"))
        previous_index = max(previous_index, index)
    return findings


def heading_line(found: list[Heading], level: int, title: str) -> int:
    return next(heading.line for heading in found if heading.level == level and heading.title == title)


def complexity_findings(page: Page) -> list[Finding]:
    for number, line in outside_fences(page.text):
        matched = COMPLEXITY.match(line)
        if matched is None:
            continue
        score = int(matched.group("packages")) + int(matched.group("parts")) + int(matched.group("concepts"))
        if TIERS[score] != matched.group("tier"):
            return [Finding(page.path, number, f"complexity score {score} is tier '{TIERS[score]}', not '{matched.group('tier')}'")]
        return []
    return [Finding(page.path, 1, "missing complexity comment under the title: <!-- complexity: packages=N parts=N concepts=N tier=light|standard|deep -->")]


def where_this_fits_findings(page: Page, level: int) -> list[Finding]:
    findings = []
    for heading in page.headings:
        if heading.level == level and heading.title == "Where this fits":
            findings += map_block_findings(page, first_block_after(page.blocks, heading.line))
    return findings


def first_block_after(blocks: list[MermaidBlock], line: int) -> MermaidBlock | None:
    return next((block for block in blocks if block.line > line), None)


def map_block_findings(page: Page, block: MermaidBlock | None) -> list[Finding]:
    if block is None:
        return [Finding(page.path, 1, "'Where this fits' has no mermaid block")]
    raw_body = page.text.splitlines()[block.line : block.line + len(block.file_lines)]
    if not any(SYSTEM_MAP_INCLUDE in line for line in raw_body):
        return [Finding(page.path, block.line, f"'Where this fits' diagram must include the system map: --8<-- \"{SYSTEM_MAP_INCLUDE}\"")]
    if not any(HIGHLIGHT.match(line) for line in raw_body):
        return [Finding(page.path, block.line, "'Where this fits' diagram highlights nothing: add 'class <ids> current' or a 'style <subgraph> ... #f59e0b' line")]
    return []


def entry_findings(page: Page) -> list[Finding]:
    findings = []
    branches: set[str] = set()
    entries = [heading for heading in page.headings if heading.level == 2]
    for index, entry in enumerate(entries):
        end_line = entries[index + 1].line if index + 1 < len(entries) else len(page.text.splitlines()) + 1
        findings += entry_title_findings(page, entry, branches)
        findings += required_in_order(page.path, [heading for heading in page.headings if entry.line < heading.line < end_line], 3, ENTRY_HEADINGS, entry.line)
        findings += where_this_fits_findings(
            Page(page.path, page.text, [heading for heading in page.headings if entry.line < heading.line < end_line], [block for block in page.blocks if entry.line < block.line < end_line]), 3
        )
    return findings


def entry_title_findings(page: Page, entry: Heading, branches: set[str]) -> list[Finding]:
    findings = []
    if not ENTRY_TITLE.match(entry.title):
        findings.append(Finding(page.path, entry.line, f"entry heading must read '## PR #N: title' or '## Branch name: title', got '## {entry.title}'"))
    lines = page.text.splitlines()
    marker = ENTRY_MARKER.match(lines[entry.line]) if entry.line < len(lines) else None
    if marker is None:
        findings.append(Finding(page.path, entry.line + 1, 'entry heading must be followed by <!-- manual-entry branch="..." pr="N|pending" date="YYYY-MM-DD" -->'))
    elif marker.group("branch") in branches:
        findings.append(Finding(page.path, entry.line + 1, f"duplicate entry for branch '{marker.group('branch')}'"))
    else:
        branches.add(marker.group("branch"))
    return findings


def palette_findings(path: Path, blocks: list[MermaidBlock], palette: set[str]) -> list[Finding]:
    allowed = {CLASS_DEF.match(line).group("name") for line in palette}
    findings = []
    for block in blocks:
        for offset, line in enumerate(block.source.splitlines(), start=1):
            findings += palette_line_findings(path, block.file_lines[offset - 1], line, palette, allowed)
    return findings


def palette_line_findings(path: Path, line_number: int, line: str, palette: set[str], allowed: set[str]) -> list[Finding]:
    if CLASS_DEF.match(line) and " ".join(line.split()) not in palette:
        return [Finding(path, line_number, f"classDef outside the palette ({PALETTE_FILE}): {line.strip()}")]
    used = {matched.group("name") for matched in [CLASS_LINE.match(line)] if matched} | set(INLINE_CLASS.findall(line))
    return [Finding(path, line_number, f"class '{name}' is not one of the palette classes {sorted(allowed)}") for name in sorted(used - allowed)]


def glossary_findings(page: Page, glossary_terms: set[str]) -> list[Finding]:
    findings = []
    for number, line in definition_lines(page):
        term = DEFINITION.match(line).group("term")
        if term.casefold() not in glossary_terms:
            findings.append(Finding(page.path, number, f"'{term}' is defined here but missing from {GLOSSARY_FILE}"))
    return findings


def definition_lines(page: Page) -> list[tuple[int, str]]:
    inside = False
    lines = []
    for number, line in outside_fences(page.text):
        matched = HEADING.match(line)
        if matched:
            inside = matched.group("title") == "Key definitions"
        elif inside and DEFINITION.match(line):
            lines.append((number, line))
    return lines


def glossary_terms(text: str) -> set[str]:
    return {DEFINITION.match(line).group("term").casefold() for _, line in outside_fences(text) if DEFINITION.match(line)}


def palette_lines(text: str) -> set[str]:
    return {" ".join(line.split()) for line in text.splitlines() if CLASS_DEF.match(line)}
