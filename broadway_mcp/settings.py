"""Where TodayTix is, where the nightly refresh keeps its snapshot, and how old a snapshot may be before answers say so, from BROADWAY_* environment
variables. Every field has a working default."""

import os
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from utils.snapshot_utils import DEFAULT_LISTINGS_DIR

# The same browser user agent the search server sends: a personal assistant reading one listing a night, not a crawler.
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
NEW_YORK_LOCATION_ID = 1


class BroadwaySettings(BaseModel):
    shows_url: str = "https://api.todaytix.com/api/v2/shows"
    location_id: int = NEW_YORK_LOCATION_ID
    products_per_request: int = 300  # New York had 287 products on 2026-10-25; one request reads them all
    timeout_seconds: float = 30.0  # the answer is about 3 MB
    snapshot_path: Path = DEFAULT_LISTINGS_DIR / "broadway.json"
    stale_after_days: int = 3  # the refresh runs nightly; older than this, an answer says how old its listings are
    max_words: int = 800  # 25 shows at about 28 words a line, the " | " between parts counted as words; inside a tool result's allowance (design doc v2/04)
    today: date | None = None  # the day the benchmark's snapshot was taken; set only by the benchmark
    user_agent: str = USER_AGENT


def broadway_settings_from_environment() -> BroadwaySettings:
    """BROADWAY_SNAPSHOT_PATH, BROADWAY_TODAY, BROADWAY_STALE_AFTER_DAYS, BROADWAY_TIMEOUT_SECONDS, and BROADWAY_MAX_WORDS override the defaults; an
    empty value counts as unset."""
    overrides = {key.removeprefix("BROADWAY_").lower(): value for key, value in os.environ.items() if key.startswith("BROADWAY_") and value.strip()}
    return BroadwaySettings(**overrides)


def broadway_today(settings: BroadwaySettings) -> date:
    """The user's local date, unless the benchmark pins it to the day its snapshot was taken."""
    return settings.today or date.today()
