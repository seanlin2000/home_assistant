"""Expose the user's pulled email newsletters as MCP tools on the existing server (design doc v2/14 section 3.5). They read only the files the hourly
pull writes (newsletters_mcp/pull.py), never Gmail; see newsletters_mcp/answers.py."""

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from newsletters_mcp.answers import NewsletterAnswers
from newsletters_mcp.settings import NewslettersSettings

NEWSLETTERS_LIST_TOOL_NAME = "newsletters_list"
NEWSLETTER_SUMMARIZE_TOOL_NAME = "newsletter_summarize"
NEWSLETTER_READ_TOOL_NAME = "newsletter_read"
MAX_DATE_CHARS = 10
MAX_NAME_CHARS = 80
MAX_TOPIC_CHARS = 40
DATE_DESCRIPTION = '"today", "yesterday", or YYYY-MM-DD'


def register_newsletters_tools(server: MCPServer, settings: NewslettersSettings) -> None:
    answers = NewsletterAnswers(settings)

    @server.tool(name=NEWSLETTERS_LIST_TOOL_NAME)
    async def newsletters_list(
        date: Annotated[str, Field(max_length=MAX_DATE_CHARS, description=DATE_DESCRIPTION)] = "today",
        newsletter: Annotated[str, Field(max_length=MAX_NAME_CHARS, description='one newsletter, as the user named it, e.g. "Money Stuff"; empty for all')] = "",
        topic: Annotated[str, Field(max_length=MAX_TOPIC_CHARS, description='only the sections that mention this, e.g. "Nvidia"; empty for all')] = "",
    ) -> str:
        """The user's own email newsletters for a day: each issue's time, publication, headline and section names. Use this first for anything about the user's newsletters, and to find which ones mention a topic. Then call newsletter_summarize for what an issue or section says."""
        return answers.listing(date, newsletter, topic)

    @server.tool(name=NEWSLETTER_SUMMARIZE_TOOL_NAME)
    async def newsletter_summarize(
        newsletter: Annotated[str, Field(max_length=MAX_NAME_CHARS, description='as the user named it, e.g. "Money Stuff" or "The Morning"')],
        date: Annotated[str, Field(max_length=MAX_DATE_CHARS, description=DATE_DESCRIPTION)] = "today",
        section: Annotated[str, Field(max_length=MAX_NAME_CHARS, description="one section's name; empty for the whole issue")] = "",
    ) -> str:
        """The text of one of the user's newsletters, or one section of it, to summarize in your own words. Keep what a source reports apart from the author's own opinion, say when the author is being ironic or posing a hypothetical, and give numbers as written. Lines starting with ">" are quotations."""
        return answers.text(newsletter, date, section)

    @server.tool(name=NEWSLETTER_READ_TOOL_NAME)
    async def newsletter_read(
        newsletter: Annotated[str, Field(max_length=MAX_NAME_CHARS, description="as the user named it; empty to continue the last reading")] = "",
        date: Annotated[str, Field(max_length=MAX_DATE_CHARS, description=DATE_DESCRIPTION)] = "today",
        section: Annotated[str, Field(max_length=MAX_NAME_CHARS, description='one section\'s name; empty for the start; "next" to continue the last reading')] = "",
    ) -> str:
        """Read one of the user's newsletters aloud, word for word, about three minutes at a time; the text goes straight to the speaker. Only when the user asks to hear it read ("read me Money Stuff", "read the Procurement section"). For a summary or what it says, call newsletter_summarize. For "continue" or "keep reading", call with section "next"."""
        return answers.reading(newsletter, date, section)
