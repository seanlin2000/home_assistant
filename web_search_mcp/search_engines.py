"""The search engines a search asks, chosen by the `engines` setting: Brave's API, the local SearXNG (DuckDuckGo), or both, the second as a fallback."""

import logging
from typing import Protocol

from web_search_mcp.brave_client import BraveClient, brave_api_key
from web_search_mcp.query_cache import QueryCache
from web_search_mcp.searxng_client import SearchResult, SearxngClient
from web_search_mcp.settings import SearchSettings, engine_names

logger = logging.getLogger(__name__)


class SearchEngine(Protocol):
    async def search(self, query: str, time_range: str | None = None) -> list[SearchResult]: ...


class FallbackSearch:
    """Asks the engines in order and returns the first answer. Brave alone scored above DuckDuckGo alone and above both lists interleaved (iteration
    log, step 6), so DuckDuckGo is only the fallback, asked when Brave fails: an error, or a refusal past its monthly limit."""

    def __init__(self, engines: list[SearchEngine]) -> None:
        self._engines = engines

    async def search(self, query: str, time_range: str | None = None) -> list[SearchResult]:
        for engine in self._engines[:-1]:
            results = await results_or_none(engine, query, time_range)
            if results is not None:
                return results
        return await self._engines[-1].search(query, time_range)


async def results_or_none(engine: SearchEngine, query: str, time_range: str | None) -> list[SearchResult] | None:
    try:
        return await engine.search(query, time_range)
    except Exception as error:
        logger.warning("a search engine failed, asking the next: %s", error)
        return None


def configured_search(settings: SearchSettings, cache: QueryCache) -> SearchEngine:
    """Brave is skipped, with a warning, when no key is stored; SearXNG alone is the fallback when nothing else is left."""
    engines = [engine for engine in (build_engine(name, settings, cache) for name in engine_names(settings)) if engine is not None]
    engines = engines or [SearxngClient(settings, cache)]
    return engines[0] if len(engines) == 1 else FallbackSearch(engines)


def build_engine(name: str, settings: SearchSettings, cache: QueryCache) -> SearchEngine | None:
    if name == "searxng":
        return SearxngClient(settings, cache)
    if name != "brave":
        raise ValueError(f"unknown search engine {name!r}; expected brave or searxng")
    api_key = brave_api_key()
    if api_key is None:
        logger.warning("no Brave Search API key in the Keychain; searching without Brave")
        return None
    return BraveClient(settings, cache, api_key)
