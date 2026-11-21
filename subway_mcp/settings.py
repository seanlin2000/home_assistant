"""Where MTA's subway feeds are, how long a fetched copy is reused, and how much of it an answer lists, from SUBWAY_* environment variables (design doc
v2/15 section 5). Every field has a working default; the feeds need no key."""

import os
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from utils.user_agent_utils import descriptive_user_agent

FEEDS_BASE_URL = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/"
TRAIN_FEED_NAMES = ("nyct%2Fgtfs", "nyct%2Fgtfs-ace", "nyct%2Fgtfs-bdfm", "nyct%2Fgtfs-g", "nyct%2Fgtfs-jz", "nyct%2Fgtfs-nqrw", "nyct%2Fgtfs-l", "nyct%2Fgtfs-si")
ALERTS_FEED_NAME = "camsys%2Fsubway-alerts.json"


class SubwaySettings(BaseModel):
    feeds_base_url: str = FEEDS_BASE_URL
    timeout_seconds: float = 8.0
    cache_seconds: float = 20.0
    keep_stale_seconds: float = 300.0  # a copy this old still answers when MTA does not, with its age said
    stale_after_seconds: float = 60.0  # MTA's terms require saying when data may be more than a minute behind
    window_minutes: int = 40
    trains_per_direction: int = 3
    max_alerts: int = 3
    alert_words: int = 40
    user_agent: str = descriptive_user_agent("subway")
    fixtures_dir: Path | None = None  # recorded feeds, read instead of MTA's; set only by the benchmark and tests
    now: datetime | None = None  # the moment the recorded feeds were taken; set only by the benchmark


def subway_settings_from_environment() -> SubwaySettings:
    """SUBWAY_FIXTURES_DIR, SUBWAY_NOW, SUBWAY_WINDOW_MINUTES, and the other fields' names override the defaults; an empty value counts as unset."""
    overrides = {key.removeprefix("SUBWAY_").lower(): value for key, value in os.environ.items() if key.startswith("SUBWAY_") and value.strip()}
    return SubwaySettings(**overrides)
