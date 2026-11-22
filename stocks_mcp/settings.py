"""Where Finnhub's API is, how long its replies are reused, and when a trade counts as current, from STOCKS_* environment variables (design doc v2/16
section 5). Every field has a working default; the key itself lives in the Keychain, not here."""

import os
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from utils.user_agent_utils import descriptive_user_agent

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


class StocksSettings(BaseModel):
    base_url: str = FINNHUB_BASE_URL
    timeout_seconds: float = 8.0
    quote_cache_seconds: float = 60.0  # while the market is open; a closed market's quote is held until the next open
    metric_cache_seconds: float = 21600.0  # Finnhub computes the metrics from daily closes
    search_cache_seconds: float = 86400.0
    fresh_trade_minutes: float = 30.0  # a younger last trade during trading hours is said as a time, an older one as a close
    user_agent: str = descriptive_user_agent("stocks")
    fixtures_dir: Path | None = None  # recorded replies, read instead of Finnhub's; set only by the benchmark and tests
    now: datetime | None = None  # the moment the replies were recorded; set only by the benchmark


def stocks_settings_from_environment() -> StocksSettings:
    """STOCKS_FIXTURES_DIR, STOCKS_NOW, STOCKS_QUOTE_CACHE_SECONDS, and the other fields' names override the defaults; an empty value counts as unset."""
    overrides = {key.removeprefix("STOCKS_").lower(): value for key, value in os.environ.items() if key.startswith("STOCKS_") and value.strip()}
    return StocksSettings(**overrides)
