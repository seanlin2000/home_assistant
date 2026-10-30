"""Expose reddit_search, what people on Reddit say about something, as an MCP tool on the existing server, so the agent sees one tool list.

The tool calls Arctic Shift and the web search while the user waits, so every failure is one sentence telling the model what to do next, never an
exception, as the other tools do. When Arctic Shift never answered, the answer starts with REDDIT_UNAVAILABLE_PREFIX, and the agent loop tells the user
before the model searches the web instead.
"""

import logging
import time
from typing import Annotated

import httpx
from mcp.server.mcpserver import MCPServer
from pydantic import Field

from assistant_core.models import REDDIT_UNAVAILABLE_PREFIX
from reddit_mcp.arctic_shift import ArcticShiftSession, RedditUnavailable
from reddit_mcp.render import threads_text, where
from reddit_mcp.settings import RedditSettings
from reddit_mcp.threads import RedditQuery, TimeRange, WebSearch, subreddit_names, threads_answering

REDDIT_TOOL_NAME = "reddit_search"
MAX_QUERY_CHARS = 120
MAX_SUBREDDIT_CHARS = 40
UNAVAILABLE_MESSAGE = f"{REDDIT_UNAVAILABLE_PREFIX} after several tries. The user has already been told, so do not apologize again; search the web with search_and_read instead."
_LOGGER = logging.getLogger(__name__)

SubredditName = Annotated[str, Field(max_length=MAX_SUBREDDIT_CHARS)]
QueryText = Annotated[str, Field(max_length=MAX_QUERY_CHARS)]


def register_reddit_tools(server: MCPServer, settings: RedditSettings, web_search: WebSearch, transport: httpx.AsyncBaseTransport | None = None) -> None:
    @server.tool(name=REDDIT_TOOL_NAME)
    async def reddit_search(query: QueryText, subreddits: list[SubredditName] | None = None, time_range: TimeRange = "all") -> str:
        """What people on Reddit say about something: the most relevant threads, each with its subreddit, month and year, upvotes, the start of the post, and its top comments. query: a few key words, such as "soup dumplings Flushing" or "Hadestown worth it". subreddits: the subreddits to read, without "r/", such as ["FoodNYC"] or ["Broadway"]; the ones the user named, or one or two that fit the topic (FoodNYC or AskNYC for New York restaurants and things to do, Broadway for shows, nba or nfl for basketball or football); empty for all of Reddit. time_range: "all" for the most relevant threads of any age, or "day", "week", "month", or "year" for only threads that recent, when the user asks what people are saying lately."""
        reddit_query = RedditQuery(subreddits=subreddit_names(subreddits or [], settings.max_subreddits), query=query, time_range=time_range)
        return await reddit_answer(reddit_query, web_search, ArcticShiftSession(settings, transport), settings)


async def reddit_answer(reddit_query: RedditQuery, web_search: WebSearch, arctic_shift: ArcticShiftSession, settings: RedditSettings) -> str:
    try:
        async with arctic_shift:
            threads = await threads_answering(reddit_query, web_search, arctic_shift, settings)
    except RedditUnavailable as error:
        _LOGGER.warning("reddit_search could not reach Arctic Shift: %s", error)
        return UNAVAILABLE_MESSAGE
    if not threads:
        return f'No Reddit threads {where(reddit_query.subreddits)} matched "{reddit_query.query}". Search the web with search_and_read instead.'
    return threads_text(threads, reddit_query, settings, time.time())
