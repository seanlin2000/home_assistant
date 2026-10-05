"""Rendering every Mermaid block of the manual through the diagrams package, so a diagram that will not draw is reported at its line in the markdown and a finished one can be written as a PNG."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from deslop.checks import Finding
from diagrams.layout import polish
from diagrams.mmdc import RenderFailed, RenderResult, render_svg
from diagrams.screenshot import screenshot
from manual_checks.blocks import MermaidBlock, file_line
from manual_checks.diagram_cache import cached, store, svg_id

Renderer = Callable[[str], RenderResult]


def mmdc_renderer(mmdc: Path, work_dir: Path, config: Path | None) -> Renderer:
    return lambda source: render_source(mmdc, source, work_dir, config)


def render_source(mmdc: Path, source: str, work_dir: Path, config: Path | None) -> RenderResult:
    try:
        drawn_svg(mmdc, source, work_dir, config)
    except RenderFailed as failure:
        return failure.result
    return RenderResult(True, "", None)


def drawn_svg(mmdc: Path, source: str, work_dir: Path, config: Path | None) -> str:
    found = cached(source)
    if found is not None:
        return found
    return store(source, polish(render_svg(mmdc, source, work_dir, config, svg_id(source)), source))


def render_png(mmdc: Path, source: str, work_dir: Path, config: Path | None, out_path: Path, sandbox: bool) -> None:
    svg_path = work_dir / f"{out_path.stem}.svg"
    svg_path.write_text(drawn_svg(mmdc, source, work_dir, config), encoding="utf-8")
    screenshot(svg_path, out_path, sandbox)


def render_findings(blocks: list[MermaidBlock], renderer: Renderer, jobs: int) -> list[Finding]:
    sources = sorted({block.source for block in blocks})
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        results = dict(zip(sources, pool.map(renderer, sources)))
    return [Finding(block.path, file_line(block, results[block.source].diagram_line), results[block.source].message) for block in blocks if not results[block.source].ok]
    # The system map is included by every page, so the same source is drawn once and its result reported at each of its lines.
