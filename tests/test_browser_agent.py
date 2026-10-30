"""The browser user agent names the newest Chrome that Macs have fully rolled out, read once a day from the record the nightly refresh writes, and
never a version older than the fallback; the page reader and the listings refreshes send it."""

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from broadway_mcp.settings import BroadwaySettings
from broadway_mcp.todaytix import refresh_broadway_snapshot
from ops import health
from ops.chrome_releases import ChromeReleasesUnavailable, newest_full_rollout, refresh_chrome_release
from utils import browser_utils
from utils.browser_utils import FALLBACK_CHROME_MAJOR, ChromeRelease, browser_user_agent, chosen_user_agent, recorded_chrome_major
from utils.snapshot_utils import read_snapshot, write_snapshot
from web_search_mcp.page_extractor import PageExtractor
from web_search_mcp.query_cache import QueryCache
from web_search_mcp.settings import SearchSettings

RECORDED_RELEASES = json.loads(Path("tests/fixtures/chrome_releases_mac_stable.json").read_text())
PUBLIC_ADDRESS = "93.184.216.34"


@pytest.fixture(autouse=True)
def fresh_daily_read() -> Iterator[None]:
    browser_utils.chrome_major_on.cache_clear()
    yield
    browser_utils.chrome_major_on.cache_clear()


def release(version: str, fraction: float) -> dict[str, Any]:
    return {"version": version, "fraction": fraction}


def recorded(major: int, days_ago: int = 0) -> ChromeRelease:
    return ChromeRelease(refreshed_at=datetime.now(UTC) - timedelta(days=days_ago), major=major, version=f"{major}.0.1000.1")


def releases_server(status: int = 200, body: dict[str, Any] | None = None) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(status, json=RECORDED_RELEASES if body is None else body))


def test_the_newest_full_rollout_wins_over_a_newer_version_still_starting_its_rollout() -> None:
    chosen = newest_full_rollout(RECORDED_RELEASES["releases"])

    assert (chosen.major, chosen.version) == (156, "156.0.8078.80")  # 157.0.8103.26 was at 0.005 when the fixture was recorded


def test_versions_compare_as_numbers_not_as_text() -> None:
    chosen = newest_full_rollout([release("156.0.8078.80", 1), release("156.0.8078.100", 1), release("99.0.1.1", 1)])

    assert chosen.version == "156.0.8078.100"


def test_a_malformed_version_is_skipped_and_no_full_rollout_raises() -> None:
    assert newest_full_rollout([release("156.0.beta", 1), release("155.0.1.2", 1)]).version == "155.0.1.2"
    with pytest.raises(ChromeReleasesUnavailable):
        newest_full_rollout([release("157.0.8103.26", 0.005), release("156.0.beta", 1)])


async def test_the_refresh_records_the_release(tmp_path: Path) -> None:
    path = tmp_path / "chrome_release.json"

    await refresh_chrome_release(path, releases_server())

    assert read_snapshot(path, ChromeRelease).major == 156


@pytest.mark.parametrize("server", [releases_server(status=503), releases_server(body={"unexpected": []})])
async def test_a_failed_refresh_keeps_the_last_record(tmp_path: Path, server: httpx.MockTransport) -> None:
    path = tmp_path / "chrome_release.json"
    write_snapshot(path, recorded(155))

    with pytest.raises(ChromeReleasesUnavailable):
        await refresh_chrome_release(path, server)

    assert read_snapshot(path, ChromeRelease).major == 155


def test_a_missing_or_garbled_record_falls_back(tmp_path: Path) -> None:
    garbled = tmp_path / "garbled.json"
    garbled.write_text("{not json")

    assert recorded_chrome_major(tmp_path / "missing.json") == FALLBACK_CHROME_MAJOR
    assert recorded_chrome_major(garbled) == FALLBACK_CHROME_MAJOR


def test_the_agent_names_the_recorded_major_in_chromes_own_form(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "chrome_release.json"
    write_snapshot(path, recorded(FALLBACK_CHROME_MAJOR + 4))
    monkeypatch.setattr(browser_utils, "CHROME_RELEASE_PATH", path)

    expected = f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{FALLBACK_CHROME_MAJOR + 4}.0.0.0 Safari/537.36"
    assert browser_user_agent() == expected


def test_a_record_older_than_the_fallback_never_takes_the_agent_backwards(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "chrome_release.json"
    write_snapshot(path, recorded(FALLBACK_CHROME_MAJOR - 10))
    monkeypatch.setattr(browser_utils, "CHROME_RELEASE_PATH", path)

    assert f"Chrome/{FALLBACK_CHROME_MAJOR}.0.0.0" in browser_user_agent()


def test_the_record_is_read_once_a_day(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "chrome_release.json"
    monkeypatch.setattr(browser_utils, "CHROME_RELEASE_PATH", path)
    write_snapshot(path, recorded(FALLBACK_CHROME_MAJOR + 1))
    first_read = browser_utils.chrome_major_on(date(2026, 11, 1))
    write_snapshot(path, recorded(FALLBACK_CHROME_MAJOR + 2))

    assert browser_utils.chrome_major_on(date(2026, 11, 1)) == first_read == FALLBACK_CHROME_MAJOR + 1
    assert browser_utils.chrome_major_on(date(2026, 11, 2)) == FALLBACK_CHROME_MAJOR + 2


def test_an_agent_named_in_settings_overrides_the_browser_agent() -> None:
    assert chosen_user_agent("studio-assistant-test/1.0") == "studio-assistant-test/1.0"
    assert chosen_user_agent("") == browser_user_agent()


async def test_the_page_reader_sends_the_browser_agent() -> None:
    sent: list[str] = []

    def page(request: httpx.Request) -> httpx.Response:
        sent.append(request.headers["user-agent"])
        return httpx.Response(200, html="<html><body><p>A page.</p></body></html>")

    async def resolve_public(host: str) -> list[str]:
        return [PUBLIC_ADDRESS]

    extractor = PageExtractor(SearchSettings(), QueryCache(None), resolver=resolve_public, transport=httpx.MockTransport(page))
    await extractor.read_page("https://example.com/page")

    assert sent == [browser_user_agent()]


async def test_the_broadway_refresh_sends_the_browser_agent(tmp_path: Path) -> None:
    sent: list[str] = []

    def empty_listing(request: httpx.Request) -> httpx.Response:
        sent.append(request.headers["user-agent"])
        return httpx.Response(200, json={"data": [], "pagination": {"total": 0}})

    await refresh_broadway_snapshot(BroadwaySettings(snapshot_path=tmp_path / "broadway.json"), httpx.MockTransport(empty_listing))

    assert sent == [browser_user_agent()]


def test_the_health_check_reports_the_agent_and_fails_a_record_the_refresh_stopped_updating(tmp_path: Path) -> None:
    path = tmp_path / "chrome_release.json"
    write_snapshot(path, recorded(FALLBACK_CHROME_MAJOR + 1, days_ago=1))
    fresh = health.check_browser_agent(path, date.today())
    write_snapshot(path, recorded(FALLBACK_CHROME_MAJOR + 1, days_ago=health.CHROME_RELEASE_STALE_DAYS + 1))
    stale = health.check_browser_agent(path, date.today())

    assert fresh.ok is True and f"sending Chrome {FALLBACK_CHROME_MAJOR + 1}" in fresh.detail
    assert stale.ok is False and f"{health.CHROME_RELEASE_STALE_DAYS + 1} days ago" in stale.detail


@pytest.mark.parametrize(("listings_loaded", "expected_ok"), [(False, None), (True, False)])
def test_no_record_is_expected_only_while_the_listings_agent_is_not_loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, listings_loaded: bool, expected_ok: bool | None) -> None:
    monkeypatch.setattr(health, "agent_loaded", lambda name: listings_loaded)

    check = health.check_browser_agent(tmp_path / "missing.json", date.today())

    assert check.ok is expected_ok and f"fallback Chrome {FALLBACK_CHROME_MAJOR}" in check.detail
