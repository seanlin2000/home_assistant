"""The two rules from claude_docs/CLEAN_CODE.md that a script can judge: every parameter is typed, and a function's comments never outnumber its code."""

import ast
import io
import tokenize
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
ALLOW_COMMENTS_MARKER = "deslop: allow-comments"
IMPLICIT_RECEIVERS = ("self", "cls")


class Finding(NamedTuple):
    path: Path
    line: int
    message: str


@dataclass(frozen=True)
class ParsedSource:
    tree: ast.Module
    lines: list[str]
    comment_lines: set[int]
    marker_lines: set[int]


def check_source(path: Path, text: str) -> list[Finding]:
    try:
        source = parse_source(text)
    except SyntaxError as error:
        return [Finding(path, error.lineno or 1, f"cannot parse: {error.msg}")]
    except tokenize.TokenError as error:
        return [Finding(path, 1, f"cannot parse: {error.args[0]}")]
    return function_findings(path, source)


def function_findings(path: Path, source: ParsedSource) -> list[Finding]:
    findings: list[Finding] = []
    for node, parent in functions_with_parents(source.tree):
        findings.extend(annotation_findings(path, node, parent))
        ratio_finding = comment_ratio_finding(path, node, source)
        if ratio_finding is not None:
            findings.append(ratio_finding)
    return sorted(findings, key=lambda finding: finding.line)


def parse_source(text: str) -> ParsedSource:
    tree = ast.parse(text)
    comment_lines: set[int] = set()
    marker_lines: set[int] = set()
    for token in comment_tokens(text):
        line = token.start[0]
        if ALLOW_COMMENTS_MARKER in token.string:
            marker_lines.add(line)
        elif token.line.lstrip().startswith("#"):
            comment_lines.add(line)
    return ParsedSource(tree, text.splitlines(), comment_lines, marker_lines)


def comment_tokens(text: str) -> Iterator[tokenize.TokenInfo]:
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.COMMENT:
            yield token


def functions_with_parents(tree: ast.Module) -> Iterator[tuple[FunctionNode, ast.AST]]:
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            if isinstance(child, FunctionNode):
                yield child, parent


def annotation_findings(path: Path, node: FunctionNode, parent: ast.AST) -> list[Finding]:
    return [Finding(path, node.lineno, f"{node.name}: parameter '{name}' has no type annotation") for name in unannotated_parameters(node, parent)]


def unannotated_parameters(node: FunctionNode, parent: ast.AST) -> list[str]:
    receiver = implicit_receiver(node, parent)
    return [parameter.arg for parameter in all_parameters(node) if parameter is not receiver and parameter.annotation is None]


def all_parameters(node: FunctionNode) -> list[ast.arg]:
    arguments = node.args
    star_parameters = [parameter for parameter in (arguments.vararg, arguments.kwarg) if parameter is not None]
    return arguments.posonlyargs + arguments.args + arguments.kwonlyargs + star_parameters


def implicit_receiver(node: FunctionNode, parent: ast.AST) -> ast.arg | None:
    if not isinstance(parent, ast.ClassDef):
        return None
    positional = node.args.posonlyargs + node.args.args
    if positional and positional[0].arg in IMPLICIT_RECEIVERS:
        return positional[0]
    return None


def comment_ratio_finding(path: Path, node: FunctionNode, source: ParsedSource) -> Finding | None:
    if is_exempt(node, source):
        return None
    comment_count, code_count = count_lines(node, source)
    if comment_count <= code_count:
        return None
    return Finding(path, node.lineno, f"{node.name}: {comment_count} comment lines exceed {code_count} code lines (add '# {ALLOW_COMMENTS_MARKER}' to exempt)")


def is_exempt(node: FunctionNode, source: ParsedSource) -> bool:
    first_line = min([node.lineno, *(decorator.lineno for decorator in node.decorator_list)])
    marker_positions = {node.lineno, node.lineno - 1, first_line - 1}
    return bool(marker_positions & source.marker_lines)


def count_lines(node: FunctionNode, source: ParsedSource) -> tuple[int, int]:
    docstring = docstring_lines(node)
    nested = nested_function_lines(node)
    comment_count = len(docstring)
    code_count = 0
    for line in range(node.lineno + 1, (node.end_lineno or node.lineno) + 1):
        if line in docstring or line in nested:
            continue
        if line in source.comment_lines:
            comment_count += 1
        elif line >= node.body[0].lineno and source.lines[line - 1].strip():
            code_count += 1
    return comment_count, code_count


def docstring_lines(node: FunctionNode) -> range:
    first_statement = node.body[0]
    if isinstance(first_statement, ast.Expr) and isinstance(first_statement.value, ast.Constant) and isinstance(first_statement.value.value, str):
        return range(first_statement.lineno, (first_statement.end_lineno or first_statement.lineno) + 1)
    return range(0)


def nested_function_lines(node: FunctionNode) -> set[int]:
    lines: set[int] = set()
    for inner in ast.walk(node):
        if inner is not node and isinstance(inner, FunctionNode):
            lines.update(range(inner.lineno, (inner.end_lineno or inner.lineno) + 1))
    return lines
