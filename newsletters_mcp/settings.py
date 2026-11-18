"""Where the newsletters are kept, which Gmail label they come from, and how long they stay, from NEWSLETTERS_* environment variables (design doc
v2/14 section 5). Every field has a working default."""

import os
from datetime import date
from pathlib import Path

from pydantic import BaseModel

DEFAULT_NEWSLETTERS_DIR = Path.home() / "Library" / "Application Support" / "studio-assistant" / "newsletters"


class NewslettersSettings(BaseModel):
    dir: Path = DEFAULT_NEWSLETTERS_DIR
    mailbox: str = "Newsletters"  # the Gmail label the user's filter fills; Gmail shows labels as IMAP folders
    look_back_days: int = 2  # each pull searches this far back, so a missed hourly run loses nothing
    keep_days: int = 30
    imap_host: str = "imap.gmail.com"
    imap_timeout_seconds: float = 30.0  # without one, a single hung run would block every later hourly run
    keychain_service: str = "studio-assistant-gmail"  # its account is the Gmail address, its secret the app password
    stale_after_hours: float = 3.0  # the health check fails once the last good pull is older than this
    today: date | None = None  # set only by the benchmark, which pins its day of made-up issues


def newsletters_settings_from_environment() -> NewslettersSettings:
    """NEWSLETTERS_DIR, NEWSLETTERS_TODAY, NEWSLETTERS_MAILBOX, and the other fields' names override the defaults; an empty value counts as unset."""
    overrides = {key.removeprefix("NEWSLETTERS_").lower(): value for key, value in os.environ.items() if key.startswith("NEWSLETTERS_") and value.strip()}
    return NewslettersSettings(**overrides)
