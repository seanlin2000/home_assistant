"""Runs web_search_mcp as a child process for the duration of a benchmark run, with a per-run cache so every candidate sees identical search results."""

import asyncio
import os
import socket
import subprocess
import sys
from pathlib import Path

from assistant_core.models import ToolSpec
from assistant_core.tools import McpToolBox
from benchmark.records import Services

READINESS_ATTEMPTS = 40
READINESS_INTERVAL_SECONDS = 0.5
REQUIRED_TOOLS = frozenset({"search_and_read", "web_search", "fetch_page", "calculate", "percent", "convert"})


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
        }
        self._process = subprocess.Popen([sys.executable, "-m", "web_search_mcp.server"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        tools = await wait_until_ready(self._services.mcp_url)
        if self._process.poll() is not None:
            raise RuntimeError(f"web_search_mcp exited with code {self._process.returncode}; something else answered at {self._services.mcp_url}")
        names = {tool.name for tool in tools}
        if not REQUIRED_TOOLS <= names:
            raise RuntimeError(f"the server at {self._services.mcp_url} is not this run's server: it lacks {sorted(REQUIRED_TOOLS - names)}")
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
