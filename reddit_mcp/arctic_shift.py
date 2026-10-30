"""Reads Reddit posts and comments from Arctic Shift (github.com/ArthurHeitmann/arctic_shift), a free archive of Reddit with a JSON API.

Arctic Shift answers a busy moment with HTTP 422 "Timeout. Maybe slow down a bit" or 429, usually within a second, so every request is retried after
a short wait, within one budget for the whole tool call. The host is fixed by settings, not chosen by the model, so requests skip the public-address
guard that fetch_page applies, as the ESPN and Wikipedia clients do; a redirect is refused instead of followed.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from reddit_mcp.settings import RedditSettings

OK = 200
RETRYABLE_STATUSES = frozenset({422, 429, 500, 502, 503, 504})
POST_FIELDS = "id,subreddit,title,selftext,score,num_comments,created_utc,permalink"


class RedditUnavailable(RuntimeError):
    """Arctic Shift did not answer within the attempts and the time budget, refused, redirected, or answered in a shape the tool cannot read."""


class RedditPost(BaseModel):
    id: str
    subreddit: str
    title: str
    selftext: str = ""
    score: int = 0
    num_comments: int = 0
    created_utc: float
    permalink: str = ""


class RedditComment(BaseModel):
    body: str
    score: int = 0


class ArcticShiftSession:
    """One tool call's connection to Arctic Shift, with its retry budget counted from the moment the session opens."""

    def __init__(
        self,
        settings: RedditSettings,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._transport = transport  # injectable so tests serve recorded answers without a socket
        self._sleep = sleep
        self._clock = clock
        self._deadline = 0.0
        self._client: httpx.AsyncClient | None = None
        self._comment_reads = asyncio.Semaphore(settings.comment_reads_at_a_time)
        self.retries = 0

    async def __aenter__(self) -> "ArcticShiftSession":
        self._deadline = self._clock() + self._settings.total_budget_seconds
        headers = {"User-Agent": self._settings.user_agent}
        self._client = httpx.AsyncClient(timeout=self._settings.timeout_seconds, follow_redirects=False, headers=headers, transport=self._transport)
        return self

    async def __aexit__(self, error_type: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def search_posts(self, subreddit: str, query: str, after_epoch_seconds: int) -> list[RedditPost]:
        """Posts in one subreddit since that moment whose title and text have every word of the query, newest first, as many as the settings allow."""
        params = {"subreddit": subreddit, "query": query, "after": after_epoch_seconds, "limit": self._settings.candidate_posts, "sort": "desc", "fields": POST_FIELDS}
        return posts_from(await self._data("/posts/search", params, self._settings.keyword_search_attempts))

    async def posts_by_id(self, post_ids: list[str]) -> list[RedditPost]:
        """The posts in the order asked, which is the web search's order of relevance; a post the archive does not hold is left out."""
        if not post_ids:
            return []
        found = {post.id: post for post in posts_from(await self._data("/posts/ids", {"ids": ",".join(post_ids), "fields": POST_FIELDS}, self._settings.attempts))}
        return [found[post_id] for post_id in post_ids if post_id in found]

    async def top_comments(self, post_id: str) -> list[RedditComment]:
        """The thread's top-level comments with the highest scores, without removed or deleted ones."""
        async with self._comment_reads:
            tree = await self._data("/comments/tree", {"link_id": f"t3_{post_id}", "limit": 100, "start_depth": 1}, self._settings.attempts)
        readable = [comment for comment in comments_from(tree) if comment.body not in ("[removed]", "[deleted]")]
        return sorted(readable, key=lambda comment: comment.score, reverse=True)[: self._settings.comments_per_thread]

    async def _data(self, path: str, params: dict[str, Any], attempts: int) -> list[dict[str, Any]]:
        body = await self._json_with_retries(path, params, attempts)
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            raise RedditUnavailable(f"Arctic Shift answered {path} without a list of data: {str(body)[:200]}")
        return data

    async def _json_with_retries(self, path: str, params: dict[str, Any], attempts: int) -> Any:
        """The answer of the first attempt that gets one. Each retry waits longer than the last, and none starts once its wait would run past the budget."""
        waits = [0.0, *self._settings.retry_waits_seconds]
        problem = "the time budget ran out before the first attempt"
        attempts_made = 0
        for attempt in range(attempts):
            wait = waits[min(attempt, len(waits) - 1)]
            if self._clock() + wait >= self._deadline:
                break
            if attempt:
                self.retries += 1
                await self._sleep(wait)
            attempts_made += 1
            try:
                return await self._json(path, params)
            except RetryableAnswer as answer:
                problem = str(answer)
        raise RedditUnavailable(f"Arctic Shift did not answer {path} after {attempts_made} attempts: {problem}")

    async def _json(self, path: str, params: dict[str, Any]) -> Any:
        if self._client is None:
            raise RuntimeError("ArcticShiftSession used outside its async with block")
        try:
            response = await self._client.get(f"{self._settings.arctic_shift_url}{path}", params=params)
        except (httpx.TimeoutException, httpx.TransportError) as error:
            raise RetryableAnswer(f"{type(error).__name__}: {error}") from error
        if response.status_code in RETRYABLE_STATUSES:
            raise RetryableAnswer(f"HTTP {response.status_code} {response.text[:120]}")
        if response.status_code != OK:
            raise RedditUnavailable(f"Arctic Shift answered {path} with HTTP {response.status_code}: {response.text[:200]}")
        return response.json()


def posts_from(data: list[dict[str, Any]]) -> list[RedditPost]:
    try:
        return [RedditPost.model_validate(post) for post in data]
    except ValidationError as error:
        raise RedditUnavailable(f"Arctic Shift answered with a post the tool cannot read: {error}") from error


def comments_from(tree: list[dict[str, Any]]) -> list[RedditComment]:
    """The top-level comments of a comment tree; its other nodes are "more comments" links."""
    try:
        return [RedditComment.model_validate(node["data"]) for node in tree if node.get("kind") == "t1"]
    except (ValidationError, KeyError, TypeError) as error:
        raise RedditUnavailable(f"Arctic Shift answered with a comment the tool cannot read: {error}") from error


class RetryableAnswer(RuntimeError):
    """An answer worth another attempt: a timeout, a dropped connection, Arctic Shift's 422 "slow down", a 429, or a server error."""
