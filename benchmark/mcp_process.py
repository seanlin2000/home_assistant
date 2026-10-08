"""Runs web_search_mcp as a child process for the duration of a benchmark run, with a per-run cache so every candidate sees identical search results
and the same home forecast."""

import asyncio
import os
import socket
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from assistant_core.models import REQUIRED_TOOL_NAMES, WEATHER_TOOL_NAMES, ToolSpec
from assistant_core.tools import McpToolBox
from benchmark.records import Services
from web_search_mcp.fixtures import FIXTURE_ROUTE

FIXTURES_DIR = Path("benchmark/fixtures/pages")
READINESS_ATTEMPTS = 40
READINESS_INTERVAL_SECONDS = 0.5


def ensure_port_free(host: str, port: int) -> None:
    """Refuse to start if the port is taken. A stale or foreign server there would answer the readiness check and silently serve a different tool set,
    which is exactly what happened on 2026-09-06: a leftover pass-1 server without the calculator tools took every pass-2 tool call."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        if probe.connect_ex((host if host != "0.0.0.0" else "127.0.0.1", port)) == 0:
            raise RuntimeError(f"port {port} is already in use; stop whatever is listening there (lsof -nP -iTCP:{port}) before running the benchmark")


class McpServerProcess:
    def __init__(self, services: Services, cache_dir: Path) -> None:
        self._services = services
        self._cache_dir = cache_dir
        self._process: subprocess.Popen | None = None

    async def __aenter__(self) -> str:
        ensure_port_free(self._services.mcp_host, self._services.mcp_port)
        env = {
            **os.environ,
            "WEB_SEARCH_CACHE_DIR": str(self._cache_dir),
            "WEB_SEARCH_PORT": str(self._services.mcp_port),
            "WEB_SEARCH_HOST": self._services.mcp_host,
            "WEB_SEARCH_SEARXNG_URL": self._services.searxng_url,
            "WEB_SEARCH_FIXTURES_DIR": str(FIXTURES_DIR.resolve()),
            **self._services.weather_home.environment(),
        }
        self._process = subprocess.Popen([sys.executable, "-m", "web_search_mcp.server"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        tools = await wait_until_ready(self._services.mcp_url)
        if self._process.poll() is not None:
            raise RuntimeError(f"web_search_mcp exited with code {self._process.returncode}; something else answered at {self._services.mcp_url}")
        missing = sorted((REQUIRED_TOOL_NAMES | WEATHER_TOOL_NAMES) - {tool.name for tool in tools})
        if missing:
            raise RuntimeError(f"the server at {self._services.mcp_url} is not this run's server: it lacks {missing}")
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


@asynccontextmanager
async def fixture_selected(mcp_url: str, fixture: str | None) -> AsyncIterator[None]:
    """Serve a question's page set for every search while it runs, then the live web again (design doc v2/01 section 3.4)."""
    if fixture is None:
        yield
        return
    route = str(httpx.URL(mcp_url).copy_with(path=FIXTURE_ROUTE))
    async with httpx.AsyncClient(timeout=10) as client:
        (await client.post(route, json={"set": fixture})).raise_for_status()
        try:
            yield
        finally:
            await client.post(route, json={"set": None})
