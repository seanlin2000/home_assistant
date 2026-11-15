"""Whether the local SearXNG should be running.

Brave answers searches first, and SearXNG is asked only when Brave fails. Docker Desktop, which SearXNG runs in, holds about 1.5 GB on the Studio, so
SearXNG runs only while something might need it: Brave's monthly credit is nearly spent, its key is missing, it failed within the last hour, or a
benchmark is running. The health check reads the demand every five minutes and starts or stops SearXNG to match it. The judgement is a pure
function of the demand, so the thresholds are unit-tested without the Keychain, Docker, or a clock.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from pydantic import BaseModel

from ops import paths
from web_search_mcp import brave_client
from web_search_mcp.brave_client import BraveFailure, brave_failures, brave_key_stored, dollars_left_this_month


class SearxngPolicy(BaseModel):
    below_brave_dollars: float = 0.20  # 40 searches of the month's $5 credit left
    after_brave_failure_seconds: float = 60 * 60  # long enough that a Brave outage which comes and goes does not start and stop Docker each time


class SearxngDemand(BaseModel):
    brave_dollars_left: float
    brave_key_stored: bool
    last_brave_failure: BraveFailure | None
    benchmark_running: bool


class SearxngVerdict(BaseModel):
    reason: str | None  # why SearXNG should run; None when nothing needs it
    idle_detail: str = ""  # what the health snapshot says while SearXNG is off on purpose


def read_searxng_demand(now: datetime) -> SearxngDemand:
    failures = brave_failures(brave_client.FAILURES_FILE)
    return SearxngDemand(
        brave_dollars_left=dollars_left_this_month(brave_client.USAGE_FILE, now.astimezone().date()),
        brave_key_stored=brave_key_stored(),
        last_brave_failure=failures[-1] if failures else None,
        benchmark_running=lease_holder_alive(),
    )


def judge_searxng_demand(demand: SearxngDemand, policy: SearxngPolicy, now: datetime) -> SearxngVerdict:
    idle_detail = f"off on purpose: Brave has ${demand.brave_dollars_left:.2f} of this month's credit left and has not failed in the last hour"
    return SearxngVerdict(reason=searxng_reason(demand, policy, now), idle_detail=idle_detail)


def searxng_reason(demand: SearxngDemand, policy: SearxngPolicy, now: datetime) -> str | None:
    if not demand.brave_key_stored:
        return "no Brave key in the Keychain"
    if demand.brave_dollars_left < policy.below_brave_dollars:
        return f"Brave has ${max(demand.brave_dollars_left, 0):.2f} of this month's credit left"
    failure = demand.last_brave_failure
    if failure is not None and (now - failure.at).total_seconds() < policy.after_brave_failure_seconds:
        return f"Brave failed {minutes_ago(failure.at, now)} ({failure.reason})"
    if demand.benchmark_running:
        return "a benchmark is running"
    return None


def minutes_ago(then: datetime, now: datetime) -> str:
    minutes = int((now - then).total_seconds() // 60)
    return "under a minute ago" if minutes < 1 else f"{minutes} min ago"


@contextmanager
def searxng_lease() -> Iterator[None]:
    """Held by a benchmark run for its whole length: the health check leaves SearXNG running while the process named in the lease is alive. A run
    that dies without releasing it leaves a stale lease, which counts for nothing because its process is gone."""
    lease = paths.searxng_lease()
    lease.parent.mkdir(parents=True, exist_ok=True)
    lease.write_text(str(os.getpid()))
    try:
        yield
    finally:
        lease.unlink(missing_ok=True)


def lease_holder_alive() -> bool:
    try:
        holder = int(paths.searxng_lease().read_text().strip())
    except (OSError, ValueError):
        return False
    return process_alive(holder)


def process_alive(process_id: int) -> bool:
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # it exists, under another user
    return True
