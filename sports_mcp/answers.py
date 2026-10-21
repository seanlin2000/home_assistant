"""What each sports tool asks ESPN, once its arguments are checked and its team or player found (design doc v2/03 section 3.4).

A head-to-head is not something ESPN answers; it is worked out here from two game logs. ESPN lists the seasons a player played, the game logs of the
seasons both played are read, and a game counts when it is in both logs with each player on the other's opponent, so games as teammates do not.
"""

import asyncio
from datetime import date

from sports_mcp.espn_client import EspnSession
from sports_mcp.espn_records import FoundPlayer, Game, LoggedGame
from sports_mcp.leagues import League
from sports_mcp.render import (
    FINISHED,
    NOT_PLAYED,
    day_heading,
    games_text,
    matchup_text,
    player_stats_text,
    roster_text,
    season_games_text,
    team_games_text,
)
from sports_mcp.teams import Team


async def day_scores(session: EspnSession, league: League, day: date, team: Team | None) -> str:
    games = [game for game in await session.scoreboard(league, day) if team is None or plays_in(team, game)]
    return games_text(day_heading(league, day, team), games, "No games that day." if team is None else "This team did not play that day.")


async def recent_team_scores(session: EspnSession, league: League, team: Team) -> str:
    """Today's game comes from the scoreboard, kept 30 seconds, so a live score is current; the last and next games come from the team's schedule."""
    today = session.today
    playing_today = next((game for game in await session.scoreboard(league, today) if plays_in(team, game)), None)
    season = league.current_season(today)
    games = await whole_season(session, league, team, season)
    finished = [game for game in games if game.state == FINISHED and game.day < today]
    if not finished:
        finished = [game for game in await whole_season(session, league, team, season - 1) if game.state == FINISHED]  # before the season's first game
    upcoming = [game for game in games if game.state == NOT_PLAYED and game.day > today]
    around_today = {
        "Today": playing_today,
        "Last game": max(finished, key=lambda game: game.day, default=None),
        "Next game": None if playing_today else min(upcoming, key=lambda game: game.day, default=None),
    }
    return team_games_text(league, team, today, around_today)


async def whole_season(session: EspnSession, league: League, team: Team, start_year: int) -> list[Game]:
    return await session.schedule(league, team, start_year, playoffs=False) + await session.schedule(league, team, start_year, playoffs=True)


async def season_scores(session: EspnSession, league: League, team: Team, start_year: int, playoffs: bool) -> str:
    return season_games_text(league, team, start_year, playoffs, await session.schedule(league, team, start_year, playoffs))


def plays_in(team: Team, game: Game) -> bool:
    return team.abbreviation in (game.home.abbreviation, game.away.abbreviation)


async def team_roster(session: EspnSession, league: League, team: Team) -> str:
    return roster_text(league, team, await session.roster(league, team))


async def player_stats(session: EspnSession, league: League, player: FoundPlayer, first_season: int | None, last_season: int | None) -> str:
    seasons = await session.player_seasons(league, player)
    played = sorted(league.start_year(espn_season) for espn_season in seasons.espn_seasons) or [league.current_season(session.today)]
    return player_stats_text(league, player, seasons, first_season or played[0], last_season or played[-1])


async def player_against_player(session: EspnSession, league: League, player: FoundPlayer, opponent: FoundPlayer) -> str:
    own_seasons, their_seasons = await asyncio.gather(session.player_seasons(league, player), session.player_seasons(league, opponent))
    shared = sorted(own_seasons.espn_seasons & their_seasons.espn_seasons)
    own_games, their_games = await asyncio.gather(session.game_logs(league, player, shared), session.game_logs(league, opponent, shared))
    return matchup_text(league, player, opponent.name, faced_each_other(own_games, their_games), opponent)


def faced_each_other(own_games: list[LoggedGame], their_games: list[LoggedGame]) -> list[tuple[LoggedGame, LoggedGame | None]]:
    theirs_by_event = {game.event_id: game for game in their_games}
    return [(own, theirs_by_event[own.event_id]) for own in own_games if own.event_id in theirs_by_event and own.opponent_id == theirs_by_event[own.event_id].team_id]


async def player_against_team(session: EspnSession, league: League, player: FoundPlayer, team: Team) -> str:
    seasons = sorted((await session.player_seasons(league, player)).espn_seasons)
    games = [game for game in await session.game_logs(league, player, seasons) if game.opponent_id == team.espn_id]
    return matchup_text(league, player, f"the {team.display_name}", [(game, None) for game in games], None)
