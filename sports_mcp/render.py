"""The sports tools' replies as the model reads them: a heading naming what was found, then one line per game, player or season, in "a | b" rows.

The heading comes first because the benchmark's wrong_entity gate reads it, and so the model can tell the user it found a different team or player
than the one asked for. Summaries come before lists, so the words cut to fit a tool result are the oldest games, never the record.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sports_mcp.espn_records import (
    FINISHED,
    NOT_PLAYED,
    BoxScore,
    BoxScoreSide,
    BoxScoreTable,
    FoundPlayer,
    Game,
    LoggedGame,
    PlayerSeasons,
    Roster,
    RosterPlayer,
    StatCategory,
    TeamLine,
    box_score_columns,
)
from sports_mcp.game_finder import MOST_SEASONS_AWAY
from sports_mcp.leagues import League
from sports_mcp.teams import Team
from utils.text_utils import clip_to_whole_lines, word_count

CUT_NOTE = "(The rest was cut to keep this short; a narrower question, such as fewer seasons, hears it.)"
THREES = "threePointFieldGoalsMade-threePointFieldGoalsAttempted"
PASSING_ATTEMPTS = "passingAttempts"


@dataclass(frozen=True)
class Column:
    category: str
    name: str
    label: str


@dataclass(frozen=True)
class StatGroup:
    """One NFL table: shown when the player's career yards in it reach a threshold, so a quarterback's two career catches do not get a table."""

    category: str
    yards: str
    columns: tuple[Column, ...]


@dataclass(frozen=True)
class GameStatLine:
    """One part of a player's line in a game, said only when the player did it. A passer's few carries are left out: they would crowd a
    head-to-head out of the word budget, and the season table still has them."""

    played_when: str
    template: str
    said_for_passers: bool = True


NBA_SEASON_COLUMNS = (
    Column("averages", "gamesPlayed", "games"),
    Column("averages", "avgPoints", "points per game"),
    Column("averages", "avgRebounds", "rebounds per game"),
    Column("averages", "avgAssists", "assists per game"),
    Column("totals", THREES, "3-pointers made-attempted (season total)"),
    Column("averages", "fieldGoalPct", "field goal %"),
)
NFL_STAT_GROUPS = (
    StatGroup(
        "passing",
        "passingYards",
        (
            Column("passing", "gamesPlayed", "games"),
            Column("passing", "completions", "completions"),
            Column("passing", "passingAttempts", "attempts"),
            Column("passing", "passingYards", "yards"),
            Column("passing", "passingTouchdowns", "touchdowns"),
            Column("passing", "interceptions", "interceptions"),
            Column("passing", "QBRating", "passer rating"),
        ),
    ),
    StatGroup(
        "rushing",
        "rushingYards",
        (
            Column("rushing", "gamesPlayed", "games"),
            Column("rushing", "rushingAttempts", "carries"),
            Column("rushing", "rushingYards", "yards"),
            Column("rushing", "rushingTouchdowns", "touchdowns"),
        ),
    ),
    StatGroup(
        "receiving",
        "receivingYards",
        (
            Column("receiving", "gamesPlayed", "games"),
            Column("receiving", "receptions", "catches"),
            Column("receiving", "receivingYards", "yards"),
            Column("receiving", "receivingTouchdowns", "touchdowns"),
        ),
    ),
)
MIN_CAREER_YARDS_FOR_A_SIDE_TABLE = 500
NBA_GAME_LINES = (GameStatLine("minutes", "{points} PTS, {totalRebounds} REB, {assists} AST, {" + THREES + "} 3PT"),)
NFL_GAME_LINES = (
    GameStatLine(PASSING_ATTEMPTS, "{completions}/{passingAttempts}, {passingYards} pass YDS, {passingTouchdowns} TD, {interceptions} INT"),
    GameStatLine("rushingAttempts", "{rushingAttempts} CAR, {rushingYards} rush YDS, {rushingTouchdowns} TD", said_for_passers=False),
    GameStatLine("receptions", "{receptions} REC, {receivingYards} rec YDS, {receivingTouchdowns} TD", said_for_passers=False),
)
NBA_AVERAGES = (("points", "points"), ("totalRebounds", "rebounds"), ("assists", "assists"), (THREES, "3-pointers made"))
NFL_AVERAGES = (
    ("passingYards", "passing yards"),
    ("passingTouchdowns", "passing touchdowns"),
    ("interceptions", "interceptions"),
    ("rushingYards", "rushing yards"),
    ("receivingYards", "receiving yards"),
)


class MissingStat(dict[str, str]):
    """A game's stats for str.format_map, with a stat ESPN left out said as a question mark rather than raising."""

    def __missing__(self, key: str) -> str:
        return "?"


def clipped(text: str, max_words: int) -> str:
    """The reply cut to the word budget, saying so, so the model never reads a cut list out as the whole of it."""
    if word_count(text) <= max_words:
        return text
    return f"{clip_to_whole_lines(text, max_words - word_count(CUT_NOTE))}\n{CUT_NOTE}"


def day_heading(league: League, day: date, team: Team | None) -> str:
    for_team = f" involving the {team.display_name}" if team else ""
    return f"{league.label} games on {day:%A, %B} {day.day}, {day.year}{for_team} (dates are US Eastern time)"


def games_text(heading: str, games: list[Game], empty_note: str) -> str:
    return "\n".join([heading, *(game_line(game) for game in games)] if games else [heading, empty_note])


def game_line(game: Game) -> str:
    parts = [game.status or game.state, scoreline(game)]
    notes = [note for note in (game.note, game.series) if note]
    if notes:
        parts.append(", ".join(notes))
    top_scorers = [f"{line.abbreviation} {line.leader}" for line in (game.away, game.home) if line.leader]
    if top_scorers:
        parts.append("Top scorers: " + "; ".join(top_scorers))
    if game.leaders:
        parts.append("Leaders: " + "; ".join(game.leaders))
    return " | ".join(parts)


def scoreline(game: Game) -> str:
    """Away team first, as ESPN and broadcasters say it; a game not yet played has no score (its scoreboard says 0-0)."""
    if game.state == NOT_PLAYED:
        return f"{game.away.name} at {game.home.name}"
    return f"{game.away.name} {game.away.score} at {game.home.name} {game.home.score}"


def dated_game_line(game: Game) -> str:
    return f"{game.day:%a %Y-%m-%d} | {game_line(game)}"


def team_games_text(league: League, team: Team, today: date, around_today: dict[str, Game | None]) -> str:
    """The game today if there is one, the last finished game, and the next game, each labelled."""
    heading = f"{league.label}: {team.display_name} games around {today:%A, %B} {today.day}, {today.year} (dates are US Eastern time)"
    lines = [f"{label}: {dated_game_line(game)}" for label, game in around_today.items() if game is not None]
    return "\n".join([heading, *lines] if lines else [heading, "ESPN lists no recent or upcoming games for this team."])


def season_games_text(league: League, team: Team, start_year: int, playoffs: bool, games: list[Game]) -> str:
    part = "playoffs" if playoffs else "regular season"
    heading = f"{league.label}: {team.display_name} {league.season_label(start_year)} {part}"
    if not games:
        return f"{heading}\nESPN lists no {part} games for this team that season."
    finished = [game for game in games if game.state == FINISHED]
    record = f"Record: {team_record(team, finished)} in {len(finished)} finished games. Games, newest first:"
    return "\n".join([heading, record, *(dated_game_line(game) for game in sorted(games, key=lambda game: game.day, reverse=True))])


def team_record(team: Team, games: list[Game]) -> str:
    sides = [game.home if game.home.abbreviation == team.abbreviation else game.away for game in games]
    wins = sum(side.winner for side in sides)
    ties = sum(1 for game in games if not game.home.winner and not game.away.winner)
    return win_loss(wins, len(games) - wins - ties, ties)


def win_loss(wins: int, losses: int, ties: int) -> str:
    return f"{wins}-{losses}" + (f"-{ties}" if ties else "")


def box_score_text(league: League, game: Game, box_score: BoxScore | None, asked_day: date | None) -> str:
    """Both teams' totals first, then each table with the away team's players before the home team's, so a cut drops the least-used players."""
    lines = [f"{league.label} box score: {dated_game_line(game)}"]
    if asked_day is not None and asked_day != game.day:
        days_away = abs((game.day - asked_day).days)
        lines.append(f"No game matched {asked_day:%Y-%m-%d} itself; this is the closest one, {days_away} day{'' if days_away == 1 else 's'} away.")
    if box_score is None:
        return "\n".join([*lines, "This game has not been played yet, so it has no box score."])
    lines.extend(f"{side.team} team totals: {', '.join(side.team_stats)}" for side in box_score.sides if side.team_stats)
    if not box_score.has_players:
        return "\n".join([*lines, "ESPN has no player statistics for this game, only the score."])
    for side, table in tables_in_order(league, box_score):
        lines.extend(box_score_table_lines(side, table))
    lines.extend(did_not_play_lines(game, box_score))
    return "\n".join(lines)


def did_not_play_lines(game: Game, box_score: BoxScore) -> list[str]:
    """Until a game is final ESPN marks every player yet to check in as not playing, for "coach's decision", so a live game lists no one."""
    if game.state != FINISHED:
        return []
    return [f"{side.abbreviation} did not play: {', '.join(side.did_not_play)}" for side in box_score.sides if side.did_not_play]


def tables_in_order(league: League, box_score: BoxScore) -> list[tuple[BoxScoreSide, BoxScoreTable]]:
    """Passing for both teams, then rushing for both, and so on; ESPN lists the away team first, and the stable sort keeps it so."""
    order = {columns.title: index for index, columns in enumerate(box_score_columns(league))}
    return sorted(((side, table) for side in box_score.sides for table in side.tables), key=lambda pair: order[pair[1].title])


def box_score_table_lines(side: BoxScoreSide, table: BoxScoreTable) -> list[str]:
    header = f"{side.abbreviation} {table.title.lower()}: " + " | ".join(["player", *table.labels])
    return [header, *(" | ".join([row.player, *row.stats]) for row in table.rows)]


def no_game_text(league: League, team: Team, opponent: Team | None, day: date) -> str:
    against = f" against the {opponent.display_name}" if opponent else ""
    return f"{league.label}: ESPN lists no game of the {team.display_name}{against} within {MOST_SEASONS_AWAY} seasons of {day:%Y-%m-%d}."


def roster_text(league: League, team: Team, roster: Roster) -> str:
    season = f", {roster.season} season" if roster.season else ""
    heading = f"{league.label}: {team.display_name} roster{season}, {len(roster.players)} players. Jersey number, name, position, and injury status if any:"
    groups: dict[str, list[RosterPlayer]] = {}
    for player in roster.players:
        groups.setdefault(player.group, []).append(player)
    lines = [heading]
    for group, players in groups.items():
        lines.extend(([f"{group}:"] if group else []) + [roster_line(player) for player in players])
    return "\n".join(lines)


def roster_line(player: RosterPlayer) -> str:
    parts = [f"#{player.jersey} {player.name}" if player.jersey else player.name, player.position, player.injury]
    return " | ".join(part for part in parts if part)


def player_heading(league: League, player: FoundPlayer) -> str:
    return f"{league.label}: {player.name}" + (f" ({player.team})" if player.team else "")


def player_stats_text(league: League, player: FoundPlayer, seasons: PlayerSeasons, first_season: int, last_season: int) -> str:
    """Regular-season rows only: ESPN's season statistics leave out the playoffs, which the heading says so the model does not add them."""
    heading = f"{player_heading(league, player)}, regular season statistics, {league.season_label(first_season)} to {league.season_label(last_season)}"
    tables = nba_tables(league, seasons, first_season, last_season) if league is League.NBA else nfl_tables(league, seasons, first_season, last_season)
    return "\n".join([heading, *tables]) if tables else f"{heading}\nESPN has no statistics for {player.name} in those seasons."


def nba_tables(league: League, seasons: PlayerSeasons, first_season: int, last_season: int) -> list[str]:
    return season_table(league, seasons, NBA_SEASON_COLUMNS, first_season, last_season)


def nfl_tables(league: League, seasons: PlayerSeasons, first_season: int, last_season: int) -> list[str]:
    groups = [group for group in NFL_STAT_GROUPS if seasons.category(group.category)]
    groups.sort(key=lambda group: career_yards(seasons, group), reverse=True)
    shown = [group for index, group in enumerate(groups) if index == 0 or career_yards(seasons, group) >= MIN_CAREER_YARDS_FOR_A_SIDE_TABLE]
    lines = []
    for group in shown:
        table = season_table(league, seasons, group.columns, first_season, last_season)
        lines.extend([f"{group.category.capitalize()}:", *table] if table else [])
    return lines


def career_yards(seasons: PlayerSeasons, group: StatGroup) -> float:
    category = seasons.category(group.category)
    if category is None or group.yards not in category.names or not category.career:
        return 0.0
    return stat_number(group.yards, category.career[category.names.index(group.yards)]) or 0.0


def season_table(league: League, seasons: PlayerSeasons, columns: tuple[Column, ...], first_season: int, last_season: int) -> list[str]:
    """One row per season in range, then the career row, under a line naming the columns."""
    present = [column for column in columns if (category := seasons.category(column.category)) and column.name in category.names]
    if not present:
        return []
    rows_by_category = {column.category: seasons.category(column.category) for column in present}
    first_category = rows_by_category[present[0].category]
    in_range = [row.espn_season for row in first_category.rows if first_season <= league.start_year(row.espn_season) <= last_season]
    if not in_range:
        return []
    header = " | ".join(["season", "team", *(column.label for column in present)])
    rows = [season_line(league, espn_season, present, rows_by_category) for espn_season in in_range]
    career = " | ".join(["Career (every season)", "", *(career_value(rows_by_category[column.category], column.name) for column in present)])
    return [header, *rows, career]


def season_line(league: League, espn_season: int, columns: list[Column], rows_by_category: dict[str, StatCategory]) -> str:
    rows = {name: next((row for row in category.rows if row.espn_season == espn_season), None) for name, category in rows_by_category.items()}
    team = next((row.team for row in rows.values() if row is not None and row.team), "")
    values = []
    for column in columns:
        row = rows[column.category]
        names = rows_by_category[column.category].names
        values.append(row.stats[names.index(column.name)] if row is not None and names.index(column.name) < len(row.stats) else "")
    return " | ".join([league.season_label(league.start_year(espn_season)), team, *values])


def career_value(category: StatCategory, name: str) -> str:
    index = category.names.index(name)
    return category.career[index] if index < len(category.career) else ""


def matchup_text(league: League, player: FoundPlayer, opponent_label: str, pairs: list[tuple[LoggedGame, LoggedGame | None]], opponent: FoundPlayer | None) -> str:
    """The record from the first player's side, split into regular season and playoffs, averages per game, then every game newest first."""
    heading = f"{player_heading(league, player)} against {opponent_label}, regular season and playoffs"
    if not pairs:
        return f"{heading}\nESPN's game logs have no game in which {player.name} played against {opponent_label}."
    games = [own for own, _ in pairs]
    lines = [heading, matchup_record(player, games), per_game_line(league, player.name, games)]
    if opponent is not None:
        lines.append(per_game_line(league, opponent.name, [theirs for _, theirs in pairs if theirs is not None]))
    lines.append("Games, newest first:")
    lines.extend(matchup_line(league, player, own, theirs, opponent) for own, theirs in sorted(pairs, key=lambda pair: pair[0].day, reverse=True))
    return "\n".join(lines)


def matchup_record(player: FoundPlayer, games: list[LoggedGame]) -> str:
    regular = [game for game in games if not game.playoffs]
    playoffs = [game for game in games if game.playoffs]
    return f"Record of {player.name}'s team: {logged_record(games)} in {len(games)} games (regular season {logged_record(regular)}, playoffs {logged_record(playoffs)})."


def logged_record(games: list[LoggedGame]) -> str:
    return win_loss(sum(game.result == "W" for game in games), sum(game.result == "L" for game in games), sum(game.result == "T" for game in games))


def per_game_line(league: League, name: str, games: list[LoggedGame]) -> str:
    stats = NBA_AVERAGES if league is League.NBA else NFL_AVERAGES
    averages = [f"{average:.1f} {label}" for key, label in stats if (average := per_game(games, key))]
    return f"Per game, {name}: " + (", ".join(averages) if averages else "no statistics recorded") + "."


def per_game(games: list[LoggedGame], key: str) -> float | None:
    numbers = [number for game in games if key in game.stats and (number := stat_number(key, game.stats[key])) is not None]
    return sum(numbers) / len(numbers) if numbers and any(numbers) else None


def stat_number(name: str, value: str) -> float | None:
    """A stat as a number: "1,123" is 1123, and a made-attempted pair such as "5-11" is its made part; a negative "-3" rushing yards stays -3."""
    text = value.replace(",", "")
    if "-" in name:
        text = text.split("-")[0]
    try:
        return float(text)
    except ValueError:
        return None


def matchup_line(league: League, player: FoundPlayer, own: LoggedGame, theirs: LoggedGame | None, opponent: FoundPlayer | None) -> str:
    where = "vs" if own.home else "at"
    kind = ", ".join(part for part in ("Playoffs" if own.playoffs else "", own.note) if part)
    parts = [f"{own.day:%Y-%m-%d}" + (f" {kind}" if kind else ""), f"{own.team} {own.team_score}-{own.opponent_score} {where} {own.opponent}, {own.result}"]
    parts.append(f"{player.name}: {game_stats(league, own)}")
    if theirs is not None and opponent is not None:
        parts.append(f"{opponent.name}: {game_stats(league, theirs)}")
    return " | ".join(parts)


def game_stats(league: League, game: LoggedGame) -> str:
    lines = NBA_GAME_LINES if league is League.NBA else NFL_GAME_LINES
    stats = MissingStat(game.stats)
    said = [line.template.format_map(stats) for line in played(lines, game)]
    return "; ".join(said) if said else "did not record a statistic"


def played(lines: Iterable[GameStatLine], game: LoggedGame) -> list[GameStatLine]:
    passed = did(game, PASSING_ATTEMPTS)
    return [line for line in lines if did(game, line.played_when) and (line.said_for_passers or not passed)]


def did(game: LoggedGame, stat: str) -> bool:
    return stat_number(stat, game.stats.get(stat, "")) not in (None, 0.0)
