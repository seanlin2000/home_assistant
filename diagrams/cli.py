"""Command line entry point: `uv run draw-diagram diagram.mmd --png out.png [--svg out.svg]` renders one Mermaid file the way the site does, so a diagram can be looked at before it goes into a page."""

import argparse
import sys
import tempfile
from pathlib import Path

from diagrams.mmdc import RendererUnavailable, find_browser, find_mmdc, render_svg, write_puppeteer_config
from diagrams.polish import polish
from diagrams.screenshot import screenshot

SVG_ID = "diagram-draw"


def main() -> None:
    args = parse_args()
    try:
        draw(args.source, args.svg, args.png, sandbox=not args.no_sandbox)
    except (RendererUnavailable, RuntimeError) as error:
        sys.exit(f"draw-diagram: {error}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="draw-diagram", description="Render one Mermaid file with the project's theme, layout engine, and post-processing.")
    parser.add_argument("source", type=Path, help="the .mmd file to render")
    parser.add_argument("--svg", type=Path, help="where to write the finished SVG")
    parser.add_argument("--png", type=Path, help="where to write a PNG of the finished SVG")
    parser.add_argument("--no-sandbox", action="store_true", help="start the browser without its sandbox (needed on GitHub's Ubuntu runners)")
    return parser.parse_args()


def draw(source: Path, svg_out: Path | None, png_out: Path | None, sandbox: bool) -> None:
    mmdc = find_mmdc()
    with tempfile.TemporaryDirectory(prefix="draw-diagram-") as work_dir:
        config = write_puppeteer_config(Path(work_dir), find_browser(), sandbox)
        svg = polish(render_svg(mmdc, source.read_text(encoding="utf-8"), Path(work_dir), config, SVG_ID))
        write_outputs(svg, Path(work_dir) / "polished.svg", svg_out, png_out, sandbox)


def write_outputs(svg: str, scratch: Path, svg_out: Path | None, png_out: Path | None, sandbox: bool) -> None:
    scratch.write_text(svg, encoding="utf-8")
    if svg_out is not None:
        svg_out.parent.mkdir(parents=True, exist_ok=True)
        svg_out.write_text(svg, encoding="utf-8")
    if png_out is not None:
        png_out.parent.mkdir(parents=True, exist_ok=True)
        screenshot(scratch, png_out, sandbox)
