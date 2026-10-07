"""Where Wikipedia is and how much of an article reaches the model, from WIKIPEDIA_* environment variables. Every field has a working default."""

import os

from pydantic import BaseModel

# Wikimedia's API etiquette asks for a User-Agent that names the application and a way to reach its owner; the repository serves as the contact,
# so no personal address ever leaves the network.
USER_AGENT = "studio-assistant-wikipedia/1.0 github.com/seanlin2000/home_assistant"


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
