"""Rendering every Mermaid block of the manual through the diagrams package, so a diagram that will not draw is reported at its line in the markdown and a finished one can be written as a PNG."""

import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from deslop.checks import Finding
from diagrams.mmdc import RenderResult, parse_failure, render_svg, run_mmdc
from diagrams.polish import polish
from diagrams.screenshot import screenshot
from manual_checks.blocks import MermaidBlock, file_line

Renderer = Callable[[str], RenderResult]


def mmdc_renderer(mmdc: Path, work_dir: Path, config: Path | None) -> Renderer:
    return lambda source: render_source(mmdc, source, work_dir, config)


def render_source(mmdc: Path, source: str, work_dir: Path, config: Path | None) -> RenderResult:
    completed = run_mmdc(mmdc, source, work_dir, config, f"diagram-{uuid.uuid4().hex}")
    if completed.returncode == 0:
        return RenderResult(True, "", None)
    return parse_failure(completed.stderr or completed.stdout)


def render_png(mmdc: Path, source: str, work_dir: Path, config: Path | None, out_path: Path, sandbox: bool) -> None:
    svg_path = work_dir / f"{out_path.stem}.svg"
    svg_path.write_text(polish(render_svg(mmdc, source, work_dir, config, f"diagram-{out_path.stem}")), encoding="utf-8")
    screenshot(svg_path, out_path, sandbox)


def render_findings(blocks: list[MermaidBlock], renderer: Renderer, jobs: int) -> list[Finding]:
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        results = list(pool.map(renderer, [block.source for block in blocks]))
    return [Finding(block.path, file_line(block, result.diagram_line), result.message) for block, result in zip(blocks, results) if not result.ok]
