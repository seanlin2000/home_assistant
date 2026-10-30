"""Where Arctic Shift is, how many threads and comments an answer carries, and how hard the tool retries, from REDDIT_* environment variables. Every
field has a working default."""

import os

from pydantic import BaseModel

# Arctic Shift asks heavy users to identify themselves; naming the application and its repository does that without any personal address leaving the network.
USER_AGENT = "studio-assistant-reddit/1.0 github.com/seanlin2000/home_assistant"


class RedditSettings(BaseModel):
    arctic_shift_url: str = "https://arctic-shift.photon-reddit.com/api"
    timeout_seconds: float = 8.0
    attempts: int = 3
    retry_waits_seconds: tuple[float, ...] = (2.0, 5.0)  # before the second and the third attempt
    # A keyword search that Arctic Shift turned away usually fails again however long the wait (2 of 9 retries after its 60-second window succeeded,
    # measured 2026-10-29), so it gets one retry; the thread and comment reads it serves in under a second get the full attempts.
    keyword_search_attempts: int = 2
    total_budget_seconds: float = 20.0  # every attempt and wait of one tool call, well inside the agent loop's 30-second tool timeout
    max_subreddits: int = 3  # each costs one web search, and live searches are at least three seconds apart
    candidate_posts: int = 100  # Arctic Shift sorts keyword matches by date only, so the tool reads this many and ranks them itself
    threads_to_return: int = 4
    comment_reads_at_a_time: int = 2
    comments_per_thread: int = 4
    words_per_post: int = 50
    words_per_comment: int = 60
    max_words: int = 800
    user_agent: str = USER_AGENT


def reddit_settings_from_environment() -> RedditSettings:
    """REDDIT_ARCTIC_SHIFT_URL, REDDIT_TIMEOUT_SECONDS, REDDIT_ATTEMPTS, REDDIT_MAX_WORDS, and the other field names override the defaults; an empty
    value counts as unset."""
    overrides = {key.removeprefix("REDDIT_").lower(): value for key, value in os.environ.items() if key.startswith("REDDIT_") and value.strip()}
    return RedditSettings(**overrides)
