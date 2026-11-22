"""Which updates sections are off unless asked for, and how long an answer may be, from UPDATES_* environment variables. Every field has a working
default."""

import os

from pydantic import BaseModel, field_validator

from updates_mcp.sections import UpdateSection


class UpdatesSettings(BaseModel):
    default_off: list[UpdateSection] = ["broadway_closings"]  # the user's choice (2026-11-21); UPDATES_DEFAULT_OFF takes names separated by commas
    max_words: int = 900  # seven sections of a few lines each; the newsletters and anime lists are the long ones

    @field_validator("default_off", mode="before")
    @classmethod
    def names_from_a_comma_list(cls, default_off: object) -> object:
        if isinstance(default_off, str):
            return [name.strip() for name in default_off.split(",") if name.strip()]
        return default_off


def updates_settings_from_environment() -> UpdatesSettings:
    """UPDATES_DEFAULT_OFF and UPDATES_MAX_WORDS override the defaults; an empty value counts as unset."""
    overrides = {key.removeprefix("UPDATES_").lower(): value for key, value in os.environ.items() if key.startswith("UPDATES_") and value.strip()}
    return UpdatesSettings(**overrides)
