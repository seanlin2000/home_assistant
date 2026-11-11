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
from reddit_mcp.threads import DEFAULT_TIME_RANGE, RedditQuery, TimeRange, subreddit_names, threads_answering
from web_search_mcp.search_engines import SearchEngine

REDDIT_TOOL_NAME = "reddit_search"
MAX_QUERY_CHARS = 120
MAX_SUBREDDIT_CHARS = 40
UNAVAILABLE_MESSAGE = f"{REDDIT_UNAVAILABLE_PREFIX} after several tries. The user has already been told, so do not apologize again; search the web with search_and_read instead."
_LOGGER = logging.getLogger(__name__)

SPOKEN_TIME_RANGES = {
    "day": "from the past day",
    "week": "from the past week",
    "month": "from the past month",
    "year": "from the past year",
    "two_years": "from the past two years",
    "all": "of any age",
}

SubredditName = Annotated[str, Field(max_length=MAX_SUBREDDIT_CHARS)]
QueryText = Annotated[str, Field(max_length=MAX_QUERY_CHARS)]


def register_reddit_tools(server: MCPServer, settings: RedditSettings, web_search: SearchEngine, transport: httpx.AsyncBaseTransport | None = None) -> None:
    @server.tool(name=REDDIT_TOOL_NAME)
    async def reddit_search(
        query: Annotated[QueryText, Field(description='a few key words, e.g. "soup dumplings Flushing"')],
        subreddits: Annotated[
            list[SubredditName] | None,
            Field(description='without "r/": ones the user named, or one or two that fit (FoodNYC, AskNYC, Broadway, nba, nfl); empty for all'),
        ] = None,
        time_range: Annotated[TimeRange, Field(description="day to year only if the user asks about recent posts; all for older too")] = DEFAULT_TIME_RANGE,
    ) -> str:
        """What people on Reddit say: top threads with subreddit, date, upvotes, post and top comments. Answer with what they agree on and recommend most, saying it is from Reddit; give a thread's age if over a year. If it says Reddit did not answer, the user was already told: do not apologize, search the web as it says."""
        reddit_query = RedditQuery(subreddits=subreddit_names(subreddits or [], settings.max_subreddits), query=query, time_range=time_range)
        return await reddit_answer(reddit_query, web_search, ArcticShiftSession(settings, transport), settings)


async def reddit_answer(reddit_query: RedditQuery, web_search: SearchEngine, arctic_shift: ArcticShiftSession, settings: RedditSettings) -> str:
    try:
        async with arctic_shift:
            threads = await threads_answering(reddit_query, web_search, arctic_shift, settings)
    except RedditUnavailable as error:
        _LOGGER.warning("reddit_search could not reach Arctic Shift: %s", error)
        return UNAVAILABLE_MESSAGE
    if not threads:
        return f'No Reddit threads {where(reddit_query.subreddits)} {SPOKEN_TIME_RANGES[reddit_query.time_range]} matched "{reddit_query.query}". Search the web with search_and_read instead.'
    return threads_text(threads, reddit_query, settings, time.time())
