"""Fenced-block scanning for the manual: Mermaid blocks with their file lines, snippet expansion, and the lines outside any fence."""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

FENCE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})[ \t]*(?P<language>[\w+-]*)[ \t]*$")
SNIPPET = re.compile(r'^\s*--8<--\s*"(?P<path>[^"]+)"\s*$')
UNTERMINATED = "unterminated"


class FencedBlock(NamedTuple):
    line: int
    language: str
    body: list[str]


class MermaidBlock(NamedTuple):
    path: Path
    line: int
    source: str
    file_lines: tuple[int, ...]


def fenced_blocks(text: str) -> Iterator[FencedBlock]:
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        opening = FENCE.match(lines[index])
        if opening is None:
            index += 1
            continue
        end = closing_fence_index(lines, index, opening)
        body = dedented_body(lines[index + 1 : end], len(opening.group("indent")))
        yield FencedBlock(index + 1, opening.group("language") if end < len(lines) else UNTERMINATED, body)
        index = end + 1


def closing_fence_index(lines: list[str], start: int, opening: re.Match[str]) -> int:
    fence = opening.group("fence")
    for index in range(start + 1, len(lines)):
        candidate = FENCE.match(lines[index])
        if candidate and candidate.group("fence")[0] == fence[0] and len(candidate.group("fence")) >= len(fence) and not candidate.group("language"):
            return index
    return len(lines)


def dedented_body(lines: list[str], indent: int) -> list[str]:
    return [line[min(indent, leading_whitespace(line)) :] for line in lines]


def leading_whitespace(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def outside_fences(text: str) -> Iterator[tuple[int, str]]:
    fenced_lines: set[int] = set()
    for block in fenced_blocks(text):
        fenced_lines.update(range(block.line, block.line + len(block.body) + 2))
    for number, line in enumerate(text.splitlines(), start=1):
        if number not in fenced_lines:
            yield number, line


def mermaid_blocks(path: Path, text: str, include_dir: Path) -> list[MermaidBlock]:
    blocks = []
    for block in fenced_blocks(text):
        if block.language == "mermaid":
            source_lines, file_lines = expand_snippets(block.body, block.line, include_dir)
            blocks.append(MermaidBlock(path, block.line, "\n".join(source_lines) + "\n", tuple(file_lines)))
    return blocks


def expand_snippets(body: list[str], fence_line: int, include_dir: Path) -> tuple[list[str], list[int]]:
    source_lines: list[str] = []
    file_lines: list[int] = []
    for offset, line in enumerate(body, start=1):
        snippet = SNIPPET.match(line)
        included = expand_snippets(snippet_lines(include_dir / snippet.group("path")), 0, include_dir)[0] if snippet else [line]
        source_lines.extend(included)
        file_lines.extend([fence_line + offset] * len(included))
    return source_lines, file_lines


def snippet_lines(path: Path) -> list[str]:
    if not path.is_file():
        return [f"Snippet not found: {path}"]
    return path.read_text(encoding="utf-8").splitlines()


def file_line(block: MermaidBlock, diagram_line: int | None) -> int:
    if diagram_line is None or diagram_line < 1 or diagram_line > len(block.file_lines):
        return block.line
    return block.file_lines[diagram_line - 1]
