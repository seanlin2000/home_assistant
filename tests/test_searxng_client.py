"""The SearXNG client keeps a minimum gap between live requests so the upstream engines do not rate-limit a burst, never delays cached queries, passes
a time range on to SearXNG, and searches once more when a search came back empty only because an engine's request failed on the way."""

import logging
from pathlib import Path
from typing import Any

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


ONE_RESULT = {"results": [{"title": "t", "url": "http://example.com", "content": "c", "engines": ["google"], "score": 1.0}]}
BRAVE_RATE_LIMITED = ["brave", "Suspended: too many requests"]


def empty_reply(*unresponsive_engines: list[str]) -> dict[str, Any]:
    return {"results": [], "unresponsive_engines": list(unresponsive_engines)}


def client_with(
    fake: FakeTime,
    monkeypatch: pytest.MonkeyPatch,
    gap: float = 3.0,
    cache_dir: str | None = None,
    seen_requests: list[httpx.Request] | None = None,
    replies: list[dict[str, Any]] | None = None,
) -> SearxngClient:
    """SearXNG answers with the given replies in turn, then with one result for every request after them."""
    queued_replies = list(replies or [])

    def answer(request: httpx.Request) -> httpx.Response:
        if seen_requests is not None:
            seen_requests.append(request)
        return httpx.Response(200, json=queued_replies.pop(0) if queued_replies else ONE_RESULT)

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


async def test_an_empty_search_after_an_engine_timed_out_is_asked_again_once_the_engine_is_back(monkeypatch: pytest.MonkeyPatch) -> None:
    fake, requests = FakeTime(), []
    client = client_with(fake, monkeypatch, seen_requests=requests, replies=[empty_reply(BRAVE_RATE_LIMITED, ["duckduckgo", "timeout"])])
    results = await client.search("difference between New York strip steak and ribeye steak")
    assert [result.url for result in results] == ["http://example.com"]
    assert len(requests) == 2 and fake.slept == [SearchSettings().transient_retry_wait_seconds]


@pytest.mark.parametrize("reason", ["HTTP connection error", "Suspended: timeout"])
async def test_a_dropped_connection_or_an_engine_still_held_back_after_one_is_asked_again(monkeypatch: pytest.MonkeyPatch, reason: str) -> None:
    requests: list[httpx.Request] = []
    client = client_with(FakeTime(), monkeypatch, seen_requests=requests, replies=[empty_reply(["duckduckgo", reason])])
    assert await client.search("nfl games today") and len(requests) == 2


@pytest.mark.parametrize(
    "empty",
    [
        empty_reply(BRAVE_RATE_LIMITED),
        empty_reply(BRAVE_RATE_LIMITED, ["duckduckgo", "CAPTCHA"]),
        empty_reply(),
    ],
    ids=["only-a-rate-limited-engine-silent", "captcha", "every-engine-answered"],
)
async def test_an_empty_search_is_not_repeated_after_a_rate_limit_a_captcha_or_a_true_miss(monkeypatch: pytest.MonkeyPatch, empty: dict[str, Any]) -> None:
    fake, requests = FakeTime(), []
    client = client_with(fake, monkeypatch, seen_requests=requests, replies=[empty])
    assert await client.search("a question nothing matches") == []
    assert len(requests) == 1 and fake.slept == []


async def test_a_search_is_asked_again_only_once(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []
    timed_out = empty_reply(["duckduckgo", "timeout"])
    client = client_with(FakeTime(), monkeypatch, seen_requests=requests, replies=[timed_out, timed_out, timed_out])
    assert await client.search("nfl games today") == []
    assert len(requests) == 2
