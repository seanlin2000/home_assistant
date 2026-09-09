"""Running mermaid-cli (mmdc): finding it and a browser, rendering one diagram to SVG, and turning its stderr into a message with the failing diagram line."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple

MMDC_HINT = "mmdc not found: brew install mermaid-cli (npm install -g @mermaid-js/mermaid-cli on Linux)"
BROWSER_HINT = "mmdc could not start a browser: install Google Chrome, or set PUPPETEER_EXECUTABLE_PATH to a Chrome or Chromium binary"
PARSE_ERROR_LINE = re.compile(r"Parse error on line (\d+)")
LAUNCH_FAILURE = re.compile(r"Could not find (chrome|Chrome)|Failed to launch|--no-sandbox|Browser was not found")
MAC_CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
LINUX_BROWSERS = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
RENDER_TIMEOUT_SECONDS = 120
MERMAID_CONFIG = Path(__file__).with_name("mermaid_config.json")


class RenderResult(NamedTuple):
    ok: bool
    message: str
    diagram_line: int | None


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


def render_svg(mmdc: Path, source: str, work_dir: Path, config: Path | None, svg_id: str) -> str:
    completed = run_mmdc(mmdc, source, work_dir, config, svg_id)
    if completed.returncode != 0:
        raise RuntimeError(parse_failure(completed.stderr or completed.stdout).message)
    return (work_dir / f"{svg_id}.svg").read_text(encoding="utf-8")


def run_mmdc(mmdc: Path, source: str, work_dir: Path, config: Path | None, name: str) -> subprocess.CompletedProcess[str]:
    input_path = work_dir / f"{name}.mmd"
    input_path.write_text(source, encoding="utf-8")
    command = [str(mmdc), "-i", str(input_path), "-o", str(work_dir / f"{name}.svg"), "-q", "-c", str(MERMAID_CONFIG), "--svgId", name]
    # The svg id doubles as a CSS selector inside the file, so callers pass a name that does not start with a digit.
    if config is not None:
        command += ["-p", str(config)]
    return subprocess.run(command, capture_output=True, text=True, timeout=RENDER_TIMEOUT_SECONDS)


def parse_failure(stderr: str) -> RenderResult:
    if LAUNCH_FAILURE.search(stderr):
        raise RendererUnavailable(BROWSER_HINT)
    message = next((line.strip() for line in stderr.splitlines() if line.strip()), "mmdc failed without output")
    matched = PARSE_ERROR_LINE.search(stderr)
    return RenderResult(False, message.removeprefix("Error: "), int(matched.group(1)) if matched else None)
