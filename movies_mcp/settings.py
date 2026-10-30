"""Where Fandango's theater listings and movie pages are, how many days of listings the nightly refresh reads, and how old a snapshot may be before answers say so, from
MOVIES_* environment variables. Every field has a working default."""

import os
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from utils.browser_utils import BROWSER_USER_AGENT
from utils.snapshot_utils import DEFAULT_LISTINGS_DIR

TIMES_SQUARE_ZIP_CODE = "10036"


class MoviesSettings(BaseModel):
    listing_page_url: str = "https://www.fandango.com/{zip_code}_movietimes"  # read once first: it sets the cookies the JSON below asks for
    theaters_url: str = "https://www.fandango.com/napi/theaterswithshowtimes"
    ratings_url: str = "https://www.fandango.com/napi/fanAndCriticRatings/{movie_id}"
    movie_page_url: str = "https://www.fandango.com{page_path}"
    zip_code: str = TIMES_SQUARE_ZIP_CODE  # Fandango lists theaters by distance from it; all 23 Manhattan theaters were on the first page of 50
    days: int = 60  # as far ahead as theaters sell tickets: 23 movies had Manhattan showings on sale two weeks out, 3 two months out
    theaters_per_request: int = 50
    seconds_between_requests: float = 1.0  # one request at a time: about 120 listing pages, then a scores read per movie and a page per new movie
    timeout_seconds: float = 30.0  # a page is up to about 4 MB
    snapshot_path: Path = DEFAULT_LISTINGS_DIR / "movies.json"
    stale_after_days: int = 3  # the refresh runs nightly; older than this, an answer says how old its listings are
    max_words: int = 1000
    today: date | None = None  # the day the benchmark's snapshot was taken; set only by the benchmark
    user_agent: str = BROWSER_USER_AGENT


def movies_settings_from_environment() -> MoviesSettings:
    """MOVIES_SNAPSHOT_PATH, MOVIES_TODAY, MOVIES_STALE_AFTER_DAYS, MOVIES_TIMEOUT_SECONDS, MOVIES_MAX_WORDS, and the other field names override the
    defaults; an empty value counts as unset."""
    overrides = {key.removeprefix("MOVIES_").lower(): value for key, value in os.environ.items() if key.startswith("MOVIES_") and value.strip()}
    return MoviesSettings(**overrides)
