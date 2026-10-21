"""Expose NBA and NFL scores, rosters, statistics and head-to-heads from ESPN as MCP tools on an existing server, so the agent sees one tool list.

Four tools rather than one, split by the kind of question, so a small model picks by what was asked (design doc v2/03 section 3.4). Every failure is
one sentence telling the model what to do next, never an exception, as the weather and Wikipedia tools do.
"""

import datetime
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Literal

import httpx
from mcp.server.mcpserver import MCPServer
from pydantic import Field

from sports_mcp.answers import day_scores, player_against_player, player_against_team, player_stats, recent_team_scores, season_scores, team_roster
from sports_mcp.cache import SportsCache
from sports_mcp.espn_client import EspnSession, EspnUnavailable
from sports_mcp.espn_records import FoundPlayer
from sports_mcp.fixtures import FixtureTransport
from sports_mcp.leagues import FIRST_SEASON, League
from sports_mcp.render import clipped
from sports_mcp.settings import SportsSettings, sports_today
from sports_mcp.teams import Team, find_teams

GAME_SCORES_TOOL_NAME = "game_scores"
TEAM_ROSTER_TOOL_NAME = "team_roster"
PLAYER_STATS_TOOL_NAME = "player_stats"
PLAYER_MATCHUP_TOOL_NAME = "player_matchup"
MAX_TEAM_CHARS = 40
MAX_PLAYER_CHARS = 60
MAX_DATE_CHARS = 10
SERVICE_DOWN_MESSAGE = "Sports error: ESPN did not answer. Search the web with search_and_read instead."
SPOKEN_DAYS = {"today": 0, "yesterday": -1, "tomorrow": 1}
_LOGGER = logging.getLogger(__name__)

LeagueName = Literal["nba", "nfl"]
TeamName = Annotated[str, Field(max_length=MAX_TEAM_CHARS)]
PlayerName = Annotated[str, Field(max_length=MAX_PLAYER_CHARS)]
DayText = Annotated[str, Field(max_length=MAX_DATE_CHARS)]
Ask = Callable[[EspnSession], Awaitable[str]]


class SportsRequestError(ValueError):
    """The arguments name no team, player, day or season the tools can look up; the message says what to ask the user."""


def register_sports_tools(server: MCPServer, settings: SportsSettings, transport: httpx.AsyncBaseTransport | None = None) -> None:
    cache = SportsCache(settings.cache_dir)
    transport = transport or (FixtureTransport(Path(settings.fixtures_dir)) if settings.fixtures_dir else None)

    async def answered(ask: Ask) -> str:
        return await answered_from_espn(EspnSession(settings, cache, sports_today(settings), transport), ask, settings.max_words)

    @server.tool(name=GAME_SCORES_TOOL_NAME)
    async def game_scores(league: LeagueName, team: TeamName = "", date: DayText = "", season: int | None = None, playoffs: bool = False) -> str:
        """NBA or NFL game scores: live, final, or scheduled, with the quarter and clock, the playoff series, and the top players. team: as the user said it, e.g. "Warriors" or "49ers". With only a team: its game today, its last game, and its next game. date: YYYY-MM-DD, worked out from today's date, for every game that day, or only that team's when a team is given. season: the year the season started (the 2015-16 NBA season is 2015) for every game the team played that season; playoffs: true for its playoff games instead."""
        return await answered(lambda espn: scores_answer(espn, League(league), team, date, season, playoffs))

    @server.tool(name=TEAM_ROSTER_TOOL_NAME)
    async def roster(league: LeagueName, team: TeamName) -> str:
        """An NBA or NFL team's current roster: every player's jersey number, name, position, and injury status. team: as the user said it, e.g. "Golden State Warriors" or "Niners"."""
        return await answered(lambda espn: team_roster(espn, League(league), one_team(League(league), team)))

    @server.tool(name=PLAYER_STATS_TOOL_NAME)
    async def stats(league: LeagueName, player: PlayerName, from_season: int | None = None, to_season: int | None = None) -> str:
        """An NBA or NFL player's regular-season statistics, one row per season plus the career total. NBA: games, points, rebounds and assists per game, 3-pointers made and attempted, field goal %. NFL: passing, rushing, or receiving. player: the full name, e.g. "Stephen Curry". from_season, to_season: the years the first and last seasons started (the 2015-16 NBA season is 2015); leave both empty for the whole career."""
        return await answered(lambda espn: stats_answer(espn, League(league), player, from_season, to_season))

    @server.tool(name=PLAYER_MATCHUP_TOOL_NAME)
    async def matchup(league: LeagueName, player: PlayerName, opponent_player: PlayerName = "", opponent_team: TeamName = "") -> str:
        """Head-to-head: every regular-season and playoff game in which an NBA or NFL player faced another player or a team, with the win-loss record, both players' averages, and each game's score and stat lines. player: the full name, e.g. "Tom Brady". Give opponent_player, e.g. "Peyton Manning", or opponent_team, e.g. "Lakers", not both."""
        return await answered(lambda espn: matchup_answer(espn, League(league), player, opponent_player, opponent_team))


async def answered_from_espn(session: EspnSession, ask: Ask, max_words: int) -> str:
    try:
        async with session as espn:
            return clipped(await ask(espn), max_words)
    except SportsRequestError as error:
        return f"Sports error: {error}"
    except EspnUnavailable as error:
        _LOGGER.warning("sports lookup failed: %s", error)
        return SERVICE_DOWN_MESSAGE


async def scores_answer(espn: EspnSession, league: League, team_name: str, day_text: str, season: int | None, playoffs: bool) -> str:
    """A day's games when a date is given; a team's season when a season (or playoffs) is; otherwise the team's games around today, or today's games."""
    team = one_team(league, team_name) if team_name.strip() else None
    if day_text.strip():
        return await day_scores(espn, league, spoken_day(day_text, espn.today), team)
    if team is None:
        if season is not None:
            raise SportsRequestError("name the team whose season you want, such as the Warriors.")
        return await day_scores(espn, league, espn.today, None)
    if season is not None or playoffs:
        return await season_scores(espn, league, team, checked_season(league, season, espn.today), playoffs)
    return await recent_team_scores(espn, league, team)


async def stats_answer(espn: EspnSession, league: League, player_name: str, from_season: int | None, to_season: int | None) -> str:
    first_season = checked_season(league, from_season, espn.today) if from_season is not None else None
    last_season = checked_season(league, to_season, espn.today) if to_season is not None else None
    if first_season is not None and last_season is not None and first_season > last_season:
        first_season, last_season = last_season, first_season
    return await player_stats(espn, league, await found_player(espn, league, player_name), first_season, last_season)


async def matchup_answer(espn: EspnSession, league: League, player_name: str, opponent_player: str, opponent_team: str) -> str:
    if bool(opponent_player.strip()) == bool(opponent_team.strip()):
        raise SportsRequestError("give either opponent_player or opponent_team, not both or neither.")
    player = await found_player(espn, league, player_name)
    if opponent_team.strip():
        return await player_against_team(espn, league, player, one_team(league, opponent_team))
    return await player_against_player(espn, league, player, await found_player(espn, league, opponent_player))


def one_team(league: League, spoken: str) -> Team:
    teams = find_teams(league, spoken)
    if not teams:
        raise SportsRequestError(f'no {league.label} team called "{spoken.strip()}" was found. Ask the user which team they mean.')
    if len(teams) > 1:
        raise SportsRequestError(f'"{spoken.strip()}" could mean the {" or the ".join(team.display_name for team in teams)}. Ask the user which one.')
    return teams[0]


async def found_player(espn: EspnSession, league: League, spoken: str) -> FoundPlayer:
    player = await espn.find_player(league, spoken.strip()) if spoken.strip() else None
    if player is None:
        raise SportsRequestError(f'no {league.label} player called "{spoken.strip()}" was found. Ask the user to say the name again.')
    return player


def spoken_day(text: str, today: datetime.date) -> datetime.date:
    """YYYY-MM-DD as the prompt asks, with "today", "yesterday" and "tomorrow" also taken, since a small model sometimes passes the word."""
    wanted = text.strip().lower()
    if wanted in SPOKEN_DAYS:
        return today + datetime.timedelta(days=SPOKEN_DAYS[wanted])
    try:
        day = datetime.date.fromisoformat(wanted)
    except ValueError as error:
        raise SportsRequestError(f'"{text.strip()}" is not a date; pass it as YYYY-MM-DD, worked out from today\'s date.') from error
    if not FIRST_SEASON <= day.year <= today.year + 1:
        raise SportsRequestError(f"ESPN's scores start in {FIRST_SEASON}; ask about a date from then to next year.")
    return day


def checked_season(league: League, season: int | None, today: datetime.date) -> int:
    current = league.current_season(today)
    start_year = current if season is None else season
    if not FIRST_SEASON <= start_year <= current + 1:
        raise SportsRequestError(f"pass a season as the year it started, from {FIRST_SEASON} to {current}; the {league.label} season in progress is {league.season_label(current)}.")
    return start_year
