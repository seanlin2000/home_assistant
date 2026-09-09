"""Turning a finished SVG into a PNG with a headless Chrome, at the drawing's natural size and twice the pixel density so small labels stay legible.

The SVG is wrapped in a one-line HTML page first: Chrome sizes a bare SVG document by its viewport rather than its viewBox, which left short diagrams blank."""

import re
import subprocess
from pathlib import Path

from diagrams.mmdc import BROWSER_HINT, RENDER_TIMEOUT_SECONDS, RendererUnavailable, find_browser

NATURAL_WIDTH = re.compile(r"max-width: (\d+(?:\.\d+)?)px")
PAGE = '<!doctype html><html><body style="margin: 0; background: #ffffff">{svg}</body></html>'
VIEW_BOX = re.compile(r'viewBox="[\d.\-]+ [\d.\-]+ ([\d.\-]+) ([\d.\-]+)"')
SCALE = "2"
MARGIN = 2


def screenshot(svg_path: Path, png_path: Path, sandbox: bool) -> None:
    browser = find_browser()
    if browser is None:
        raise RendererUnavailable(BROWSER_HINT)
    svg = svg_path.read_text(encoding="utf-8")
    page_path = svg_path.with_suffix(".html")
    page_path.write_text(PAGE.format(svg=svg), encoding="utf-8")
    width, height = natural_size(svg)
    subprocess.run(chrome_command(browser, page_path, png_path, width, height, sandbox), capture_output=True, text=True, timeout=RENDER_TIMEOUT_SECONDS, check=True)


def natural_size(svg: str) -> tuple[int, int]:
    width = NATURAL_WIDTH.search(svg)
    box = VIEW_BOX.search(svg)
    if width is None or box is None:
        raise ValueError("the SVG has no max-width style or viewBox to size the screenshot from")
    return int(float(width.group(1))) + MARGIN, int(float(box.group(2))) + MARGIN


def chrome_command(browser: Path, page_path: Path, png_path: Path, width: int, height: int, sandbox: bool) -> list[str]:
    command = [str(browser), "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--force-device-scale-factor={SCALE}", f"--window-size={width},{height}", f"--screenshot={png_path}"]
    if not sandbox:
        command += ["--no-sandbox", "--disable-setuid-sandbox"]
    return command + [page_path.resolve().as_uri()]
