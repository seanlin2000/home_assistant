import os

from pydantic import BaseModel


class SearchSettings(BaseModel):
    searxng_url: str = "http://127.0.0.1:8080"
    host: str = "127.0.0.1"
    port: int = 8765
    pages_to_read: int = 4
    words_per_page: int = 600
    total_word_budget: int = 2000
    fetch_timeout_seconds: float = 6.0
    results_to_return: int = 8
    cache_dir: str | None = None
    user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    blocked_domains: tuple[str, ...] = (
        "facebook.com",
        "instagram.com",
        "x.com",
        "twitter.com",
        "tiktok.com",
        "pinterest.com",
        "linkedin.com",
        "wsj.com",
        "ft.com",
        "bloomberg.com",
        "nytimes.com",
    )


def settings_from_environment() -> SearchSettings:
    """Environment variables prefixed WEB_SEARCH_ override the defaults, e.g. WEB_SEARCH_CACHE_DIR for a benchmark run."""
    overrides = {key.removeprefix("WEB_SEARCH_").lower(): value for key, value in os.environ.items() if key.startswith("WEB_SEARCH_")}
    return SearchSettings(**overrides)
