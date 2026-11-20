"""MkDocs hook: every ```mermaid block becomes the SVG the diagrams package draws for it, so the site shows exactly what manual-check rendered.

Rendered SVGs come from the cache `manual_checks/diagram_cache.py` keeps under .cache/manual_diagrams, shared with `manual-check`, so `mkdocs serve` only draws what changed and never draws what the checker has already drawn.
"""

import re
import tempfile
from pathlib import Path
from typing import Any

from mkdocs.exceptions import PluginError

from diagrams.layout import polish
from diagrams.mmdc import RendererUnavailable, RenderFailed, find_browser, find_mmdc, render_svg, write_puppeteer_config
from manual_checks.blocks import MermaidBlock, expand_snippets, fenced_blocks, file_line
from manual_checks.diagram_cache import cached, store, svg_id

FIGURE = '<figure class="manual-diagram">\n{svg}\n</figure>'
NATURAL_WIDTH = re.compile(r'style="max-width: (\d+(?:\.\d+)?)px; background-color: white;"')
MIN_SCALE = 0.7


def on_page_markdown(markdown: str, page: Any, config: Any, files: Any) -> str:
    docs_dir = Path(config["docs_dir"])
    replacements = rendered_blocks(markdown, Path(page.file.src_uri), docs_dir)
    if not replacements:
        return markdown
    lines = markdown.splitlines()
    for start, end, svg in reversed(replacements):
        lines[start - 1 : end] = [FIGURE.format(svg=svg)]
    return "\n".join(lines) + "\n"


def rendered_blocks(markdown: str, page_path: Path, docs_dir: Path) -> list[tuple[int, int, str]]:
    replacements = []
    for block in fenced_blocks(markdown):
        if block.language != "mermaid":
            continue
        source_lines, file_lines = expand_snippets(block.body, block.line, docs_dir)
        mermaid_block = MermaidBlock(page_path, block.line, "\n".join(source_lines) + "\n", tuple(file_lines))
        replacements.append((block.line, block.line + len(block.body) + 1, sized(block_svg(mermaid_block))))
    return replacements


def block_svg(block: MermaidBlock) -> str:
    try:
        return cached_svg(block.source)
    except RenderFailed as failure:
        raise PluginError(f"{block.path}:{file_line(block, failure.result.diagram_line)}: {failure.result.message}") from failure
    # The strict build is the docs job's only render check, so a diagram that will not draw is reported at its page and line, as manual-check reports it.


def cached_svg(source: str) -> str:
    found = cached(source)
    return found if found is not None else render_fresh(source)


def render_fresh(source: str) -> str:
    try:
        mmdc = find_mmdc()
    except RendererUnavailable as error:
        raise RuntimeError(f"manual diagrams: {error}") from error
    with tempfile.TemporaryDirectory(prefix="manual-diagram-") as work_dir:
        config = write_puppeteer_config(Path(work_dir), find_browser(), sandbox=False)
        return store(source, polish(render_svg(mmdc, source, Path(work_dir), config, svg_id(source)), source))


def sized(svg: str) -> str:
    return NATURAL_WIDTH.sub(lambda match: f'style="width: 100%; max-width: {match.group(1)}px; min-width: {float(match.group(1)) * MIN_SCALE:.0f}px;"', svg, count=1)
