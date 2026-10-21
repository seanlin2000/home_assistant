"""Where ESPN is, how hard the tools may lean on it, and where its answers are kept, from SPORTS_* environment variables. Every field has a working default."""

import os
from datetime import date
from pathlib import Path

from pydantic import BaseModel

# ESPN publishes no etiquette for these addresses; naming the application and its repository lets ESPN tell this client apart, without any
# personal address leaving the network.
USER_AGENT = "studio-assistant-sports/1.0 github.com/seanlin2000/home_assistant"
DEFAULT_CACHE_DIR = Path.home() / "Library" / "Caches" / "studio-assistant" / "sports"


class SportsSettings(BaseModel):
    site_base_url: str = "https://site.api.espn.com/apis/site/v2/sports"
    web_base_url: str = "https://site.web.api.espn.com/apis"
    timeout_seconds: float = 10.0
    requests_at_a_time: int = 4  # a matchup reads dozens of game logs; four at a time took 1.2 s for Brady against Manning
    max_words: int = 600  # about 800 tokens, well inside a tool result's allowance (design doc v2/04)
    box_score_max_words: int = 900  # a whole NBA box score is about 700 words, a third of them the | between figures; still inside the allowance
    cache_dir: str | None = str(DEFAULT_CACHE_DIR)  # unlike the other tools, kept in the product: most of what sports reads never changes
    fixtures_dir: str | None = None  # recorded ESPN responses, set only by the benchmark (design doc v2/01 section 3.3)
    today: date | None = None  # the day the recordings were made, so "today's game" asks for a recorded scoreboard; set only by the benchmark
    user_agent: str = USER_AGENT


def sports_settings_from_environment() -> SportsSettings:
    """SPORTS_CACHE_DIR, SPORTS_FIXTURES_DIR, SPORTS_TODAY, SPORTS_TIMEOUT_SECONDS, SPORTS_REQUESTS_AT_A_TIME, SPORTS_MAX_WORDS, and SPORTS_BOX_SCORE_MAX_WORDS override the defaults; an empty value counts as unset."""
    overrides = {key.removeprefix("SPORTS_").lower(): value for key, value in os.environ.items() if key.startswith("SPORTS_") and value.strip()}
    return SportsSettings(**overrides)


def sports_today(settings: SportsSettings) -> date:
    """The user's local date, as the harness puts it in the prompt, unless the benchmark pins it."""
    return settings.today or date.today()
