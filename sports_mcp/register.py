"""Expose NBA and NFL scores, box scores, rosters, statistics and head-to-heads from ESPN as MCP tools on an existing server, so the agent sees one tool list.

Five tools rather than one, split by the kind of question, so a small model picks by what was asked (design doc v2/03 section 3.4). Every failure is
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

from sports_mcp.answers import day_scores, game_box_score, player_against_player, player_against_team, player_stats, recent_team_scores, season_scores, team_roster
from sports_mcp.cache import SportsCache
from sports_mcp.espn_client import EspnSession, EspnUnavailable
from sports_mcp.espn_records import FoundPlayer
from sports_mcp.fixtures import FixtureTransport
from sports_mcp.leagues import FIRST_SEASON, League
from sports_mcp.render import clipped
from sports_mcp.settings import SportsSettings, sports_today
from sports_mcp.teams import Team, find_teams

GAME_SCORES_TOOL_NAME = "game_scores"
BOX_SCORE_TOOL_NAME = "box_score"
TEAM_ROSTER_TOOL_NAME = "team_roster"
PLAYER_STATS_TOOL_NAME = "player_stats"
PLAYER_MATCHUP_TOOL_NAME = "player_matchup"
MAX_TEAM_CHARS = 40
MAX_PLAYER_CHARS = 60
MAX_DATE_CHARS = 10
SERVICE_DOWN_MESSAGE = "Sports error: ESPN did not answer. Search the web with search_and_read instead."
SPOKEN_DAYS = {"today": 0, "yesterday": -1, "tomorrow": 1}
USE_BEFORE_SEARCH = "Use the sports tools, never a web search, for NBA and NFL games, players and teams."
READ_AS_GIVEN = "Say numbers as given; never add, round or estimate. If the heading names a different team or player than the user meant, say so."
SEASON_FORMAT = "year the season started (2015-16 is 2015)"
_LOGGER = logging.getLogger(__name__)

LeagueName = Annotated[Literal["nba", "nfl"], Field(description="the league")]
TeamName = Annotated[str, Field(max_length=MAX_TEAM_CHARS)]
PlayerName = Annotated[str, Field(max_length=MAX_PLAYER_CHARS)]
DayText = Annotated[str, Field(max_length=MAX_DATE_CHARS)]
Ask = Callable[[EspnSession], Awaitable[str]]


class SportsRequestError(ValueError):
    """The arguments name no team, player, day or season the tools can look up; the message says what to ask the user."""


def register_sports_tools(server: MCPServer, settings: SportsSettings, transport: httpx.AsyncBaseTransport | None = None) -> None:
    cache = SportsCache(settings.cache_dir)
    transport = transport or (FixtureTransport(Path(settings.fixtures_dir)) if settings.fixtures_dir else None)

    async def answered(ask: Ask, max_words: int = settings.max_words) -> str:
        return await answered_from_espn(EspnSession(settings, cache, sports_today(settings), transport), ask, max_words)

    @server.tool(name=GAME_SCORES_TOOL_NAME, description=f"NBA or NFL scores: live, final or scheduled, with clock, playoff series and top players. {USE_BEFORE_SEARCH} {READ_AS_GIVEN}")
    async def game_scores(
        league: LeagueName,
        team: Annotated[TeamName, Field(description='as the user said it, e.g. "Warriors"; alone: its last, current and next game')] = "",
        date: Annotated[DayText, Field(description="YYYY-MM-DD: that day's games")] = "",
        season: Annotated[int | None, Field(description=f"{SEASON_FORMAT}: the team's whole season")] = None,
        playoffs: Annotated[bool, Field(description="true for the team's playoff games")] = False,
    ) -> str:
        return await answered(lambda espn: scores_answer(espn, League(league), team, date, season, playoffs))

    @server.tool(name=BOX_SCORE_TOOL_NAME, description=f"One NBA or NFL game's box score: player statistics and team totals. {USE_BEFORE_SEARCH} {READ_AS_GIVEN}")
    async def box_score(
        league: LeagueName,
        team: Annotated[TeamName, Field(description='as the user said it, e.g. "49ers"; alone: its last game')],
        opponent: Annotated[TeamName, Field(description="the other team, for their last game together")] = "",
        date: Annotated[DayText, Field(description="YYYY-MM-DD: the game closest to it")] = "",
    ) -> str:
        return await answered(lambda espn: box_score_answer(espn, League(league), team, opponent, date), settings.box_score_max_words)

    @server.tool(name=TEAM_ROSTER_TOOL_NAME, description=f"An NBA or NFL team's roster: number, name, position, injury status. {USE_BEFORE_SEARCH} {READ_AS_GIVEN}")
    async def roster(league: LeagueName, team: Annotated[TeamName, Field(description='as the user said it, e.g. "Niners"')]) -> str:
        return await answered(lambda espn: team_roster(espn, League(league), one_team(League(league), team)))

    @server.tool(name=PLAYER_STATS_TOOL_NAME, description=f"An NBA or NFL player's regular-season statistics by season, with career totals. {USE_BEFORE_SEARCH} {READ_AS_GIVEN}")
    async def stats(
        league: LeagueName,
        player: Annotated[PlayerName, Field(description='full name, e.g. "Stephen Curry"')],
        from_season: Annotated[int | None, Field(description=f"first season, {SEASON_FORMAT}; empty for whole career")] = None,
        to_season: Annotated[int | None, Field(description="last season, same format; empty for whole career")] = None,
    ) -> str:
        return await answered(lambda espn: stats_answer(espn, League(league), player, from_season, to_season))

    @server.tool(
        name=PLAYER_MATCHUP_TOOL_NAME,
        description=f"Every game an NBA or NFL player played against another player or a team: record, averages, and each game's score and stat lines. {USE_BEFORE_SEARCH} {READ_AS_GIVEN}",
    )
    async def matchup(
        league: LeagueName,
        player: Annotated[PlayerName, Field(description='full name, e.g. "Tom Brady"')],
        opponent_player: Annotated[PlayerName, Field(description="other player's full name; or opponent_team")] = "",
        opponent_team: Annotated[TeamName, Field(description='team faced, e.g. "Lakers"; or opponent_player')] = "",
    ) -> str:
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


async def box_score_answer(espn: EspnSession, league: League, team_name: str, opponent_name: str, day_text: str) -> str:
    team = one_team(league, team_name)
    opponent = one_team(league, opponent_name) if opponent_name.strip() else None
    if opponent == team:
        raise SportsRequestError(f"the team and the opponent are both the {team.display_name}; ask the user which other team they mean.")
    day = spoken_day(day_text, espn.today) if day_text.strip() else None
    return await game_box_score(espn, league, team, opponent, day)


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
