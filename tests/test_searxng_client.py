"""The SearXNG client keeps a minimum gap between live requests so the upstream engines do not rate-limit a burst, and never delays cached queries."""

from pathlib import Path

import httpx
import pytest

from web_search_mcp.query_cache import QueryCache
from web_search_mcp.searxng_client import SearxngClient
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


def client_with(fake: FakeTime, monkeypatch: pytest.MonkeyPatch, gap: float = 3.0, cache_dir: str | None = None) -> SearxngClient:
    payload = {"results": [{"title": "t", "url": "http://example.com", "content": "c", "engines": ["google"], "score": 1.0}]}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
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
