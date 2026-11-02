"""Where the Michelin Guide is, where the monthly refresh keeps its snapshot, and how gently it reads, from RESTAURANTS_* environment variables. Every
field has a working default."""

import os
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from utils.snapshot_utils import DEFAULT_LISTINGS_DIR


class RestaurantsSettings(BaseModel):
    guide_url: str = "https://guide.michelin.com/us/en"
    timeout_seconds: float = 20.0
    seconds_between_requests: float = 2.0  # about 180 listing pages and, the first month, 530 restaurant pages; a few dozen in later months
    refresh_after_days: int = 28  # the nightly listings job reads Michelin only once the snapshot is this old
    snapshot_path: Path = DEFAULT_LISTINGS_DIR / "restaurants.json"
    descriptions_path: Path = DEFAULT_LISTINGS_DIR / "restaurant_descriptions.json"  # read while answering, kept until the next monthly refresh
    pages_read_at_once: int = 4  # restaurant pages read together while answering, so ten descriptions take a few seconds rather than ten
    max_words: int = 900  # ten restaurants with a sentence of description each came to about 600 words
    stale_after_days: int = 35  # a missed monthly refresh, plus a week; older than this, an answer says how old its listings are
    today: date | None = None  # the day the benchmark's snapshot was taken; set only by the benchmark
    user_agent: str = ""  # empty sends what current Chrome sends (utils/browser_utils.py); Michelin's firewall challenges old Chrome versions


def restaurants_settings_from_environment() -> RestaurantsSettings:
    """RESTAURANTS_SNAPSHOT_PATH, RESTAURANTS_TODAY, RESTAURANTS_REFRESH_AFTER_DAYS, and the other fields' names override the defaults; an empty value
    counts as unset."""
    overrides = {key.removeprefix("RESTAURANTS_").lower(): value for key, value in os.environ.items() if key.startswith("RESTAURANTS_") and value.strip()}
    return RestaurantsSettings(**overrides)
