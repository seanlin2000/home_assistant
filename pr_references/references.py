"""Line references for pull request descriptions that a script can verify, so a reviewer never follows a range that was typed from memory.

Two forms. A symbol reference, `path:12-30` (`ClassName.method`), must match the exact span of that definition, decorators included. A text reference,
`path:12-30` ("quoted text"), must have the quoted text on one of the cited lines; it is for shell, YAML, and markdown files that have no symbols.
"""

import ast
import re
from pathlib import Path
from typing import NamedTuple

SYMBOL_REFERENCE = re.compile(r"`(?P<path>[^`:\s]+):(?P<start>\d+)-(?P<end>\d+)` \(`(?P<symbol>[^`]+)`\)")
TEXT_REFERENCE = re.compile(r"`(?P<path>[^`:\s]+):(?P<start>\d+)-(?P<end>\d+)` \(\"(?P<text>[^\"]+)\"\)")
SECTION_HEADING = re.compile(r"^## (?P<title>.+)$", re.MULTILINE)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
SECTIONS_WITHOUT_CODE = frozenset({"Summary", "How to verify", "Review notes"})
Definition = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Assign | ast.AnnAssign


class SymbolAnchor(NamedTuple):
    path: Path
    symbol: str

    def render(self) -> str:
        return f"`{self.symbol}`"

    def span(self) -> tuple[int, int]:
        definition = find_definition(ast.parse(self.path.read_text(encoding="utf-8")), self.symbol.split("."))
        return definition_span(definition)

    def mismatch(self, start: int, end: int) -> str | None:
        actual_start, actual_end = self.span()
        if (actual_start, actual_end) == (start, end):
            return None
        return f"`{self.symbol}` actually spans lines {actual_start}-{actual_end}"


class TextAnchor(NamedTuple):
    path: Path
    text: str

    def render(self) -> str:
        return f'"{self.text}"'

    def span(self) -> tuple[int, int]:
        lines = read_lines(self.path)
        start = first_line_containing(lines, self.text)
        return start, indented_block_end(lines, start)

    def mismatch(self, start: int, end: int) -> str | None:
        if any(self.text in line for line in read_lines(self.path)[start - 1 : end]):
            return None
        return f"text {self.text!r} is not on lines {start}-{end}"


class Reference(NamedTuple):
    anchor: SymbolAnchor | TextAnchor
    start: int
    end: int

    def render(self) -> str:
        return f"`{self.anchor.path}:{self.start}-{self.end}` ({self.anchor.render()})"


def parse_anchor(argument: str) -> SymbolAnchor | TextAnchor:
    path, _, target = argument.partition(":")
    if len(target) >= 2 and target.startswith('"') and target.endswith('"'):
        return TextAnchor(Path(path), target[1:-1])
    return SymbolAnchor(Path(path), target)


def resolve(anchor: SymbolAnchor | TextAnchor) -> Reference:
    start, end = anchor.span()
    return Reference(anchor, start, end)


def find_references(text: str) -> list[Reference]:
    text = HTML_COMMENT.sub("", text)
    symbol_references = [Reference(SymbolAnchor(Path(match["path"]), match["symbol"]), int(match["start"]), int(match["end"])) for match in SYMBOL_REFERENCE.finditer(text)]
    text_references = [Reference(TextAnchor(Path(match["path"]), match["text"]), int(match["start"]), int(match["end"])) for match in TEXT_REFERENCE.finditer(text)]
    return sorted(symbol_references + text_references, key=lambda reference: (str(reference.anchor.path), reference.start))


def mismatches(references: list[Reference]) -> list[str]:
    return [problem for problem in map(mismatch, references) if problem is not None]


def mismatch(reference: Reference) -> str | None:
    path = reference.anchor.path
    if not path.is_file():
        return f"{reference.render()}: file not found"
    line_count = len(read_lines(path))
    if not 1 <= reference.start <= reference.end <= line_count:
        return f"{reference.render()}: lines out of range, the file has {line_count} lines"
    return anchor_mismatch(reference)


def anchor_mismatch(reference: Reference) -> str | None:
    try:
        problem = reference.anchor.mismatch(reference.start, reference.end)
    except (LookupError, SyntaxError) as error:
        problem = str(error)
    return None if problem is None else f"{reference.render()}: {problem}"


def sections_without_references(text: str) -> list[str]:
    titles = [match["title"].strip() for match in SECTION_HEADING.finditer(text)]
    bodies = SECTION_HEADING.split(text)[2::2]
    return [title for title, body in zip(titles, bodies) if title not in SECTIONS_WITHOUT_CODE and not find_references(body)]


def find_definition(scope: ast.AST, names: list[str]) -> Definition:
    name, *rest = names
    for node in ast.iter_child_nodes(scope):
        if isinstance(node, Definition) and name in definition_names(node):
            return node if not rest else find_definition(node, rest)
    raise LookupError(f"no definition named {name!r}")


def definition_names(node: Definition) -> list[str]:
    if isinstance(node, ast.Assign):
        return [target.id for target in node.targets if isinstance(target, ast.Name)]
    if isinstance(node, ast.AnnAssign):
        return [node.target.id] if isinstance(node.target, ast.Name) else []
    return [node.name]


def definition_span(node: Definition) -> tuple[int, int]:
    decorators = getattr(node, "decorator_list", [])
    start = min([node.lineno, *(decorator.lineno for decorator in decorators)])
    return start, node.end_lineno or node.lineno


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def first_line_containing(lines: list[str], text: str) -> int:
    for number, line in enumerate(lines, start=1):
        if text in line:
            return number
    raise LookupError(f"text {text!r} not found")


def indented_block_end(lines: list[str], start: int) -> int:
    indent = indentation(lines[start - 1])
    end = start
    for number in range(start + 1, len(lines) + 1):
        line = lines[number - 1]
        if not line.strip() or indentation(line) <= indent:
            break
        end = number
    return end


def indentation(line: str) -> int:
    return len(line) - len(line.lstrip())
