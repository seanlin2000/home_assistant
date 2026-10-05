"""The rendered-SVG cache the site build, the checker, and the PNG writer share, so one diagram is drawn once however many pages include it and however many commands ask for it.

A diagram is keyed by its source together with the code that draws it, so editing a diagram, the theme, or the layout stages draws it afresh, and nothing else does.
"""

import hashlib
from pathlib import Path

from diagrams import grid as grid_module
from diagrams import layout as layout_module
from diagrams import polish as polish_module
from diagrams.mmdc import MERMAID_CONFIG

CACHE_DIR = Path(".cache/manual_diagrams")
RENDER_INPUTS = (MERMAID_CONFIG, Path(polish_module.__file__), Path(grid_module.__file__), Path(layout_module.__file__))


def cache_key(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8") + b"".join(path.read_bytes() for path in RENDER_INPUTS)).hexdigest()


def svg_id(source: str) -> str:
    return f"diagram-{cache_key(source)[:12]}"
    # The id doubles as a CSS selector inside the file, so it is stable per diagram and never starts with a digit.


def cached(source: str) -> str | None:
    path = CACHE_DIR / f"{cache_key(source)}.svg"
    return path.read_text(encoding="utf-8") if path.is_file() else None


def store(source: str, svg: str) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{cache_key(source)}.svg").write_text(svg, encoding="utf-8")
    return svg
