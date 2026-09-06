"""A minimal MCP client over streamable HTTP using only httpx.

The benchmark uses the official `mcp` package (McpToolBox). Home Assistant pins its own, older `mcp` release for its built-in MCP integration, so the
component cannot rely on that package's API. The protocol itself is small: JSON-RPC 2.0 over POST, with responses arriving either as JSON or as a
server-sent-events stream. This client speaks exactly that subset: initialize, tools/list, tools/call.
"""

import json
from typing import Any

import httpx

from assistant_core.models import ToolCall, ToolSpec

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "studio_assistant", "version": "0.1.0"}
SESSION_HEADER = "mcp-session-id"


class McpProtocolError(RuntimeError):
    """The server answered with a JSON-RPC error or an unreadable response."""


class HttpMcpToolBox:
    """Implements the ToolBox protocol against an MCP streamable-HTTP endpoint such as web_search_mcp."""

    def __init__(self, url: str, client: httpx.AsyncClient | None = None, timeout_seconds: float = 60.0) -> None:
        self._url = url
        self._client = client
        self._owns_client = client is None
        self._timeout = timeout_seconds
        self._session_id: str | None = None
        self._next_id = 1
        self._tool_specs: list[ToolSpec] | None = None

    async def __aenter__(self) -> "HttpMcpToolBox":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        await self._initialize()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
        self._client = None
        self._session_id = None

    async def list_tools(self) -> list[ToolSpec]:
        if self._tool_specs is None:
            result = await self._request("tools/list", {})
            self._tool_specs = [ToolSpec(name=tool["name"], description=tool.get("description", ""), input_schema=tool.get("inputSchema", {})) for tool in result.get("tools", [])]
        return self._tool_specs

    async def call(self, call: ToolCall) -> str:
        result = await self._request("tools/call", {"name": call.name, "arguments": call.arguments})
        text = "\n".join(block.get("text", "") for block in result.get("content", []) if block.get("type") == "text")
        return f"Tool error: {text}" if result.get("isError") else text

    async def _initialize(self) -> None:
        params = {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": CLIENT_INFO}
        await self._request("initialize", params)
        await self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        response = await self._post({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        message = find_response(response, request_id)
        if "error" in message:
            raise McpProtocolError(f"{method} failed: {message['error']}")
        return message.get("result", {})

    async def _post(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        if self._client is None:
            raise RuntimeError("HttpMcpToolBox must be used inside 'async with'")
        headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json", "MCP-Protocol-Version": PROTOCOL_VERSION}
        if self._session_id:
            headers[SESSION_HEADER] = self._session_id
        response = await self._client.post(self._url, json=body, headers=headers, timeout=self._timeout)
        response.raise_for_status()
        if SESSION_HEADER in response.headers:
            self._session_id = response.headers[SESSION_HEADER]
        return parse_messages(response)


def parse_messages(response: httpx.Response) -> list[dict[str, Any]]:
    """Return every JSON-RPC message in the response, whether it came back as plain JSON or as an SSE stream."""
    content_type = response.headers.get("content-type", "")
    if response.status_code == 202 or not response.content:
        return []
    if content_type.startswith("application/json"):
        payload = response.json()
        return payload if isinstance(payload, list) else [payload]
    if content_type.startswith("text/event-stream"):
        return parse_sse(response.text)
    raise McpProtocolError(f"unexpected content type {content_type!r}")


def parse_sse(text: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    data_lines: list[str] = []
    for line in text.splitlines() + [""]:
        if line.startswith("data:"):
            data_lines.append(line[5:].strip())
        elif line == "" and data_lines:
            messages.append(json.loads("\n".join(data_lines)))
            data_lines = []
    return messages


def find_response(messages: list[dict[str, Any]], request_id: int) -> dict[str, Any]:
    for message in messages:
        if message.get("id") == request_id:
            return message
    raise McpProtocolError(f"no response with id {request_id} in {messages!r}")
