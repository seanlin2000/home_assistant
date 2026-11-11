"""Expose Wikipedia lookups as an MCP tool on an existing server, alongside web search, the calculators, and the forecast, so the agent sees one tool list."""

import logging
from typing import Annotated

import httpx
from mcp.server.mcpserver import MCPServer
from pydantic import Field

from wikipedia_mcp.article import render_article
from wikipedia_mcp.client import ArticleStore, WikipediaClient, WikipediaUnavailable
from wikipedia_mcp.passages import select_passages
from wikipedia_mcp.settings import WikipediaSettings

WIKIPEDIA_TOOL_NAME = "wikipedia_lookup"
SERVICE_DOWN_MESSAGE = "Wikipedia error: Wikipedia did not answer. Search the web with search_and_read instead."
NO_TOPIC_MESSAGE = "Wikipedia error: name a topic, such as a person, a team, a place, or a list."
NO_ARTICLE_MESSAGE = 'Wikipedia has no article matching "{topic}". Try a shorter or different topic, or search the web with search_and_read.'
_LOGGER = logging.getLogger(__name__)


def register_wikipedia_tools(server: MCPServer, settings: WikipediaSettings, store: ArticleStore, transport: httpx.AsyncBaseTransport | None = None) -> None:
    client = WikipediaClient(settings, store, transport)

    @server.tool(name=WIKIPEDIA_TOOL_NAME)
    async def wikipedia_lookup(
        topic: Annotated[str, Field(description='subject, e.g. "San Francisco 49ers starting quarterbacks"')],
        focus: Annotated[str, Field(description="words or a year for the part you need; a year means from then on")] = "",
    ) -> str:
        """Read a Wikipedia article, tables as rows. For settled facts, lists and records: who held an office, a country's history, a career, leagues other than the NBA and NFL. For things that change over time, use search_and_read."""
        if not topic.strip():
            return NO_TOPIC_MESSAGE
        try:
            return await looked_up(client, topic, focus or topic, settings.max_words)
        except WikipediaUnavailable as error:
            _LOGGER.warning("%s failed: %s", WIKIPEDIA_TOOL_NAME, error)
            return SERVICE_DOWN_MESSAGE


async def looked_up(client: WikipediaClient, topic: str, focus: str, max_words: int) -> str:
    """The best-matching article, cut to the parts the focus names, with the runners-up listed so the model can ask for one of them instead."""
    titles = await client.search_titles(topic)
    if not titles:
        return NO_ARTICLE_MESSAGE.format(topic=topic)
    best_title, *other_titles = titles
    text = select_passages(render_article(await client.article_html(best_title)), focus, max_words, best_title)
    reply = f"Wikipedia: {best_title}\nURL: {client.article_url(best_title)}\n\n{text}"
    return reply + (f"\n\nOther articles: {'; '.join(other_titles)}" if other_titles else "")
