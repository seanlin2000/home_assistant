"""Searches Brave's own index through its paid API, the engine asked before SearXNG's DuckDuckGo.

The key lives in the macOS Keychain (service "studio-assistant", account "brave-search-api"), read through utils/keychain_utils.py. The only
spending limit is the monthly usage limit set in Brave's dashboard: past it Brave refuses, and the search falls back to SearXNG. Each month's live
searches are counted in a text file beside the other service files, so the spend can be read without the dashboard.

SearXNG runs only while Brave might not answer (ops/searxng_demand.py). So a search Brave fails is written to a second file, and the health check is
woken at once to start SearXNG, rather than at its next five-minute run.
"""

import asyncio
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import NamedTuple

import httpx

from utils import launchd_utils
from utils.keychain_utils import keychain_item_stored, keychain_secret
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
FAILURES_FILE = Path.home() / "Library/Application Support/studio-assistant/brave-failures.txt"
MONTHLY_CREDIT_DOLLARS = 5.0
DOLLARS_PER_SEARCH = 5 / 1000
FAILURES_KEPT = 50
FAILURES_HEADER = "# Brave Search API: searches Brave failed, newest last (UTC time, then why)"
RETRY_DELAY_SECONDS = 1.0
RETRIED_STATUS_CODES = frozenset({429})  # Brave's per-second rate limit; any 5xx is retried too
HEALTH_AGENT = "health"
USAGE_HEADER = "# Brave Search API: live searches per calendar month, at $5 per 1,000 ($5 of credit each month)"
USAGE_LINE = re.compile(r"^(\d{4}-\d{2})\s+(\d+)")


def brave_api_key() -> str | None:
    return keychain_secret(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)


def brave_key_stored() -> bool:
    return keychain_item_stored(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)


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
        results = await self._live_search(query, time_filter)
        count_live_search(USAGE_FILE, date.today())
        self._cache.put_brave_search(query, time_filter, [result.model_dump() for result in results])
        return results

    async def _live_search(self, query: str, time_range: str | None) -> list[SearchResult]:
        try:
            return await self._search_with_one_retry(query, time_range)
        except httpx.HTTPError as error:
            note_brave_failure(FAILURES_FILE, failure_reason(error), datetime.now(UTC))
            launchd_utils.wake_agent(HEALTH_AGENT)
            raise

    async def _search_with_one_retry(self, query: str, time_range: str | None) -> list[SearchResult]:
        try:
            return await self._search_uncached(query, time_range)
        except httpx.HTTPError as error:
            if not worth_retrying(error):
                raise
        await asyncio.sleep(RETRY_DELAY_SECONDS)
        return await self._search_uncached(query, time_range)

    async def _search_uncached(self, query: str, time_range: str | None) -> list[SearchResult]:
        params = {"q": query, "count": RESULTS_PER_SEARCH, "text_decorations": "false"} | ({"freshness": FRESHNESS[time_range]} if time_range else {})
        headers = {"X-Subscription-Token": self._api_key, "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=self._settings.fetch_timeout_seconds + 4) as client:
            response = await client.get(BRAVE_SEARCH_URL, params=params, headers=headers)
        response.raise_for_status()
        return [to_search_result(item) for item in (response.json().get("web") or {}).get("results", [])]


def worth_retrying(error: httpx.HTTPError) -> bool:
    """A refused connection, a Brave error, or a rate-limit refusal comes back at once, so one more try costs about a second. A timeout is never
    retried: it already took the whole timeout, and a Brave that hangs once usually hangs again, so a retry would double the wait."""
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        return status in RETRIED_STATUS_CODES or status >= httpx.codes.INTERNAL_SERVER_ERROR
    return isinstance(error, httpx.ConnectError)


def failure_reason(error: httpx.HTTPError) -> str:
    if isinstance(error, httpx.TimeoutException):
        return "timed out"
    if isinstance(error, httpx.ConnectError):
        return "could not connect"
    if isinstance(error, httpx.HTTPStatusError):
        return f"HTTP {error.response.status_code}{brave_error_code(error.response)}"
    return type(error).__name__


def brave_error_code(response: httpx.Response) -> str:
    """Brave names the refusal in its error body (a rate limit or a spent quota both answer 429); an unreadable body adds nothing."""
    try:
        code = response.json()["error"]["code"]
    except (ValueError, KeyError, TypeError):
        return ""
    return f" {code}" if isinstance(code, str) and code else ""


class BraveFailure(NamedTuple):
    at: datetime
    reason: str


def note_brave_failure(failures_file: Path, reason: str, at: datetime) -> None:
    """Adds one line and keeps the newest FAILURES_KEPT: the health check reads only the newest, and a person reading the file sees the recent run."""
    kept = [f"{failure.at.isoformat(timespec='seconds')}  {failure.reason}" for failure in brave_failures(failures_file)[-(FAILURES_KEPT - 1) :]]
    failures_file.parent.mkdir(parents=True, exist_ok=True)
    failures_file.write_text("\n".join([FAILURES_HEADER, *kept, f"{at.isoformat(timespec='seconds')}  {reason}"]) + "\n")


def brave_failures(failures_file: Path) -> list[BraveFailure]:
    lines = failures_file.read_text().splitlines() if failures_file.exists() else []
    return [failure for failure in (parsed_failure(line) for line in lines if not line.startswith("#")) if failure is not None]


def parsed_failure(line: str) -> BraveFailure | None:
    stamp, _, reason = line.partition("  ")
    try:
        return BraveFailure(at=datetime.fromisoformat(stamp), reason=reason.strip())
    except ValueError:
        return None


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


def dollars_left_this_month(usage_file: Path, today: date) -> float:
    return MONTHLY_CREDIT_DOLLARS - searches_by_month(usage_file).get(today.strftime("%Y-%m"), 0) * DOLLARS_PER_SEARCH


def searches_by_month(usage_file: Path) -> dict[str, int]:
    lines = usage_file.read_text().splitlines() if usage_file.exists() else []
    return {match[1]: int(match[2]) for match in (USAGE_LINE.match(line) for line in lines) if match}
