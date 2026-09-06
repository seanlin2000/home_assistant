import asyncio
from urllib.parse import urlparse

import httpx
import trafilatura
from pydantic import BaseModel

from web_search_mcp.query_cache import QueryCache
from web_search_mcp.searxng_client import SearchResult
from web_search_mcp.settings import SearchSettings

SKIPPED_EXTENSIONS = (".pdf", ".zip", ".png", ".jpg", ".jpeg", ".gif", ".mp4", ".mp3")


class PageExcerpt(BaseModel):
    title: str
    url: str
    text: str
    word_count: int


class PageExtractor:
    def __init__(self, settings: SearchSettings, cache: QueryCache) -> None:
        self._settings = settings
        self._cache = cache

    async def read_pages(self, results: list[SearchResult]) -> list[PageExcerpt]:
        """Fetches the first readable pages concurrently and keeps result order so ranking survives extraction."""
        candidates = [result for result in results if self.is_fetchable(result.url)][: self._settings.pages_to_read * 2]
        texts = await asyncio.gather(*(self.read_page(result.url) for result in candidates))
        excerpts = [to_excerpt(result, text, self._settings.words_per_page) for result, text in zip(candidates, texts) if text]
        return apply_total_budget(excerpts[: self._settings.pages_to_read], self._settings.total_word_budget)

    async def read_page(self, url: str) -> str:
        cached = self._cache.get_page(url)
        if cached is not None:
            return cached
        text = await self._read_uncached(url)
        self._cache.put_page(url, text)
        return text

    async def _read_uncached(self, url: str) -> str:
        try:
            html = await self._download(url)
        except (httpx.HTTPError, ValueError):
            return ""
        extracted = trafilatura.extract(html, include_comments=False, include_tables=True, favor_precision=True)
        return (extracted or "").strip()

    async def _download(self, url: str) -> str:
        headers = {"User-Agent": self._settings.user_agent, "Accept-Language": "en-US,en;q=0.9"}
        async with httpx.AsyncClient(timeout=self._settings.fetch_timeout_seconds, follow_redirects=True, headers=headers) as client:
            response = await client.get(url)
        response.raise_for_status()
        if "html" not in response.headers.get("content-type", ""):
            raise ValueError("not an HTML page")
        return response.text

    def is_fetchable(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or parsed.path.lower().endswith(SKIPPED_EXTENSIONS):
            return False
        host = parsed.netloc.lower().removeprefix("www.")
        return not any(host == blocked or host.endswith(f".{blocked}") for blocked in self._settings.blocked_domains)


def to_excerpt(result: SearchResult, text: str, words_per_page: int) -> PageExcerpt:
    words = text.split()
    clipped = " ".join(words[:words_per_page])
    return PageExcerpt(title=result.title, url=result.url, text=clipped, word_count=len(clipped.split()))


def apply_total_budget(excerpts: list[PageExcerpt], total_word_budget: int) -> list[PageExcerpt]:
    kept: list[PageExcerpt] = []
    remaining = total_word_budget
    for excerpt in excerpts:
        if remaining <= 0:
            break
        words = excerpt.text.split()[:remaining]
        kept.append(PageExcerpt(title=excerpt.title, url=excerpt.url, text=" ".join(words), word_count=len(words)))
        remaining -= len(words)
    return kept
