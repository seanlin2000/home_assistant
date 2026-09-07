"""The httpx-only MCP client must parse both response encodings and talk to the real web_search_mcp server."""

from pathlib import Path

import httpx
import pytest

from assistant_core.mcp_http import HttpMcpToolBox, find_response, parse_sse
from assistant_core.models import ToolCall


def test_parse_sse_extracts_every_data_event() -> None:
    text = 'event: message\ndata: {"jsonrpc": "2.0", "id": 1, "result": {"ok": true}}\n\ndata: {"jsonrpc": "2.0", "id": 2, "result": {}}\n\n'
    messages = parse_sse(text)
    assert [message["id"] for message in messages] == [1, 2]
    assert find_response(messages, 2) == {"jsonrpc": "2.0", "id": 2, "result": {}}


async def test_lists_and_calls_tools_on_the_real_server(unused_tcp_port: int, tmp_path: Path) -> None:
    from benchmark.mcp_process import McpServerProcess
    from benchmark.records import Services

    services = Services(ollama_host="http://127.0.0.1:11434", searxng_url="http://127.0.0.1:1", mcp_host="127.0.0.1", mcp_port=unused_tcp_port, results_dir="benchmark/results")
    async with McpServerProcess(services, tmp_path / "cache") as url:
        async with HttpMcpToolBox(url) as toolbox:
            names = {tool.name for tool in await toolbox.list_tools()}
            assert {"search_and_read", "web_search", "fetch_page"} <= names
            # SearXNG is pointed at a dead port on purpose: the call must come back as text, not raise.
            result = await toolbox.call(ToolCall(id="c1", name="search_and_read", arguments={"query": "ping"}))
            assert isinstance(result, str) and result


async def test_reports_connection_failure_as_exception() -> None:
    with pytest.raises(httpx.HTTPError):
        async with HttpMcpToolBox("http://127.0.0.1:1/mcp", timeout_seconds=2):
            pass
