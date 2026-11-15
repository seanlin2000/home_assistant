"""The SearXNG client keeps a minimum gap between live requests so the upstream engines do not rate-limit a burst, never delays cached queries, and passes
a time range on to SearXNG."""

import logging
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

import web_search_mcp.brave_client
import web_search_mcp.search_engines
from web_search_mcp.brave_client import BraveClient, BraveFailure, brave_failures, count_live_search, note_brave_failure, searches_by_month
from web_search_mcp.query_cache import QueryCache, search_key
from web_search_mcp.search_engines import FallbackSearch, configured_search
from web_search_mcp.searxng_client import SearchResult, SearxngClient, warn_about_unresponsive_engines
from web_search_mcp.settings import SearchSettings


class FakeTime:
    def __init__(self) -> None:
        self.now = 100.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def client_with(fake: FakeTime, monkeypatch: pytest.MonkeyPatch, gap: float = 3.0, cache_dir: str | None = None, seen_requests: list[httpx.Request] | None = None) -> SearxngClient:
    payload = {"results": [{"title": "t", "url": "http://example.com", "content": "c", "engines": ["google"], "score": 1.0}]}

    def answer(request: httpx.Request) -> httpx.Response:
        if seen_requests is not None:
            seen_requests.append(request)
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(answer)
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_async_client(transport=transport, **kwargs))
    return SearxngClient(SearchSettings(min_seconds_between_searches=gap), QueryCache(cache_dir), clock=fake.clock, sleep=fake.sleep)


async def test_back_to_back_live_searches_are_spaced_by_the_minimum_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeTime()
    client = client_with(fake, monkeypatch)
    await client.search("first question")
    fake.now += 1.0
    await client.search("second question")
    assert fake.slept == [2.0]


async def test_cached_queries_never_wait(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeTime()
    client = client_with(fake, monkeypatch, cache_dir=str(tmp_path))
    await client.search("same question")
    await client.search("same question")
    assert fake.slept == []


async def test_no_wait_once_the_gap_has_already_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeTime()
    client = client_with(fake, monkeypatch)
    await client.search("first")
    fake.now += 10.0
    await client.search("second")
    assert fake.slept == []


async def test_a_time_range_reaches_searxng_and_is_cached_apart_from_the_plain_query(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    client = client_with(FakeTime(), monkeypatch, gap=0.0, cache_dir=str(tmp_path), seen_requests=requests)
    await client.search("fed funds rate", "week")
    await client.search("fed funds rate")
    await client.search("fed funds rate", "week")
    assert [request.url.params.get("time_range") for request in requests] == ["week", None]
    assert search_key(" Fed Funds Rate", None) == "search:fed funds rate"


async def test_an_empty_or_unknown_time_range_searches_without_a_filter_and_case_does_not_matter(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []
    client = client_with(FakeTime(), monkeypatch, gap=0.0, seen_requests=requests)
    for time_range in ("", "decade", " WEEK "):
        await client.search("fed funds rate", time_range)
    assert [request.url.params.get("time_range") for request in requests] == [None, None, "week"]


def test_engines_that_did_not_answer_are_logged_by_name_and_reason(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        warn_about_unresponsive_engines([["brave", "too many requests"], ["duckduckgo", "CAPTCHA"]])
        warn_about_unresponsive_engines([])
    assert [record.getMessage() for record in caplog.records] == ["SearXNG engines not answering: brave (too many requests), duckduckgo (CAPTCHA)"]


def brave_payload(*urls: str) -> dict:
    return {"web": {"results": [{"title": f"Brave {url}", "url": url, "description": "d"} for url in urls]}}


async def test_brave_asks_for_twenty_results_with_its_freshness_name_and_the_key_in_a_header(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=brave_payload("https://a.example/"))

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_async_client(transport=httpx.MockTransport(answer), **kwargs))
    results = await BraveClient(SearchSettings(), QueryCache(None), api_key="test-key").search("fed rate", time_range="Week")
    assert [(result.url, result.engines) for result in results] == [("https://a.example/", ["brave api"])]
    assert seen[0].url.params["count"] == "20" and seen[0].url.params["freshness"] == "pw"
    assert seen[0].headers["X-Subscription-Token"] == "test-key"
    assert searches_by_month(web_search_mcp.brave_client.USAGE_FILE) == {date.today().strftime("%Y-%m"): 1}


class FakeEngine:
    def __init__(self, *urls: str, failure: Exception | None = None) -> None:
        self._results = [SearchResult(title=url, url=url, snippet="", engines=["fake"], score=0.0) for url in urls]
        self._failure = failure

    async def search(self, query: str, time_range: str | None = None) -> list[SearchResult]:
        if self._failure is not None:
            raise self._failure
        return self._results


async def test_the_fallback_is_asked_only_when_the_first_engine_fails_and_a_search_fails_only_when_all_do() -> None:
    over_limit = httpx.HTTPStatusError("402", request=httpx.Request("GET", "https://brave"), response=httpx.Response(402))
    assert [result.url for result in await FallbackSearch([FakeEngine("https://brave1/"), FakeEngine("https://ddg1/")]).search("q")] == ["https://brave1/"]
    assert [result.url for result in await FallbackSearch([FakeEngine(failure=over_limit), FakeEngine("https://ddg1/")]).search("q")] == ["https://ddg1/"]
    with pytest.raises(httpx.HTTPStatusError):
        await FallbackSearch([FakeEngine(failure=over_limit), FakeEngine(failure=over_limit)]).search("q")


def test_engines_follow_the_setting_and_brave_is_skipped_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = QueryCache(None)
    assert isinstance(configured_search(SearchSettings(engines="brave,searxng"), cache), SearxngClient)
    monkeypatch.setattr(web_search_mcp.search_engines, "brave_api_key", lambda: "test-key")
    assert isinstance(configured_search(SearchSettings(engines="Brave"), cache), BraveClient)
    assert isinstance(configured_search(SearchSettings(engines="brave, searxng"), cache), FallbackSearch)
    with pytest.raises(ValueError):
        configured_search(SearchSettings(engines="bing"), cache)


def test_each_live_brave_search_adds_one_to_its_month_and_the_dollar_figure_follows(tmp_path: Path) -> None:
    usage_file = tmp_path / "brave-searches.txt"
    for _ in range(3):
        count_live_search(usage_file, date(2026, 10, 10))
    count_live_search(usage_file, date(2026, 11, 1))
    assert usage_file.read_text().splitlines()[1:] == ["2026-10  3  $0.01", "2026-11  1  $0.01"]
    assert searches_by_month(usage_file) == {"2026-10": 3, "2026-11": 1}


def brave_answering(monkeypatch: pytest.MonkeyPatch, *answers: httpx.Response | Exception) -> list[httpx.Request]:
    """Brave answers each request with the next of `answers` in turn; an exception is raised as the transport's failure. The retry waits no time."""
    seen: list[httpx.Request] = []
    remaining = list(answers)

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        reply = remaining.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_async_client(transport=httpx.MockTransport(answer), **kwargs))
    monkeypatch.setattr(web_search_mcp.brave_client, "RETRY_DELAY_SECONDS", 0)
    return seen


async def brave_search() -> list[SearchResult]:
    return await BraveClient(SearchSettings(), QueryCache(None), api_key="test-key").search("fed rate")


async def test_a_brave_error_that_comes_back_at_once_is_retried_once_and_a_success_counts_one_search(
    monkeypatch: pytest.MonkeyPatch, brave_failures_in_a_temporary_file: Path, woken_agents: list[str]
) -> None:
    seen = brave_answering(monkeypatch, httpx.Response(503), httpx.Response(200, json=brave_payload("https://a.example/")))
    assert [result.url for result in await brave_search()] == ["https://a.example/"]
    assert len(seen) == 2
    assert searches_by_month(web_search_mcp.brave_client.USAGE_FILE) == {date.today().strftime("%Y-%m"): 1}
    assert brave_failures(brave_failures_in_a_temporary_file) == [] and woken_agents == []


async def test_a_brave_failure_after_the_retry_is_recorded_and_wakes_the_health_check(monkeypatch: pytest.MonkeyPatch, brave_failures_in_a_temporary_file: Path, woken_agents: list[str]) -> None:
    rate_limited = httpx.Response(429, json={"type": "ErrorResponse", "error": {"code": "RATE_LIMITED", "status": 429}})
    seen = brave_answering(monkeypatch, rate_limited, rate_limited)
    with pytest.raises(httpx.HTTPStatusError):
        await brave_search()
    assert len(seen) == 2
    assert [failure.reason for failure in brave_failures(brave_failures_in_a_temporary_file)] == ["HTTP 429 RATE_LIMITED"]
    assert woken_agents == ["health"]
    assert searches_by_month(web_search_mcp.brave_client.USAGE_FILE) == {}


async def test_a_brave_timeout_is_not_retried_because_a_second_would_double_the_wait(monkeypatch: pytest.MonkeyPatch, brave_failures_in_a_temporary_file: Path, woken_agents: list[str]) -> None:
    seen = brave_answering(monkeypatch, httpx.ReadTimeout("no answer"), httpx.Response(200, json=brave_payload("https://never.example/")))
    with pytest.raises(httpx.ReadTimeout):
        await brave_search()
    assert len(seen) == 1
    assert [failure.reason for failure in brave_failures(brave_failures_in_a_temporary_file)] == ["timed out"]
    assert woken_agents == ["health"]


async def test_a_refused_key_is_not_retried(monkeypatch: pytest.MonkeyPatch, brave_failures_in_a_temporary_file: Path) -> None:
    seen = brave_answering(monkeypatch, httpx.Response(401, text="unauthorized"), httpx.Response(200, json=brave_payload("https://never.example/")))
    with pytest.raises(httpx.HTTPStatusError):
        await brave_search()
    assert len(seen) == 1
    assert [failure.reason for failure in brave_failures(brave_failures_in_a_temporary_file)] == ["HTTP 401"]


async def test_a_refused_connection_is_retried(monkeypatch: pytest.MonkeyPatch, brave_failures_in_a_temporary_file: Path) -> None:
    seen = brave_answering(monkeypatch, httpx.ConnectError("refused"), httpx.ConnectError("refused"))
    with pytest.raises(httpx.ConnectError):
        await brave_search()
    assert len(seen) == 2
    assert [failure.reason for failure in brave_failures(brave_failures_in_a_temporary_file)] == ["could not connect"]


def test_the_failures_file_keeps_the_newest_fifty_and_skips_lines_it_cannot_read(tmp_path: Path) -> None:
    failures_file = tmp_path / "brave-failures.txt"
    for minute in range(55):
        note_brave_failure(failures_file, f"HTTP 50{minute % 4}", datetime(2026, 11, 15, 12, minute, tzinfo=UTC))
    failures = brave_failures(failures_file)
    assert len(failures) == 50
    assert failures[-1] == BraveFailure(at=datetime(2026, 11, 15, 12, 54, tzinfo=UTC), reason="HTTP 502")
    failures_file.write_text(failures_file.read_text() + "garbled line\n")
    assert len(brave_failures(failures_file)) == 50
