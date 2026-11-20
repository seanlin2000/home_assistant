"""`uv run pr-refs resolve path:symbol ...` prints references to paste into a PR description; `uv run pr-refs check body.md` verifies every reference in one;
`uv run pr-refs lint body.md` verifies that the description has the template's shape."""

import argparse
import sys
from pathlib import Path

from pr_references.lint import lint
from pr_references.references import find_references, mismatches, parse_anchor, resolve, sections_without_references


def main() -> None:
    arguments = parse_args()
    arguments.command(arguments)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="pr-refs", description="Produce and verify the line references in a pull request description.")
    commands = parser.add_subparsers(required=True)
    resolve_parser = commands.add_parser("resolve", help='print a reference for each anchor, e.g. deslop/checks.py:count_lines or .githooks/pre-commit:"uv run deslop"')
    resolve_parser.add_argument("anchors", nargs="+", help='path:symbol (dotted for methods) or path:"quoted text"')
    resolve_parser.set_defaults(command=resolve_command)
    check_parser = commands.add_parser("check", help="verify every reference in a markdown file against the working tree")
    check_parser.add_argument("body", type=Path, help="the PR description as a markdown file")
    check_parser.set_defaults(command=check_command)
    lint_parser = commands.add_parser("lint", help="verify the description's shape: required sections, and every change bullet reads reference, bold phrase, description")
    lint_parser.add_argument("body", type=Path, help="the PR description as a markdown file")
    lint_parser.set_defaults(command=lint_command)
    return parser.parse_args()


def resolve_command(arguments: argparse.Namespace) -> None:
    try:
        print_resolved(arguments.anchors)
    except (LookupError, FileNotFoundError, SyntaxError) as error:
        sys.exit(f"pr-refs: {error}")


def print_resolved(anchors: list[str]) -> None:
    for anchor in anchors:
        print(resolve(parse_anchor(anchor)).render())


def check_command(arguments: argparse.Namespace) -> None:
    text = arguments.body.read_text(encoding="utf-8")
    references = find_references(text)
    problems = mismatches(references)
    for title in sections_without_references(text):
        print(f"warning: section '{title}' cites no code")
    for problem in problems:
        print(problem)
    print(f"{len(references)} references checked, {len(problems)} wrong")
    sys.exit(1 if problems else 0)


def lint_command(arguments: argparse.Namespace) -> None:
    problems = lint(arguments.body.read_text(encoding="utf-8"))
    for problem in problems:
        print(problem.render(str(arguments.body)))
    print(f"description shape: {len(problems)} problem{'' if len(problems) == 1 else 's'}")
    sys.exit(1 if problems else 0)
