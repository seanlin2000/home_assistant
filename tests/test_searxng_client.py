"""The SearXNG client keeps a minimum gap between live requests so the upstream engines do not rate-limit a burst, never delays cached queries, and passes
a time range on to SearXNG."""

import logging
from pathlib import Path

import httpx
import pytest

from web_search_mcp.query_cache import QueryCache, search_key
from web_search_mcp.searxng_client import SearxngClient, warn_about_unresponsive_engines
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
        warn_about_unresponsive_engines([["brave", "too many requests"], ["bing", "HTTP connection error"]])
        warn_about_unresponsive_engines([])
    assert [record.getMessage() for record in caplog.records] == ["SearXNG engines not answering: brave (too many requests), bing (HTTP connection error)"]
