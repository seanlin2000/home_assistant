"""Expose Wikipedia lookups as an MCP tool on an existing server, alongside web search, the calculators, and the forecast, so the agent sees one tool list."""

import logging

import httpx
from mcp.server.mcpserver import MCPServer

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
    async def wikipedia_lookup(topic: str, focus: str = "") -> str:
        """Read the encyclopedia article on a topic, for settled facts, lists, records, and histories: who held an office, a team's seasons or starting players, a person's career, a country's history. Tables come back as rows. topic: what the article is about, e.g. "San Francisco 49ers starting quarterbacks". focus: optional words or a year naming the part you need; a year means that year onward, e.g. "2000". Not for prices, news, or anything that changes week to week; search the web for those."""
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
    text = select_passages(render_article(await client.article_html(best_title)), focus, max_words)
    reply = f"Wikipedia: {best_title}\nURL: {client.article_url(best_title)}\n\n{text}"
    return reply + (f"\n\nOther articles: {'; '.join(other_titles)}" if other_titles else "")
