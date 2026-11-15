"""SearXNG runs only while Brave might not answer: its credit nearly spent, its key missing, a failure within the hour, or a benchmark running."""

import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from ops import paths
from ops.searxng_demand import SearxngDemand, SearxngPolicy, judge_searxng_demand, lease_holder_alive, read_searxng_demand, searxng_lease, searxng_reason
from web_search_mcp.brave_client import BraveFailure, count_live_search, note_brave_failure

NOW = datetime(2026, 11, 15, 18, 0, tzinfo=UTC)
POLICY = SearxngPolicy()


def demand(dollars_left: float = 4.80, key_stored: bool = True, failure_minutes_ago: float | None = None, benchmark_running: bool = False) -> SearxngDemand:
    failure = None if failure_minutes_ago is None else BraveFailure(at=NOW - timedelta(minutes=failure_minutes_ago), reason="timed out")
    return SearxngDemand(brave_dollars_left=dollars_left, brave_key_stored=key_stored, last_brave_failure=failure, benchmark_running=benchmark_running)


def test_nothing_needs_searxng_while_brave_has_credit_its_key_and_no_recent_failure() -> None:
    verdict = judge_searxng_demand(demand(), POLICY, NOW)
    assert verdict.reason is None
    assert verdict.idle_detail == "off on purpose: Brave has $4.80 of this month's credit left and has not failed in the last hour"


def test_searxng_is_needed_once_less_than_twenty_cents_of_credit_is_left() -> None:
    assert searxng_reason(demand(dollars_left=0.20), POLICY, NOW) is None
    assert searxng_reason(demand(dollars_left=0.195), POLICY, NOW) == "Brave has $0.20 of this month's credit left"
    assert searxng_reason(demand(dollars_left=-0.40), POLICY, NOW) == "Brave has $0.00 of this month's credit left"


def test_searxng_is_needed_for_an_hour_after_brave_fails() -> None:
    assert searxng_reason(demand(failure_minutes_ago=0.5), POLICY, NOW) == "Brave failed under a minute ago (timed out)"
    assert searxng_reason(demand(failure_minutes_ago=59), POLICY, NOW) == "Brave failed 59 min ago (timed out)"
    assert searxng_reason(demand(failure_minutes_ago=61), POLICY, NOW) is None


def test_searxng_is_needed_without_a_brave_key_and_while_a_benchmark_runs() -> None:
    assert searxng_reason(demand(key_stored=False), POLICY, NOW) == "no Brave key in the Keychain"
    assert searxng_reason(demand(benchmark_running=True), POLICY, NOW) == "a benchmark is running"


def test_the_demand_is_read_from_the_usage_and_failure_files_the_search_tool_writes(
    monkeypatch: pytest.MonkeyPatch, brave_usage_in_a_temporary_file: Path, brave_failures_in_a_temporary_file: Path, tmp_path: Path
) -> None:
    monkeypatch.setenv("STUDIO_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr("ops.searxng_demand.brave_key_stored", lambda: True)
    for _ in range(40):
        count_live_search(brave_usage_in_a_temporary_file, date(2026, 11, 3))
    note_brave_failure(brave_failures_in_a_temporary_file, "HTTP 503", NOW - timedelta(minutes=20))
    read = read_searxng_demand(NOW)
    assert read.brave_dollars_left == pytest.approx(4.80)
    assert read.last_brave_failure == BraveFailure(at=NOW - timedelta(minutes=20), reason="HTTP 503")
    assert read.benchmark_running is False


def test_a_new_month_restores_the_credit(brave_usage_in_a_temporary_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ops.searxng_demand.brave_key_stored", lambda: True)
    for _ in range(990):
        count_live_search(brave_usage_in_a_temporary_file, date(2026, 11, 3))
    assert read_searxng_demand(datetime(2026, 11, 30, 12, tzinfo=UTC)).brave_dollars_left == pytest.approx(0.05)
    assert read_searxng_demand(datetime(2026, 12, 1, 12, tzinfo=UTC)).brave_dollars_left == pytest.approx(5.0)


def test_the_lease_counts_while_its_process_lives_and_is_gone_after_the_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STUDIO_LOG_DIR", str(tmp_path))
    assert lease_holder_alive() is False
    with searxng_lease():
        assert paths.searxng_lease().read_text() == str(os.getpid())
        assert lease_holder_alive() is True
    assert not paths.searxng_lease().exists()


def test_a_lease_left_by_a_run_that_died_counts_for_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STUDIO_LOG_DIR", str(tmp_path))
    monkeypatch.setattr("ops.searxng_demand.os.kill", fake_kill_of_a_gone_process)
    paths.searxng_lease().write_text("99999")
    assert lease_holder_alive() is False
    paths.searxng_lease().write_text("not a process id")
    assert lease_holder_alive() is False


def fake_kill_of_a_gone_process(process_id: int, signal_number: int) -> None:
    raise ProcessLookupError(process_id)
