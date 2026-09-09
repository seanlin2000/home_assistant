"""Command line entry point: `uv run manual-check [paths...]` prints one line per finding and exits 1 when there are any."""

import argparse
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

from deslop.checks import Finding
from deslop.cli import format_finding
from manual_checks.blocks import MermaidBlock, mermaid_blocks
from manual_checks.headings import GLOSSARY_FILE, PALETTE_FILE, Page, glossary_terms, headings, palette_lines, structure_findings
from manual_checks.render import RendererUnavailable, find_browser, find_mmdc, mmdc_renderer, render_findings, render_png, write_puppeteer_config

DEFAULT_ROOT = Path("operator_manual")
INCLUDES_DIR = "_includes"


def main() -> None:
    args = parse_args()
    try:
        findings = check(args.root, args.paths or [args.root], render=not args.no_render, sandbox=not args.no_sandbox, jobs=args.jobs)
        if args.png is not None:
            write_pngs(args.root, args.paths or [args.root], args.png, sandbox=not args.no_sandbox)
    except RendererUnavailable as error:
        sys.exit(f"manual-check: {error}")
    for finding in findings:
        print(format_finding(finding))
    sys.exit(1 if findings else 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="manual-check", description="Check the operator manual: every Mermaid diagram renders with mmdc, and every page has the headings its profile requires.")
    parser.add_argument("paths", nargs="*", type=Path, help="markdown files or folders to check (default: the manual root)")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help=f"manual root holding {GLOSSARY_FILE} and {PALETTE_FILE} (default: {DEFAULT_ROOT})")
    parser.add_argument("--no-render", action="store_true", help="skip mmdc; check structure only")
    parser.add_argument("--no-sandbox", action="store_true", help="start the browser without its sandbox (needed on GitHub's Ubuntu runners)")
    parser.add_argument("--jobs", type=int, default=4, help="diagrams rendered in parallel (default: 4)")
    parser.add_argument("--png", type=Path, help="also write every diagram as <dir>/<page stem>_<line>.png, to look at")
    return parser.parse_args()


def check(root: Path, paths: list[Path], render: bool, sandbox: bool, jobs: int) -> list[Finding]:
    pages = [load_page(path, root) for target in paths for path in markdown_files(target)]
    terms = glossary_terms(read_or_empty(root / GLOSSARY_FILE))
    palette = palette_lines(read_or_empty(root / PALETTE_FILE))
    findings = [finding for page in pages for finding in structure_findings(page, terms, palette)]
    if render:
        findings += rendered_findings([block for page in pages for block in page.blocks], sandbox, jobs)
    return sorted(findings, key=lambda finding: (str(finding.path), finding.line))


def load_page(path: Path, root: Path) -> Page:
    text = path.read_text(encoding="utf-8")
    return Page(path, text, headings(text), mermaid_blocks(path, text, root))


def markdown_files(path: Path) -> Iterator[Path]:
    if path.is_file():
        yield path
        return
    for candidate in sorted(path.rglob("*.md")):
        if INCLUDES_DIR not in candidate.parts:
            yield candidate


def read_or_empty(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def rendered_findings(blocks: list, sandbox: bool, jobs: int) -> list[Finding]:
    mmdc = find_mmdc()
    with tempfile.TemporaryDirectory(prefix="manual-check-") as work_dir:
        config = write_puppeteer_config(Path(work_dir), find_browser(), sandbox)
        return render_findings(blocks, mmdc_renderer(mmdc, Path(work_dir), config), jobs)


def write_pngs(root: Path, paths: list[Path], out_dir: Path, sandbox: bool) -> None:
    blocks = [block for target in paths for path in markdown_files(target) for block in load_page(path, root).blocks]
    out_dir.mkdir(parents=True, exist_ok=True)
    mmdc = find_mmdc()
    with tempfile.TemporaryDirectory(prefix="manual-check-") as work_dir:
        config = write_puppeteer_config(Path(work_dir), find_browser(), sandbox)
        for block in blocks:
            render_png(mmdc, block.source, Path(work_dir), config, png_path(out_dir, block))


def png_path(out_dir: Path, block: MermaidBlock) -> Path:
    return out_dir / f"{block.path.stem}_{block.line}.png"
