"""Find the Reddit threads that answer a question, and read each one's top comments.

The web search the other tools use ranks the threads, whichever engine it runs on, so this module never names one. Arctic Shift's own keyword search
sorts by date and turned away 14 of 19 searches (measured 2026-10-30), while its thread and comment reads answered 34 of 34, so Arctic Shift only
reads the threads the web search found. The query names the subreddit in its words, "site:reddit.com r/FoodNYC ...", because Brave's API ignores a
path in site: and DuckDuckGo accepts either form.

A time range is asked of the engine and then checked against each thread's date, since an engine may ignore it (SearXNG's DuckDuckGo returns nothing
when given one). For the default range and "all", one search asks for the past year and one for any age, and the threads take turns, so an answer
carries the current discussion and the best thread even when nothing recent matches.
"""

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel

from reddit_mcp.arctic_shift import ArcticShiftSession, RedditComment, RedditPost, RedditUnavailable
from reddit_mcp.settings import RedditSettings
from web_search_mcp.search_engines import SearchEngine
from web_search_mcp.searxng_client import SearchResult

TimeRange = Literal["day", "week", "month", "year", "two_years", "all"]
DEFAULT_TIME_RANGE: TimeRange = "two_years"
SECONDS_IN_TIME_RANGE = {"day": 86_400, "week": 7 * 86_400, "month": 30 * 86_400, "year": 365 * 86_400, "two_years": 730 * 86_400}
# The engine time filters asked for each range, in turn; None asks for any age. Engines know day, week, month, and year only.
ENGINE_TIME_RANGES: dict[str, tuple[str | None, ...]] = {"day": ("day",), "week": ("week",), "month": ("month",), "year": ("year",), "two_years": ("year", None), "all": ("year", None)}
THREAD_ID_IN_URL = re.compile(r"reddit\.com/r/(\w+)/comments/([a-z0-9]{5,10})\b", re.IGNORECASE)
SUBREDDIT_NAME = re.compile(r"^\w{2,21}$")
SPOKEN_PREFIX = re.compile(r"^\s*(/?r\s*/|r slash\s+)", re.IGNORECASE)
_LOGGER = logging.getLogger(__name__)


class RedditThread(BaseModel):
    post: RedditPost
    comments: list[RedditComment]


class RedditQuery(BaseModel):
    subreddits: list[str]
    query: str
    time_range: TimeRange


def subreddit_names(spoken: list[str], max_subreddits: int) -> list[str]:
    """The subreddit names as Reddit's addresses spell them: "r/FoodNYC", "r slash nba", and "Food NYC" become FoodNYC, nba, FoodNYC."""
    names = ["".join(SPOKEN_PREFIX.sub("", name).split()) for name in spoken]
    return list(dict.fromkeys(name for name in names if SUBREDDIT_NAME.match(name)))[:max_subreddits]


async def threads_answering(reddit_query: RedditQuery, web_search: SearchEngine, arctic_shift: ArcticShiftSession, settings: RedditSettings, now: float | None = None) -> list[RedditThread]:
    """The most relevant threads in the time range first, each with its top comments. A thread whose comments could not be read keeps its post;
    RedditUnavailable only when Arctic Shift could not read the threads themselves."""
    since = oldest_allowed(reddit_query.time_range, now or time.time())
    posts = within_range(await arctic_shift.posts_by_id(await web_ranked_thread_ids(reddit_query, web_search)), since)
    chosen = posts[: settings.threads_to_return]
    comments = await asyncio.gather(*(comments_or_none(arctic_shift.top_comments, post.id) for post in chosen))
    return [RedditThread(post=post, comments=thread_comments) for post, thread_comments in zip(chosen, comments, strict=True)]


def oldest_allowed(time_range: str, now: float) -> int | None:
    seconds = SECONDS_IN_TIME_RANGE.get(time_range)
    return int(now - seconds) if seconds else None


async def web_ranked_thread_ids(reddit_query: RedditQuery, web_search: SearchEngine) -> list[str]:
    """Thread ids in the web search's order: within a subreddit the time filters' rankings take turns, then the subreddits take turns, so neither
    recent threads nor one subreddit crowd out the rest. Anywhere on Reddit when no subreddit was named."""
    subreddits: list[str | None] = list(reddit_query.subreddits) or [None]
    per_subreddit = [await subreddit_ranking(subreddit, reddit_query, web_search) for subreddit in subreddits]
    return list(dict.fromkeys(taking_turns(per_subreddit)))


async def subreddit_ranking(subreddit: str | None, reddit_query: RedditQuery, web_search: SearchEngine) -> list[str]:
    query = f"site:reddit.com r/{subreddit} {reddit_query.query}" if subreddit else f"site:reddit.com {reddit_query.query}"
    rankings = [thread_ids(await web_results(web_search, query, engine_range), subreddit) for engine_range in ENGINE_TIME_RANGES[reddit_query.time_range]]
    return list(dict.fromkeys(taking_turns(rankings)))


async def web_results(web_search: SearchEngine, query: str, time_range: str | None) -> list[SearchResult]:
    """The web search's results, or none when it failed, so one failed search leaves the others to answer."""
    try:
        return await web_search.search(query, time_range)
    except Exception as error:  # noqa: BLE001 - a broken search must not fail the threads the other searches found
        _LOGGER.warning("web search for Reddit threads failed: %s: %s", type(error).__name__, error)
        return []


def thread_ids(results: list[SearchResult], subreddit: str | None) -> list[str]:
    """Ids of the thread pages among the results, only from the subreddit when one was named."""
    matches = (THREAD_ID_IN_URL.search(result.url) for result in results)
    return [match.group(2).lower() for match in matches if match and (subreddit is None or match.group(1).lower() == subreddit.lower())]


def taking_turns(rankings: list[list[str]]) -> list[str]:
    """The first of each ranking, then the second of each, and so on."""
    depth = max((len(ranking) for ranking in rankings), default=0)
    return [ranking[index] for index in range(depth) for ranking in rankings if index < len(ranking)]


def within_range(posts: list[RedditPost], since: int | None) -> list[RedditPost]:
    return posts if since is None else [post for post in posts if post.created_utc >= since]


async def comments_or_none(read_comments: Callable[[str], Awaitable[list[RedditComment]]], post_id: str) -> list[RedditComment]:
    try:
        return await read_comments(post_id)
    except RedditUnavailable:
        return []
