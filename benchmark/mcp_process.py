"""Runs web_search_mcp as a child process for the duration of a benchmark run, with a per-run cache so every candidate sees identical search results."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from assistant_core.models import ToolSpec
from assistant_core.tools import McpToolBox
from benchmark.records import Services

READINESS_ATTEMPTS = 40
READINESS_INTERVAL_SECONDS = 0.5


class McpServerProcess:
    def __init__(self, services: Services, cache_dir: Path) -> None:
        self._services = services
        self._cache_dir = cache_dir
        self._process: subprocess.Popen | None = None

    async def __aenter__(self) -> str:
        env = {
            **os.environ,
            "WEB_SEARCH_CACHE_DIR": str(self._cache_dir),
            "WEB_SEARCH_PORT": str(self._services.mcp_port),
            "WEB_SEARCH_HOST": self._services.mcp_host,
            "WEB_SEARCH_SEARXNG_URL": self._services.searxng_url,
        }
        self._process = subprocess.Popen([sys.executable, "-m", "web_search_mcp.server"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await wait_until_ready(self._services.mcp_url)
        return self._services.mcp_url

    async def __aexit__(self, *exc_info: object) -> None:
        if self._process is not None:
            self._process.terminate()
            self._process.wait(timeout=10)


async def wait_until_ready(mcp_url: str) -> list[ToolSpec]:
    last_error: Exception | None = None
    for _ in range(READINESS_ATTEMPTS):
        try:
            async with McpToolBox(mcp_url) as toolbox:
                return await toolbox.list_tools()
        except Exception as error:
            last_error = error
            await asyncio.sleep(READINESS_INTERVAL_SECONDS)
    raise RuntimeError(f"web_search_mcp did not become ready at {mcp_url}: {last_error}")
