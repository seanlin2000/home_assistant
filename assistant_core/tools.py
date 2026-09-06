"""Tool access for the agent loop. The agent only ever sees the ToolBox protocol; the MCP wiring lives here.

The `mcp` package is imported lazily, inside McpToolBox, because this module is also vendored into the Home Assistant component. Home Assistant
pins its own, older `mcp` (1.x, a different client API) and the component talks to the tool server through assistant_core.mcp_http instead, so
importing `mcp` at module load would break the component for a class it never uses.
"""

import json
from contextlib import AsyncExitStack
from typing import Any, Protocol

from assistant_core.models import ToolCall, ToolSpec


class ToolBox(Protocol):
    async def list_tools(self) -> list[ToolSpec]: ...

    async def call(self, call: ToolCall) -> str: ...


class McpToolBox:
    """Connects to an MCP server (streamable HTTP by URL, or an in-process server object in tests) and exposes its tools."""

    def __init__(self, server: Any) -> None:
        self._server = server
        self._exit_stack = AsyncExitStack()
        self._client: Any = None
        self._tool_specs: list[ToolSpec] | None = None

    async def __aenter__(self) -> "McpToolBox":
        from mcp.client.client import Client

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

    def _connected_client(self) -> Any:
        if self._client is None:
            raise RuntimeError("McpToolBox must be used inside 'async with'")
        return self._client


def render_tool_result(result: Any) -> str:
    """Flatten an MCP CallToolResult to the text the model reads; anything else is serialised as JSON."""
    content = getattr(result, "content", None)
    if content is None:
        return json.dumps(result, default=str)
    text = "\n".join(block.text for block in content if getattr(block, "type", None) == "text")
    return f"Tool error: {text}" if getattr(result, "is_error", False) else text


def find_tool_spec(specs: list[ToolSpec], name: str) -> ToolSpec | None:
    return next((spec for spec in specs if spec.name == name), None)
