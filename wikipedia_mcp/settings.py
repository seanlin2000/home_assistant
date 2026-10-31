"""Where Wikipedia is and how much of an article reaches the model, from WIKIPEDIA_* environment variables. Every field has a working default."""

import os

from pydantic import BaseModel

from utils.user_agent_utils import descriptive_user_agent

# Wikimedia's User-Agent policy asks for the application's name and version, then a way to reach its owner in parentheses.
USER_AGENT = descriptive_user_agent("wikipedia")


class WikipediaSettings(BaseModel):
    base_url: str = "https://en.wikipedia.org"
    timeout_seconds: float = 8.0
    max_words: int = 900  # what wikipedia_lookup returns; search_and_read clips its Wikipedia pages to its own words_per_page instead
    titles_to_offer: int = 5
    user_agent: str = USER_AGENT


def wikipedia_settings_from_environment() -> WikipediaSettings:
    """WIKIPEDIA_BASE_URL, WIKIPEDIA_TIMEOUT_SECONDS, WIKIPEDIA_MAX_WORDS, and WIKIPEDIA_TITLES_TO_OFFER override the defaults; an empty value counts as unset."""
    overrides = {key.removeprefix("WIKIPEDIA_").lower(): value for key, value in os.environ.items() if key.startswith("WIKIPEDIA_") and value.strip()}
    return WikipediaSettings(**overrides)
