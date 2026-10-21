"""Which game a box score is asked about: a team's game, or its game against one opponent, closest to a day (design doc v2/03 section 3.4).

One search answers all three ways of asking. "The Warriors game on the 12th" is the team's game closest to that day, "the last Niners-Seahawks
game" is the two teams' meeting closest to today, and "the Niners-Seahawks game in 2019" is their meeting closest to a day in 2019. A game not yet
played counts only when the day asked is after today, so "the last game" is never tonight's game before it starts.

ESPN lists games by team and season, so the search reads whole seasons, outward from the day's season. Once a season holds a game it reads one
more season each way, because a meeting early in the next season can be closer than one late in this one. Two teams of different NFL conferences
meet about once in four seasons, so it gives up after MOST_SEASONS_AWAY.
"""

import asyncio
from datetime import date

from sports_mcp.espn_client import EspnSession
from sports_mcp.espn_records import NOT_PLAYED, Game
from sports_mcp.leagues import FIRST_SEASON, League
from sports_mcp.teams import Team

MOST_SEASONS_AWAY = 10


async def game_near_day(session: EspnSession, league: League, team: Team, day: date) -> Game | None:
    return await closest_game(session, league, team, None, day)


async def last_meeting(session: EspnSession, league: League, team: Team, opponent: Team) -> Game | None:
    return await closest_game(session, league, team, opponent, session.today)


async def closest_game(session: EspnSession, league: League, team: Team, opponent: Team | None, day: date) -> Game | None:
    """The team's game nearest the day, against the opponent if one is given; between two equally near games, the earlier."""
    rings = seasons_outward(league, league.current_season(day), session.today)
    for index, ring in enumerate(rings):
        found = [game for game in await games_of_seasons(session, league, team, ring) if counts(game, opponent, day, session.today)]
        if found:
            next_ring = rings[index + 1] if index + 1 < len(rings) else []
            found += [game for game in await games_of_seasons(session, league, team, next_ring) if counts(game, opponent, day, session.today)]
            return min(found, key=lambda game: (abs((game.day - day).days), game.day))
    return None


def seasons_outward(league: League, center: int, today: date) -> list[list[int]]:
    """The day's season, then the seasons one away on each side, then two away, and so on, from the first season ESPN has to the current one."""
    newest = league.current_season(today)
    rings = [[season for season in (center - away, center + away) if FIRST_SEASON <= season <= newest] for away in range(MOST_SEASONS_AWAY + 1)]
    return [sorted(set(ring)) for ring in rings if ring]


async def games_of_seasons(session: EspnSession, league: League, team: Team, start_years: list[int]) -> list[Game]:
    seasons = await asyncio.gather(*(whole_season(session, league, team, start_year) for start_year in start_years))
    return [game for season in seasons for game in season]


async def whole_season(session: EspnSession, league: League, team: Team, start_year: int) -> list[Game]:
    """The regular season and the playoffs; ESPN lists them apart."""
    return await session.schedule(league, team, start_year, playoffs=False) + await session.schedule(league, team, start_year, playoffs=True)


def counts(game: Game, opponent: Team | None, day: date, today: date) -> bool:
    against_opponent = opponent is None or plays_in(opponent, game)
    return against_opponent and (game.state != NOT_PLAYED or day > today)


def plays_in(team: Team, game: Game) -> bool:
    """ESPN's id stays with a team that moves and its abbreviation does not (OAK became LV); games kept before ids were read have only the abbreviation."""
    return team.espn_id in (game.home.espn_id, game.away.espn_id) or team.abbreviation in (game.home.abbreviation, game.away.abbreviation)
