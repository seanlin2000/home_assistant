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
    def __init__(self, settings: SearchSettings, cache: QueryCache) -> None:
        self._settings = settings
        self._cache = cache

    async def search(self, query: str) -> list[SearchResult]:
        cached = self._cache.get_search(query)
        if cached is not None:
            return [SearchResult(**item) for item in cached]
        results = await self._search_uncached(query)
        self._cache.put_search(query, [result.model_dump() for result in results])
        return results

    async def _search_uncached(self, query: str) -> list[SearchResult]:
        params = {"q": query, "format": "json", "language": "en", "safesearch": "0"}
        async with httpx.AsyncClient(timeout=self._settings.fetch_timeout_seconds + 4) as client:
            response = await client.get(f"{self._settings.searxng_url}/search", params=params)
        response.raise_for_status()
        return [to_search_result(item) for item in response.json().get("results", [])]


def to_search_result(item: dict) -> SearchResult:
    return SearchResult(title=item.get("title", ""), url=item.get("url", ""), snippet=item.get("content", "") or "", engines=list(item.get("engines", [])), score=float(item.get("score", 0.0)))
