"""The two leagues the sports tools cover, and how ESPN names their seasons.

A season is spoken as the year it started: the NBA's 2015-16 season is 2015, and the NFL's 2015 season is 2015. ESPN names NBA seasons by the year
they end, so the NBA's ESPN year is one more. Games are dated in US Eastern time, as ESPN's scoreboard dates them.
"""

from datetime import date
from enum import StrEnum
from zoneinfo import ZoneInfo

LEAGUE_TIMEZONE = ZoneInfo("America/New_York")
FIRST_SEASON = 1980
NBA_SEASON_STARTS_IN_MONTH = 8  # from August the coming season is the current one; its games start in October
NFL_SEASON_STARTS_IN_MONTH = 3  # until March the season that started last September is still the current one


class League(StrEnum):
    NBA = "nba"
    NFL = "nfl"

    @property
    def espn_path(self) -> str:
        return "basketball/nba" if self is League.NBA else "football/nfl"

    @property
    def espn_code(self) -> str:
        """The league's number in ESPN's ids, such as s:40~l:46~a:3975 for an NBA player."""
        return "46" if self is League.NBA else "28"

    @property
    def label(self) -> str:
        return self.value.upper()

    def espn_season(self, start_year: int) -> int:
        return start_year + 1 if self is League.NBA else start_year

    def start_year(self, espn_season: int) -> int:
        return espn_season - 1 if self is League.NBA else espn_season

    def season_label(self, start_year: int) -> str:
        return f"{start_year}-{(start_year + 1) % 100:02d}" if self is League.NBA else str(start_year)

    def current_season(self, today: date) -> int:
        """The start year of the season in progress or about to start."""
        starts_in_month = NBA_SEASON_STARTS_IN_MONTH if self is League.NBA else NFL_SEASON_STARTS_IN_MONTH
        return today.year if today.month >= starts_in_month else today.year - 1
