"""Find the Reddit threads that answer a question, and read each one's top comments.

Arctic Shift's keyword search sorts by date, not relevance, and turns many queries away, so the web search ranks the threads instead: a site: search per
subreddit found a relevant thread for 8 of 8 test questions, against 3 of 8 for the keyword search (measured 2026-10-29). Arctic Shift then reads the
threads it found, which it held for all 40 tried, back to 2019. The web search's own time filter returned nothing on every try, so a time range is
applied to the threads' dates instead, and Arctic Shift's keyword search adds the recent threads the web search does not rank; it also stands in
when the web search finds none.
"""

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Literal, Protocol

from pydantic import BaseModel

from reddit_mcp.arctic_shift import ArcticShiftSession, RedditComment, RedditPost, RedditUnavailable
from reddit_mcp.settings import RedditSettings
from web_search_mcp.searxng_client import SearchResult

TimeRange = Literal["day", "week", "month", "year", "all"]
SECONDS_IN_TIME_RANGE = {"day": 86_400, "week": 7 * 86_400, "month": 30 * 86_400, "year": 365 * 86_400}
KEYWORD_SEARCH_FALLBACK_RANGE = "year"
THREAD_ID_IN_URL = re.compile(r"reddit\.com/r/(\w+)/comments/([a-z0-9]{5,10})\b", re.IGNORECASE)
SUBREDDIT_NAME = re.compile(r"^\w{2,21}$")
SPOKEN_PREFIX = re.compile(r"^\s*(/?r\s*/|r slash\s+)", re.IGNORECASE)
_LOGGER = logging.getLogger(__name__)


class WebSearch(Protocol):
    async def search(self, query: str, time_range: str | None = None) -> list[SearchResult]: ...


class RedditThread(BaseModel):
    post: RedditPost
    comments: list[RedditComment]


class RedditQuery(BaseModel):
    subreddits: list[str]
    query: str
    time_range: TimeRange


def subreddit_names(spoken: list[str], max_subreddits: int) -> list[str]:
    """The subreddit names as Arctic Shift and Reddit's addresses spell them: "r/FoodNYC", "r slash nba", and "Food NYC" become FoodNYC, nba, FoodNYC."""
    names = ["".join(SPOKEN_PREFIX.sub("", name).split()) for name in spoken]
    return list(dict.fromkeys(name for name in names if SUBREDDIT_NAME.match(name)))[:max_subreddits]


async def threads_answering(reddit_query: RedditQuery, web_search: WebSearch, arctic_shift: ArcticShiftSession, settings: RedditSettings, now: float | None = None) -> list[RedditThread]:
    """The most relevant threads first, each with its top comments. A thread whose comments could not be read keeps its post; RedditUnavailable only
    when Arctic Shift could not read the threads themselves."""
    now = now or time.time()
    since = oldest_allowed(reddit_query.time_range, now)
    posts = within_range(await arctic_shift.posts_by_id(await web_ranked_thread_ids(reddit_query, web_search)), since)
    if since is not None or not posts:
        posts = await with_keyword_matches(posts, reddit_query, arctic_shift, since or oldest_allowed(KEYWORD_SEARCH_FALLBACK_RANGE, now))
    chosen = posts[: settings.threads_to_return]
    comments = await asyncio.gather(*(comments_or_none(arctic_shift.top_comments, post.id) for post in chosen))
    return [RedditThread(post=post, comments=thread_comments) for post, thread_comments in zip(chosen, comments, strict=True)]


def oldest_allowed(time_range: str, now: float) -> int | None:
    seconds = SECONDS_IN_TIME_RANGE.get(time_range)
    return int(now - seconds) if seconds else None


async def web_ranked_thread_ids(reddit_query: RedditQuery, web_search: WebSearch) -> list[str]:
    """Thread ids in the web search's order, the subreddits' best threads taking turns; anywhere on Reddit when no subreddit was named."""
    sites = [f"site:reddit.com/r/{subreddit}" for subreddit in reddit_query.subreddits] or ["site:reddit.com"]
    ranked_per_site = [thread_ids(await web_results(web_search, f"{site} {reddit_query.query}"), reddit_query.subreddits) for site in sites]
    return list(dict.fromkeys(taking_turns(ranked_per_site)))


async def web_results(web_search: WebSearch, query: str) -> list[SearchResult]:
    """The web search's results, or none when it failed, so Arctic Shift's keyword search stands in."""
    try:
        return await web_search.search(query)
    except Exception as error:  # noqa: BLE001 - a broken web search must leave the keyword search to answer
        _LOGGER.warning("web search for Reddit threads failed: %s: %s", type(error).__name__, error)
        return []


def thread_ids(results: list[SearchResult], subreddits: list[str]) -> list[str]:
    """Ids of the thread pages among the results, only from the named subreddits when any were named."""
    wanted = {subreddit.lower() for subreddit in subreddits}
    matches = (THREAD_ID_IN_URL.search(result.url) for result in results)
    return [match.group(2).lower() for match in matches if match and (not wanted or match.group(1).lower() in wanted)]


def taking_turns(rankings: list[list[str]]) -> list[str]:
    """The first of each ranking, then the second of each, and so on, so one subreddit's threads do not crowd out another's."""
    depth = max((len(ranking) for ranking in rankings), default=0)
    return [ranking[index] for index in range(depth) for ranking in rankings if index < len(ranking)]


def within_range(posts: list[RedditPost], since: int | None) -> list[RedditPost]:
    return posts if since is None else [post for post in posts if post.created_utc >= since]


async def with_keyword_matches(posts: list[RedditPost], reddit_query: RedditQuery, arctic_shift: ArcticShiftSession, since: int) -> list[RedditPost]:
    """The web search's threads, then Arctic Shift's keyword matches. When Arctic Shift turns every search away, the web search's threads answer
    alone; with none of those either, Reddit could not be reached."""
    try:
        return merged(posts, await keyword_matches(reddit_query, arctic_shift, since))
    except RedditUnavailable:
        if posts:
            return posts
        raise


async def keyword_matches(reddit_query: RedditQuery, arctic_shift: ArcticShiftSession, since: int) -> list[RedditPost]:
    """Arctic Shift's matches in every named subreddit, the most discussed first. A subreddit it turns away adds none; RedditUnavailable only when
    it turned away every one."""
    searches = [arctic_shift.search_posts(subreddit, reddit_query.query, since) for subreddit in reddit_query.subreddits]
    found = await asyncio.gather(*searches, return_exceptions=True)
    unexpected = [result for result in found if isinstance(result, BaseException) and not isinstance(result, RedditUnavailable)]
    if unexpected:
        raise unexpected[0]
    failures = [result for result in found if isinstance(result, RedditUnavailable)]
    if failures and len(failures) == len(found):
        raise failures[0]
    posts = [post for result in found if isinstance(result, list) for post in result]
    return sorted(posts, key=lambda post: (post.num_comments, post.score), reverse=True)


def merged(first: list[RedditPost], then: list[RedditPost]) -> list[RedditPost]:
    seen = {post.id for post in first}
    return [*first, *(post for post in then if post.id not in seen)]


async def comments_or_none(read_comments: Callable[[str], Awaitable[list[RedditComment]]], post_id: str) -> list[RedditComment]:
    try:
        return await read_comments(post_id)
    except RedditUnavailable:
        return []
