"""Rendering every Mermaid block through mermaid-cli (mmdc) so a diagram that will not draw is reported at its line in the markdown."""

import json
import os
import re
import shutil
import subprocess
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import NamedTuple

from deslop.checks import Finding
from manual_checks.blocks import MermaidBlock, file_line

MMDC_HINT = "mmdc not found: brew install mermaid-cli (npm install -g @mermaid-js/mermaid-cli on Linux)"
BROWSER_HINT = "mmdc could not start a browser: install Google Chrome, or set PUPPETEER_EXECUTABLE_PATH to a Chrome or Chromium binary"
PARSE_ERROR_LINE = re.compile(r"Parse error on line (\d+)")
LAUNCH_FAILURE = re.compile(r"Could not find (chrome|Chrome)|Failed to launch|--no-sandbox|Browser was not found")
MAC_CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
LINUX_BROWSERS = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
RENDER_TIMEOUT_SECONDS = 120
MERMAID_CONFIG = Path(__file__).with_name("mermaid_config.json")
PNG_WIDTH = "1600"


class RenderResult(NamedTuple):
    ok: bool
    message: str
    diagram_line: int | None


Renderer = Callable[[str], RenderResult]


class RendererUnavailable(RuntimeError):
    pass


def find_mmdc() -> Path:
    found = shutil.which("mmdc")
    if found is None:
        raise RendererUnavailable(MMDC_HINT)
    return Path(found)


def find_browser() -> Path | None:
    configured = os.environ.get("PUPPETEER_EXECUTABLE_PATH")
    if configured:
        return Path(configured)
    if MAC_CHROME.is_file():
        return MAC_CHROME
    return next((Path(found) for name in LINUX_BROWSERS if (found := shutil.which(name))), None)


def write_puppeteer_config(work_dir: Path, browser: Path | None, sandbox: bool) -> Path | None:
    settings: dict[str, object] = {}
    if browser is not None:
        settings["executablePath"] = str(browser)
    if not sandbox:
        settings["args"] = ["--no-sandbox", "--disable-setuid-sandbox"]
    if not settings:
        return None
    config = work_dir / "puppeteer.json"
    config.write_text(json.dumps(settings), encoding="utf-8")
    return config


def mmdc_renderer(mmdc: Path, work_dir: Path, config: Path | None) -> Renderer:
    return lambda source: render_source(mmdc, source, work_dir, config)


def render_source(mmdc: Path, source: str, work_dir: Path, config: Path | None) -> RenderResult:
    completed = run_mmdc(mmdc, source, work_dir, config, uuid.uuid4().hex)
    if completed.returncode == 0:
        return RenderResult(True, "", None)
    return parse_failure(completed.stderr or completed.stdout)


def render_svg(mmdc: Path, source: str, work_dir: Path, config: Path | None, svg_id: str) -> str:
    completed = run_mmdc(mmdc, source, work_dir, config, svg_id)
    if completed.returncode != 0:
        raise RuntimeError(parse_failure(completed.stderr or completed.stdout).message)
    return (work_dir / f"{svg_id}.svg").read_text(encoding="utf-8")


def render_png(mmdc: Path, source: str, work_dir: Path, config: Path | None, out_path: Path) -> None:
    run_mmdc(mmdc, source, work_dir, config, f"diagram-{out_path.stem}", out_path)
    # The SVG id is also a CSS selector inside the file, so it must not start with a page's leading digit.


def run_mmdc(mmdc: Path, source: str, work_dir: Path, config: Path | None, name: str, output: Path | None = None) -> subprocess.CompletedProcess[str]:
    input_path = work_dir / f"{name}.mmd"
    input_path.write_text(source, encoding="utf-8")
    output = output or work_dir / f"{name}.svg"
    command = [str(mmdc), "-i", str(input_path), "-o", str(output), "-q", "-c", str(MERMAID_CONFIG), "--svgId", name]
    if output.suffix == ".png":
        command += ["-w", PNG_WIDTH, "-b", "white"]
    if config is not None:
        command += ["-p", str(config)]
    return subprocess.run(command, capture_output=True, text=True, timeout=RENDER_TIMEOUT_SECONDS)


def parse_failure(stderr: str) -> RenderResult:
    if LAUNCH_FAILURE.search(stderr):
        raise RendererUnavailable(BROWSER_HINT)
    message = next((line.strip() for line in stderr.splitlines() if line.strip()), "mmdc failed without output")
    matched = PARSE_ERROR_LINE.search(stderr)
    return RenderResult(False, message.removeprefix("Error: "), int(matched.group(1)) if matched else None)


def render_findings(blocks: list[MermaidBlock], renderer: Renderer, jobs: int) -> list[Finding]:
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        results = list(pool.map(renderer, [block.source for block in blocks]))
    return [Finding(block.path, file_line(block, result.diagram_line), result.message) for block, result in zip(blocks, results) if not result.ok]
