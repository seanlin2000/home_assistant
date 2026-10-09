"""The tool server's plain HTTP route beside /mcp: GET /healthz names the tools, and only requests that name this machine are served."""

import httpx
import pytest

from web_search_mcp.server import build_server, transport_security_for
from web_search_mcp.settings import SearchSettings


def client_for(allowed_hosts: str = "") -> httpx.AsyncClient:
    settings = SearchSettings(searxng_url="http://127.0.0.1:1", allowed_hosts=allowed_hosts)
    server = build_server(settings)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=server.streamable_http_app(transport_security=transport_security_for(settings))), base_url="http://testserver")


@pytest.mark.asyncio
async def test_healthz_lists_every_required_tool() -> None:
    async with client_for() as client:
        response = await client.get("/healthz")
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["missing"] == []
    assert {"search_and_read", "calculate", "percent"} <= set(body["tools"])


@pytest.mark.asyncio
async def test_host_allow_list_turns_away_other_names_and_browser_origins() -> None:
    async with client_for(allowed_hosts="mac.lan:8765, 127.0.0.1:8765") as client:
        assert (await client.get("/healthz", headers={"host": "evil.example:8765"})).status_code == 421
        assert (await client.get("/healthz", headers={"host": "mac.lan:8765", "origin": "http://mac.lan:8765"})).status_code == 421
        assert (await client.get("/healthz", headers={"host": "127.0.0.1:8765"})).status_code == 200


@pytest.mark.asyncio
async def test_host_allow_list_also_guards_the_mcp_endpoint() -> None:
    settings = SearchSettings(searxng_url="http://127.0.0.1:1", allowed_hosts="mac.lan:8765")
    app = build_server(settings).streamable_http_app(transport_security=transport_security_for(settings))
    mcp_headers = {"content-type": "application/json", "accept": "application/json, text/event-stream"}
    async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        assert (await client.post("/mcp", content=b"{}", headers=mcp_headers | {"host": "evil.example:8765"})).status_code == 421
        assert (await client.post("/mcp", content=b"{}", headers=mcp_headers | {"host": "mac.lan:8765"})).status_code != 421
