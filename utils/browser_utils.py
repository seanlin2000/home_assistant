"""The browser user agent sent by the tools that read pages made for people (the search server's page reader and the listings refreshes): a personal
assistant reading what one person would, not a crawler.

Sites behind a bot filter turn away browsers a few versions old: on 2026-10-30 guide.michelin.com challenged Chrome 128 and served Chrome 141. So the
major version follows Chrome's own releases. The nightly listings refresh records the newest Chrome that Macs have fully rolled out
(ops/chrome_releases.py), and this module reads that record once a day, never naming a version older than the checked-in fallback.
"""

from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from utils.snapshot_utils import DEFAULT_LISTINGS_DIR, SnapshotMissing, read_snapshot

# Exactly what Chrome on a Mac sends: Chrome freezes the macOS version at 10_15_7 and zeroes the minor version numbers, so any other form marks the
# request as not a real browser.
USER_AGENT_TEMPLATE = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
FALLBACK_CHROME_MAJOR = 156  # stable on 2026-10-30; named until the nightly refresh has recorded a release, as on a Mac without the listings agent
CHROME_RELEASE_PATH = DEFAULT_LISTINGS_DIR / "chrome_release.json"


class ChromeRelease(BaseModel):
    refreshed_at: datetime
    major: int
    version: str  # the full version the major came from, e.g. "156.0.8078.80"


def chosen_user_agent(override: str) -> str:
    """The agent a tool's settings name, or what current Chrome sends when they name none."""
    return override or browser_user_agent()


def browser_user_agent() -> str:
    return USER_AGENT_TEMPLATE.format(major=chrome_major_on(date.today()))


@lru_cache(maxsize=1)
def chrome_major_on(day: date) -> int:
    """Keyed by the day so the record is read once a day: a tool server runs for weeks, so the version cannot be fixed when it starts."""
    return max(FALLBACK_CHROME_MAJOR, recorded_chrome_major(CHROME_RELEASE_PATH))


def recorded_chrome_major(path: Path) -> int:
    try:
        return read_snapshot(path, ChromeRelease).major
    except SnapshotMissing:
        return FALLBACK_CHROME_MAJOR
