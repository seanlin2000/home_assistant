"""MkDocs hook: every ```mermaid block becomes the SVG mermaid-cli draws for it, so the site shows exactly what manual-check rendered.

Rendered SVGs are cached by content hash under .cache/manual_diagrams so `mkdocs serve` only renders what changed."""

import hashlib
import re
import tempfile
from pathlib import Path
from typing import Any

from manual_checks.blocks import expand_snippets, fenced_blocks
from manual_checks.render import MERMAID_CONFIG, RendererUnavailable, find_browser, find_mmdc, render_svg, write_puppeteer_config

CACHE_DIR = Path(".cache/manual_diagrams")
FIGURE = '<figure class="manual-diagram">\n{svg}\n</figure>'
NATURAL_WIDTH = re.compile(r'style="max-width: (\d+(?:\.\d+)?)px; background-color: white;"')
MIN_SCALE = 0.7


def on_page_markdown(markdown: str, page: Any, config: Any, files: Any) -> str:
    docs_dir = Path(config["docs_dir"])
    replacements = rendered_blocks(markdown, docs_dir)
    if not replacements:
        return markdown
    lines = markdown.splitlines()
    for start, end, svg in reversed(replacements):
        lines[start - 1 : end] = [FIGURE.format(svg=svg)]
    return "\n".join(lines) + "\n"


def rendered_blocks(markdown: str, docs_dir: Path) -> list[tuple[int, int, str]]:
    replacements = []
    for block in fenced_blocks(markdown):
        if block.language != "mermaid":
            continue
        source_lines, _ = expand_snippets(block.body, block.line, docs_dir)
        source = "\n".join(source_lines) + "\n"
        replacements.append((block.line, block.line + len(block.body) + 1, cached_svg(source)))
    return replacements


def cached_svg(source: str) -> str:
    key = hashlib.sha256(source.encode("utf-8") + MERMAID_CONFIG.read_bytes()).hexdigest()
    cached = CACHE_DIR / f"{key}.svg"
    if cached.is_file():
        return cached.read_text(encoding="utf-8")
    svg = render_fresh(source, key[:12])
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_text(svg, encoding="utf-8")
    return svg


def render_fresh(source: str, svg_id: str) -> str:
    try:
        mmdc = find_mmdc()
    except RendererUnavailable as error:
        raise RuntimeError(f"manual diagrams: {error}") from error
    with tempfile.TemporaryDirectory(prefix="manual-diagram-") as work_dir:
        config = write_puppeteer_config(Path(work_dir), find_browser(), sandbox=False)
        return sized(render_svg(mmdc, source, Path(work_dir), config, f"diagram-{svg_id}"))


def sized(svg: str) -> str:
    return NATURAL_WIDTH.sub(lambda match: f'style="width: 100%; max-width: {match.group(1)}px; min-width: {float(match.group(1)) * MIN_SCALE:.0f}px;"', svg, count=1)
