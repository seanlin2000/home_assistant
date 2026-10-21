"""Reads ESPN's public JSON for the sports tools: scoreboards, team schedules, rosters, player search, season statistics and game logs.

The hosts are fixed by settings, not chosen by the model, so requests skip the public-address guard that fetch_page applies, as the Wikipedia and
Met.no clients do; a redirect is refused instead of followed. ESPN publishes no rate limit, so the client sends at most a few requests at a time,
and keeps every answer for as long as sports_mcp.cache says its kind can change. One session serves one tool call and shares its connections.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from types import TracebackType
from typing import Any, TypeVar

import httpx
from pydantic import TypeAdapter

from sports_mcp.cache import CURRENT_SEASON_SECONDS, FOREVER, LIVE_SECONDS, ROSTER_SECONDS, SCHEDULE_SECONDS, SportsCache
from sports_mcp.espn_records import (
    EspnShapeError,
    FoundPlayer,
    Game,
    LoggedGame,
    PlayerSeasons,
    Roster,
    read_found_player,
    read_game_log,
    read_games,
    read_player_seasons,
    read_roster,
)
from sports_mcp.leagues import League
from sports_mcp.settings import SportsSettings
from sports_mcp.teams import Team, normalized, team_by_id

OK = 200
REGULAR_SEASON_TYPE = 2
PLAYOFFS_SEASON_TYPE = 3
PLAYERS_TO_SEARCH = 10
Parsed = TypeVar("Parsed")


class EspnUnavailable(RuntimeError):
    """ESPN did not answer, refused, redirected, or answered in a shape the tools cannot read."""


class EspnSession:
    def __init__(self, settings: SportsSettings, cache: SportsCache, today: date, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._settings = settings
        self._cache = cache
        self._today = today
        self._transport = transport  # injectable so tests and the benchmark can serve recorded answers without a socket
        self._limit = asyncio.Semaphore(settings.requests_at_a_time)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "EspnSession":
        headers = {"User-Agent": self._settings.user_agent}
        self._client = httpx.AsyncClient(timeout=self._settings.timeout_seconds, follow_redirects=False, headers=headers, transport=self._transport)
        return self

    async def __aexit__(self, error_type: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None) -> None:
        if self._client is not None:
            await self._client.aclose()

    @property
    def today(self) -> date:
        return self._today

    async def scoreboard(self, league: League, day: date) -> list[Game]:
        """Every game on a day, as ESPN's scoreboard dates them (US Eastern time)."""
        keep = FOREVER if day < self._today - timedelta(days=1) else LIVE_SECONDS
        url = f"{self._settings.site_base_url}/{league.espn_path}/scoreboard"
        return await self._kept(f"scores:{league}:{day.isoformat()}", keep, TypeAdapter(list[Game]), lambda: self._read(url, {"dates": f"{day:%Y%m%d}"}, read_games))

    async def schedule(self, league: League, team: Team, start_year: int, playoffs: bool) -> list[Game]:
        season_type = PLAYOFFS_SEASON_TYPE if playoffs else REGULAR_SEASON_TYPE
        keep = FOREVER if start_year < league.current_season(self._today) else SCHEDULE_SECONDS
        url = f"{self._settings.site_base_url}/{league.espn_path}/teams/{team.espn_id}/schedule"
        params = {"season": league.espn_season(start_year), "seasontype": season_type}
        return await self._kept(f"schedule:{league}:{team.espn_id}:{start_year}:{season_type}", keep, TypeAdapter(list[Game]), lambda: self._read(url, params, read_games))

    async def roster(self, league: League, team: Team) -> Roster:
        url = f"{self._settings.site_base_url}/{league.espn_path}/teams/{team.espn_id}/roster"
        return await self._kept(f"roster:{league}:{team.espn_id}", ROSTER_SECONDS, TypeAdapter(Roster), lambda: self._read(url, {}, read_roster))

    async def find_player(self, league: League, spoken: str) -> FoundPlayer | None:
        """ESPN's best-known player of that name in the league. A miss is not kept, so a player ESPN adds later is found."""
        key = f"player:{league}:{normalized(spoken)}"
        kept = self._cache.get(key)
        if kept is not None:
            return FoundPlayer.model_validate(kept)
        params = {"query": " ".join(spoken.lower().split()), "limit": PLAYERS_TO_SEARCH, "type": "player"}  # one spelling per name, so a recording matches "LeBron" and "Lebron"
        found = await self._read(f"{self._settings.web_base_url}/search/v2", params, lambda body: read_found_player(body, league))
        if found is not None:
            self._cache.put(key, found.model_dump(mode="json"), FOREVER)
        return found

    async def player_seasons(self, league: League, player: FoundPlayer) -> PlayerSeasons:
        url = f"{self._settings.web_base_url}/common/v3/sports/{league.espn_path}/athletes/{player.espn_id}/stats"
        return await self._kept(f"seasons:{league}:{player.espn_id}", CURRENT_SEASON_SECONDS, TypeAdapter(PlayerSeasons), lambda: self._read(url, {}, read_player_seasons))

    async def game_logs(self, league: League, player: FoundPlayer, espn_seasons: list[int]) -> list[LoggedGame]:
        """Every regular-season and playoff game of those seasons, read a few seasons at a time."""
        seasons = await asyncio.gather(*(self.game_log(league, player, espn_season) for espn_season in espn_seasons))
        return [game for season in seasons for game in season if is_between_league_teams(league, game)]

    async def game_log(self, league: League, player: FoundPlayer, espn_season: int) -> list[LoggedGame]:
        finished = league.start_year(espn_season) < league.current_season(self._today)
        url = f"{self._settings.web_base_url}/common/v3/sports/{league.espn_path}/athletes/{player.espn_id}/gamelog"
        key = f"gamelog:{league}:{player.espn_id}:{espn_season}"
        return await self._kept(key, FOREVER if finished else CURRENT_SEASON_SECONDS, TypeAdapter(list[LoggedGame]), lambda: self._read(url, {"season": espn_season}, read_game_log))

    async def _kept(self, key: str, keep_seconds: float | None, shape: TypeAdapter[Parsed], fetch: Callable[[], Awaitable[Parsed]]) -> Parsed:
        kept = self._cache.get(key)
        if kept is not None:
            return shape.validate_python(kept)
        fresh = await fetch()
        self._cache.put(key, shape.dump_python(fresh, mode="json"), keep_seconds)
        return fresh

    async def _read(self, url: str, params: dict[str, Any], reader: Callable[[dict[str, Any]], Parsed]) -> Parsed:
        try:
            return reader(await self._json(url, params))
        except EspnShapeError as error:
            raise EspnUnavailable(f"ESPN answered {httpx.URL(url).path} in an unexpected shape ({error})") from error

    async def _json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        assert self._client is not None, "EspnSession is used inside async with"
        try:
            async with self._limit:
                response = await self._client.get(url, params=params)
        except httpx.HTTPError as error:
            raise EspnUnavailable(f"no answer from ESPN ({type(error).__name__})") from error
        if response.status_code != OK:
            raise EspnUnavailable(f"ESPN answered {response.status_code} for {response.request.url.path}")
        try:
            return response.json()
        except ValueError as error:
            raise EspnUnavailable(f"ESPN's answer for {response.request.url.path} was not JSON") from error


def is_between_league_teams(league: League, game: LoggedGame) -> bool:
    """ESPN files the All-Star Game and the Pro Bowl under the regular season in a game log, with made-up teams; filtered here, after the cache, so logs already kept are filtered too."""
    return team_by_id(league, game.team_id) is not None and team_by_id(league, game.opponent_id) is not None
