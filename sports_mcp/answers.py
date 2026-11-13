"""What each sports tool asks ESPN, once its arguments are checked and its team or player found (design doc v2/03 section 3.4).

A head-to-head is not something ESPN answers; it is worked out here from two game logs. ESPN lists the seasons a player played, the game logs of the
seasons both played are read, and a game counts when it is in both logs with each player on the other's opponent, so games as teammates do not.
"""

import asyncio
from datetime import date

from sports_mcp.espn_client import EspnSession
from sports_mcp.espn_records import FINISHED, NOT_PLAYED, BoxScore, FoundPlayer, Game, LoggedGame, RosterPlayer
from sports_mcp.game_finder import closest_game, game_near_day, last_meeting, plays_in, whole_season
from sports_mcp.leagues import League
from sports_mcp.render import (
    box_score_text,
    day_heading,
    games_text,
    has_stat_table,
    matchup_text,
    player_stats_text,
    roster_text,
    season_games_text,
    team_games_text,
    team_stats_text,
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


async def season_scores(session: EspnSession, league: League, team: Team, start_year: int, playoffs: bool) -> str:
    return season_games_text(league, team, start_year, playoffs, await session.schedule(league, team, start_year, playoffs))


async def game_box_score(session: EspnSession, league: League, team: Team, opponent: Team | None, day: date | None) -> str:
    """With a day, the game closest to it; with only an opponent, the two teams' last meeting; with neither, the team's last game."""
    if day is not None:
        game = await closest_game(session, league, team, opponent, day)
    elif opponent is not None:
        game = await last_meeting(session, league, team, opponent)
    else:
        game = await game_near_day(session, league, team, session.today)
    if game is None:
        return no_game_text(league, team, opponent, day or session.today)
    box_score = None if game.state == NOT_PLAYED else await session.box_score(league, game)
    return box_score_text(league, game_as_summarized(game, box_score), box_score, day)


def game_as_summarized(game: Game, box_score: BoxScore | None) -> Game:
    """The game's own summary arrives with the box score, so its score and clock match the statistics. A team schedule is kept for minutes and
    gives no score for an NBA game in progress."""
    if box_score is None or box_score.progress is None:
        return game
    return game.updated_to(box_score.progress)


async def team_roster(session: EspnSession, league: League, team: Team) -> str:
    return roster_text(league, team, await session.roster(league, team))


async def team_stats(session: EspnSession, league: League, team: Team) -> str:
    """Each player's statistics page, read a few at a time; ESPN's league-wide statistics ignore a team filter and run to megabytes."""
    players = [player for player in (await session.roster(league, team)).players if player.espn_id and has_stat_table(league, player)]
    seasons = await asyncio.gather(*(session.player_seasons(league, as_found_player(player, team)) for player in players))
    return team_stats_text(league, team, league.current_season(session.today), list(zip(players, seasons, strict=True)))


def as_found_player(player: RosterPlayer, team: Team) -> FoundPlayer:
    return FoundPlayer(espn_id=player.espn_id, name=player.name, team=team.display_name)


async def player_stats(session: EspnSession, league: League, player: FoundPlayer, first_season: int | None, last_season: int | None) -> str:
    seasons = await session.player_seasons(league, player)
    played = sorted(league.start_year(espn_season) for espn_season in seasons.espn_seasons) or [league.current_season(session.today)]
    return player_stats_text(league, player, seasons, *season_range(played, first_season, last_season))


def season_range(played: list[int], first_season: int | None, last_season: int | None) -> tuple[int, int]:
    """An end not asked for is the career's end, but never past the end that was asked for: a player last seen in 2025-26 asked about from
    2026-27 gets 2026-27 to 2026-27, which says he has no statistics then, not a backwards 2026-27 to 2025-26."""
    last = last_season or max(played[-1], first_season or played[0])
    return first_season or min(played[0], last), last


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
