"""Parsed ESPN rows on disk, each kept for as long as its kind can change (design doc v2/03 section 3.4).

Rows are kept, not ESPN's JSON: one NBA matchup reads 25 MB of game logs, of which a few kilobytes are used. No cache directory turns it off.
"""

from typing import Any

import diskcache

FOREVER: float | None = None  # a past day's scores, a finished season, a player's id
LIVE_SECONDS = 30.0  # today's scores and any game in progress
SCHEDULE_SECONDS = 300.0  # the season in progress, as a team's schedule: a result appears within five minutes of the final whistle
CURRENT_SEASON_SECONDS = 3600.0  # the season in progress, as a player's statistics and game logs
ROSTER_SECONDS = 12 * 3600.0


class SportsCache:
    def __init__(self, cache_dir: str | None) -> None:
        self._cache = diskcache.Cache(cache_dir) if cache_dir else None

    def get(self, key: str) -> Any:
        return None if self._cache is None else self._cache.get(key)

    def put(self, key: str, value: Any, keep_seconds: float | None) -> None:
        if self._cache is not None:
            self._cache.set(key, value, expire=keep_seconds)
