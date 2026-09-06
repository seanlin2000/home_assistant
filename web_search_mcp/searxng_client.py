import asyncio
import time
from collections.abc import Awaitable, Callable

import httpx
from pydantic import BaseModel

from web_search_mcp.query_cache import QueryCache
from web_search_mcp.settings import SearchSettings


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    engines: list[str]
    score: float


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

    async def search(self, query: str) -> list[SearchResult]:
        cached = self._cache.get_search(query)
        if cached is not None:
            return [SearchResult(**item) for item in cached]
        await self._wait_for_gap()
        results = await self._search_uncached(query)
        self._cache.put_search(query, [result.model_dump() for result in results])
        return results

    async def _wait_for_gap(self) -> None:
        async with self._gap_lock:
            if self._last_live_search is not None:
                remaining = self._settings.min_seconds_between_searches - (self._clock() - self._last_live_search)
                if remaining > 0:
                    await self._sleep(remaining)
            self._last_live_search = self._clock()

    async def _search_uncached(self, query: str) -> list[SearchResult]:
        params = {"q": query, "format": "json", "language": "en", "safesearch": "0"}
        async with httpx.AsyncClient(timeout=self._settings.fetch_timeout_seconds + 4) as client:
            response = await client.get(f"{self._settings.searxng_url}/search", params=params)
        response.raise_for_status()
        return [to_search_result(item) for item in response.json().get("results", [])]


def to_search_result(item: dict) -> SearchResult:
    return SearchResult(title=item.get("title", ""), url=item.get("url", ""), snippet=item.get("content", "") or "", engines=list(item.get("engines", [])), score=float(item.get("score", 0.0)))
