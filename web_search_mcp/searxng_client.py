import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

import httpx
from pydantic import BaseModel

from web_search_mcp.query_cache import QueryCache
from web_search_mcp.settings import SearchSettings

_LOGGER = logging.getLogger(__name__)
TIME_RANGES = frozenset({"day", "week", "month", "year"})  # SearXNG's time_range values: only results published within that span
# SearXNG's words for an engine request that failed on the way, which the next request usually gets through. A CAPTCHA or a rate limit is left out:
# SearXNG holds the engine back for an hour or more after one, and asking again only adds to the burst that caused it.
TRANSIENT_ENGINE_FAILURES = frozenset({"timeout", "HTTP connection error", "network error", "HTTP protocol error"})
SUSPENDED_PREFIX = "Suspended: "


def time_range_filter(time_range: str | None) -> str | None:
    """A time range SearXNG knows, in any case; anything else, "" included, searches without a filter rather than failing, since the model fills it in."""
    normalized = (time_range or "").strip().lower()
    return normalized if normalized in TIME_RANGES else None


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    engines: list[str]
    score: float


class SearxngReply(BaseModel):
    results: list[SearchResult]
    unresponsive_engines: list[list[str]] = []  # [engine, reason] pairs, as SearXNG names the engines that did not answer

    @property
    def failed_on_the_way(self) -> bool:
        """No results because an engine's request timed out or lost its connection, not because nothing matched."""
        return not self.results and any(is_transient_failure(reason) for _, reason in self.unresponsive_engines)


def is_transient_failure(reason: str) -> bool:
    """A failure SearXNG reports bare the first time and, while it holds the engine back afterwards, as "Suspended: timeout"."""
    return reason.removeprefix(SUSPENDED_PREFIX) in TRANSIENT_ENGINE_FAILURES


class SearxngClient:
    """Searches through the local SearXNG instance, with a cache in front and a minimum gap between live requests behind.

    The gap exists because the upstream engines (Google, Bing, Brave, DuckDuckGo) rate-limit or CAPTCHA an address that queries them in bursts;
    a benchmark pass tripped all four at once. Cached queries never wait. A single spoken question rarely makes two live searches, so the
    assistant does not feel the gap; back-to-back callers such as the benchmark do."""

    def __init__(self, settings: SearchSettings, cache: QueryCache, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self._settings = settings
        self._cache = cache
        self._clock = clock
        self._sleep = sleep
        self._last_live_search: float | None = None
        self._gap_lock = asyncio.Lock()

    async def search(self, query: str, time_range: str | None = None) -> list[SearchResult]:
        time_filter = time_range_filter(time_range)
        cached = self._cache.get_search(query, time_filter)
        if cached is not None:
            return [SearchResult(**item) for item in cached]
        await self._wait_for_gap()
        results = await self._search_live(query, time_filter)
        self._cache.put_search(query, time_filter, [result.model_dump() for result in results])
        return results

    async def _wait_for_gap(self) -> None:
        async with self._gap_lock:
            if self._last_live_search is not None:
                remaining = self._settings.min_seconds_between_searches - (self._clock() - self._last_live_search)
                if remaining > 0:
                    await self._sleep(remaining)
            self._last_live_search = self._clock()

    async def _search_live(self, query: str, time_range: str | None) -> list[SearchResult]:
        """One more try when the search came back empty only because an engine's request failed on the way. When a single engine is carrying the
        search, one timeout would otherwise leave the user with no results at all."""
        reply = await self._ask_searxng(query, time_range)
        if not reply.failed_on_the_way:
            return reply.results
        _LOGGER.info("Searching again after engines failed on the way: %s", describe_unresponsive_engines(reply.unresponsive_engines))
        await self._sleep(self._settings.transient_retry_wait_seconds)
        await self._wait_for_gap()
        return (await self._ask_searxng(query, time_range)).results

    async def _ask_searxng(self, query: str, time_range: str | None) -> SearxngReply:
        params = {"q": query, "format": "json", "language": "en", "safesearch": "0"} | ({"time_range": time_range} if time_range else {})
        async with httpx.AsyncClient(timeout=self._settings.fetch_timeout_seconds + 4) as client:
            response = await client.get(f"{self._settings.searxng_url}/search", params=params)
        response.raise_for_status()
        reply = response.json()
        unresponsive_engines = reply.get("unresponsive_engines", [])
        warn_about_unresponsive_engines(unresponsive_engines)
        return SearxngReply(results=[to_search_result(item) for item in reply.get("results", [])], unresponsive_engines=unresponsive_engines)


def warn_about_unresponsive_engines(unresponsive: list[list[str]]) -> None:
    """Search quietly narrows to the engines that still answer, so without this line a blocked or broken engine shows only as worse answers."""
    if unresponsive:
        _LOGGER.warning("SearXNG engines not answering: %s", describe_unresponsive_engines(unresponsive))


def describe_unresponsive_engines(unresponsive: list[list[str]]) -> str:
    """SearXNG names each silent engine with its reason, as [name, reason] pairs: "brave (too many requests)"."""
    return ", ".join(f"{name} ({reason})" for name, reason in unresponsive)


def to_search_result(item: dict) -> SearchResult:
    return SearchResult(title=item.get("title", ""), url=item.get("url", ""), snippet=item.get("content", "") or "", engines=list(item.get("engines", [])), score=float(item.get("score", 0.0)))
