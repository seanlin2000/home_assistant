"""Searches Brave's own index through its paid API, the engine asked before SearXNG's DuckDuckGo.

The key lives in the macOS Keychain (service "studio-assistant", account "brave-search-api") and is read with the `security` tool, which stored it and so
reads it back without the access dialog that would stall an unattended run. The only spending limit is the monthly usage limit set in Brave's dashboard:
past it Brave refuses, and the search falls back to SearXNG. Each month's live searches are counted in a text file beside the
other service files, so the spend can be read without the dashboard.
"""

import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import httpx

from web_search_mcp.query_cache import QueryCache
from web_search_mcp.searxng_client import SearchResult, time_range_filter
from web_search_mcp.settings import SearchSettings

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
KEYCHAIN_SERVICE = "studio-assistant"
KEYCHAIN_ACCOUNT = "brave-search-api"
FRESHNESS = {"day": "pd", "week": "pw", "month": "pm", "year": "py"}  # Brave's names for SearXNG's time ranges
RESULTS_PER_SEARCH = 20  # Brave's most per request; a request costs the same whatever the count
ENGINE_NAME = "brave api"
USAGE_FILE = Path.home() / "Library/Application Support/studio-assistant/brave-searches.txt"
DOLLARS_PER_SEARCH = 5 / 1000
USAGE_HEADER = "# Brave Search API: live searches per calendar month, at $5 per 1,000 ($5 of credit each month)"
USAGE_LINE = re.compile(r"^(\d{4}-\d{2})\s+(\d+)")


def brave_api_key() -> str | None:
    """None when no key is stored, the Keychain is locked, or this is not a Mac."""
    if shutil.which("security") is None:
        return None
    found = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w"], capture_output=True, text=True)
    return (found.stdout.strip() or None) if found.returncode == 0 else None


class BraveClient:
    def __init__(self, settings: SearchSettings, cache: QueryCache, api_key: str) -> None:
        self._settings = settings
        self._cache = cache
        self._api_key = api_key

    async def search(self, query: str, time_range: str | None = None) -> list[SearchResult]:
        time_filter = time_range_filter(time_range)
        cached = self._cache.get_brave_search(query, time_filter)
        if cached is not None:
            return [SearchResult(**item) for item in cached]
        results = await self._search_uncached(query, time_filter)
        count_live_search(USAGE_FILE, date.today())
        self._cache.put_brave_search(query, time_filter, [result.model_dump() for result in results])
        return results

    async def _search_uncached(self, query: str, time_range: str | None) -> list[SearchResult]:
        params = {"q": query, "count": RESULTS_PER_SEARCH, "text_decorations": "false"} | ({"freshness": FRESHNESS[time_range]} if time_range else {})
        headers = {"X-Subscription-Token": self._api_key, "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=self._settings.fetch_timeout_seconds + 4) as client:
            response = await client.get(BRAVE_SEARCH_URL, params=params, headers=headers)
        response.raise_for_status()
        return [to_search_result(item) for item in (response.json().get("web") or {}).get("results", [])]


def to_search_result(item: dict) -> SearchResult:
    return SearchResult(title=item.get("title", ""), url=item.get("url", ""), snippet=item.get("description", "") or "", engines=[ENGINE_NAME], score=0.0)


def count_live_search(usage_file: Path, today: date) -> None:
    """Adds one to this month's line, so spending can be read off without the dashboard. Only live searches that succeeded reach here: Brave bills
    nothing for a refused one, and a cached one never asks."""
    counts = searches_by_month(usage_file)
    month = today.strftime("%Y-%m")
    counts[month] = counts.get(month, 0) + 1
    usage_file.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{month}  {count}  ${count * DOLLARS_PER_SEARCH:.2f}" for month, count in sorted(counts.items())]
    usage_file.write_text("\n".join([USAGE_HEADER, *lines]) + "\n")


def searches_by_month(usage_file: Path) -> dict[str, int]:
    lines = usage_file.read_text().splitlines() if usage_file.exists() else []
    return {match[1]: int(match[2]) for match in (USAGE_LINE.match(line) for line in lines) if match}
