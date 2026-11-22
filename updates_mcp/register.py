"""Expose the user's updates as one MCP tool on the shared tool server, so one call covers everything the user follows: a small model manages one
call far more reliably than the five tool families it would otherwise need.

The sections are read at once, each from its own source, and come back in a fixed order under their own headings. Which sections are off unless
asked for is a setting, applied on every call (updates_mcp/sections.py says why it is not the skip argument's default).
"""

import asyncio
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from sports_mcp.render import clipped
from updates_mcp.blocks import UpdateSources, section_blocks
from updates_mcp.sections import UpdateSection, include_description, shown_sections, tool_description
from updates_mcp.settings import UpdatesSettings

UPDATES_TOOL_NAME = "updates"
BLOCK_SEPARATOR = "\n\n"


def register_updates_tools(server: MCPServer, settings: UpdatesSettings, sources: UpdateSources) -> None:
    @server.tool(name=UPDATES_TOOL_NAME, description=tool_description(settings.default_off))
    async def updates(
        skip: Annotated[list[UpdateSection] | None, Field(description="sections the user said to leave out")] = None,
        include: Annotated[list[UpdateSection] | None, Field(description=include_description(settings.default_off))] = None,
    ) -> str:
        sections = shown_sections(skip or [], include or [], settings.default_off)
        return clipped(await updates_text(sections, sources), settings.max_words)


async def updates_text(sections: list[UpdateSection], sources: UpdateSources) -> str:
    blocks = await asyncio.gather(*(section_blocks(section, sources) for section in sections))
    return BLOCK_SEPARATOR.join(block for section in blocks for block in section) or "Every section was skipped; tell the user there is nothing to report."
