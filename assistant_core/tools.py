"""Tool access for the agent loop. The agent only ever sees the ToolBox protocol; the MCP wiring lives here."""

import json
from contextlib import AsyncExitStack
from typing import Any, Protocol

from mcp.client.client import Client
from mcp.types import CallToolResult, TextContent

from assistant_core.models import ToolCall, ToolSpec


class ToolBox(Protocol):
    async def list_tools(self) -> list[ToolSpec]: ...

    async def call(self, call: ToolCall) -> str: ...


class McpToolBox:
    """Connects to an MCP server (streamable HTTP by URL, or an in-process server object in tests) and exposes its tools."""

    def __init__(self, server: Any) -> None:
        self._server = server
        self._exit_stack = AsyncExitStack()
        self._client: Client | None = None
        self._tool_specs: list[ToolSpec] | None = None

    async def __aenter__(self) -> "McpToolBox":
        self._client = await self._exit_stack.enter_async_context(Client(self._server))
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._exit_stack.aclose()
        self._client = None

    async def list_tools(self) -> list[ToolSpec]:
        if self._tool_specs is None:
            listed = await self._connected_client().list_tools()
            self._tool_specs = [ToolSpec(name=tool.name, description=tool.description or "", input_schema=tool.input_schema) for tool in listed.tools]
        return self._tool_specs

    async def call(self, call: ToolCall) -> str:
        result = await self._connected_client().call_tool(call.name, call.arguments)
        return render_tool_result(result)

    def _connected_client(self) -> Client:
        if self._client is None:
            raise RuntimeError("McpToolBox must be used inside 'async with'")
        return self._client


def render_tool_result(result: Any) -> str:
    if isinstance(result, CallToolResult):
        text = "\n".join(block.text for block in result.content if isinstance(block, TextContent))
        return f"Tool error: {text}" if result.is_error else text
    return json.dumps(result, default=str)


def find_tool_spec(specs: list[ToolSpec], name: str) -> ToolSpec | None:
    return next((spec for spec in specs if spec.name == name), None)
