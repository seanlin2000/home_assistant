"""Command line entry point: `uv run deslop [paths...]` prints one line per finding and exits 1 when there are any."""

import argparse
import sys
from collections.abc import Iterator
from pathlib import Path

from deslop.checks import Finding, check_source

EXCLUDED_DIRS = frozenset({".venv", ".git", "vm", "__pycache__"})


def main() -> None:
    findings = check_paths(parse_args().paths)
    for finding in findings:
        print(format_finding(finding))
    sys.exit(1 if findings else 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="deslop", description="Check Python files against claude_docs/CLEAN_CODE.md: every parameter typed, and at most one comment line per code line in each function."
    )
    parser.add_argument("paths", nargs="*", type=Path, default=[Path(".")], help="files or directories to check (default: the current directory)")
    return parser.parse_args()


def check_paths(paths: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        for python_file in python_files(path):
            findings.extend(check_source(python_file, python_file.read_text(encoding="utf-8")))
    return sorted(findings, key=lambda finding: (str(finding.path), finding.line))


def python_files(path: Path) -> Iterator[Path]:
    if path.is_file():
        yield path
        return
    for folder, subfolders, files in path.walk():
        subfolders[:] = sorted(name for name in subfolders if name not in EXCLUDED_DIRS)
        yield from (folder / name for name in sorted(files) if name.endswith(".py"))


def format_finding(finding: Finding) -> str:
    return f"{finding.path}:{finding.line}: {finding.message}"
