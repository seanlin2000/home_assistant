"""ESPN's JSON turned into the few fields the sports tools speak from: games, rosters, players, season rows and game logs.

ESPN does not document these answers, so every reader here takes only the fields it needs, and a missing one raises EspnShapeError, which the
client reports as ESPN not answering. Every name and note goes through sports_mcp.names on the way in.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from sports_mcp.leagues import LEAGUE_TIMEZONE, League
from sports_mcp.names import cleaned_name, cleaned_note, cleaned_stat

PLAYOFFS_SEASON_TYPE = 3
NBA_LEADER_STAT = "points"
NFL_LEADER_STATS = ("passingYards", "rushingYards", "receivingYards")
NFL_ROSTER_GROUPS = {
    "offense": "Offense",
    "defense": "Defense",
    "specialTeam": "Special teams",
    "injuredReserveOrOut": "Injured reserve or out",
    "suspended": "Suspended",
}  # the practice squad is left out: its players are not on the active roster
SKIPPED_SEASON_TYPES = ("Preseason", "All-Star")
PLAYOFF_SEASON_TYPE_NAME = "Postseason"
EVENT_CATEGORY = "event"
NOT_PLAYED = "pre"  # a game's state, as ESPN names it
FINISHED = "post"
FINAL_ONLY_STAT_KEYS = frozenset({"adjQBR"})  # listed among a live NFL game's passing keys, though its label and values only arrive once the game is final


class EspnShapeError(ValueError):
    """An ESPN answer lacked a field the tools read."""


class TeamLine(BaseModel):
    name: str
    abbreviation: str
    espn_id: str = ""
    score: str = ""
    winner: bool = False
    leader: str = ""  # the NBA's top scorer, such as "LeBron James 27"


class GameProgress(BaseModel):
    """Where a game stands by its summary, which ESPN updates along with the box score."""

    state: str
    status: str
    away_score: str
    home_score: str


class Game(BaseModel):
    event_id: str
    day: date
    state: str  # "pre", "in", or "post"
    status: str  # "Final", "1:52 - 4th Quarter", "Tue, October 20th at 9:50 PM EDT"
    note: str = ""
    series: str = ""
    playoffs: bool = False
    home: TeamLine
    away: TeamLine
    leaders: list[str] = []  # the NFL's passing, rushing and receiving leaders, such as "Jayden Daniels 29/40, 300 YDS, 2 TD"

    def updated_to(self, progress: GameProgress) -> "Game":
        return self.model_copy(
            update={
                "state": progress.state,
                "status": progress.status or self.status,
                "away": self.away.model_copy(update={"score": progress.away_score or self.away.score}),
                "home": self.home.model_copy(update={"score": progress.home_score or self.home.score}),
            }
        )


class RosterPlayer(BaseModel):
    name: str
    jersey: str = ""
    position: str = ""
    group: str = ""
    injury: str = ""


class Roster(BaseModel):
    season: str
    players: list[RosterPlayer]


class FoundPlayer(BaseModel):
    espn_id: str
    name: str
    team: str = ""


class SeasonRow(BaseModel):
    espn_season: int
    team: str
    stats: list[str]


class StatCategory(BaseModel):
    name: str
    labels: list[str]
    names: list[str]
    rows: list[SeasonRow]
    career: list[str] = []


class PlayerSeasons(BaseModel):
    categories: list[StatCategory]

    @property
    def espn_seasons(self) -> set[int]:
        return {row.espn_season for category in self.categories for row in category.rows}

    def category(self, name: str) -> StatCategory | None:
        return next((category for category in self.categories if category.name == name), None)


class LoggedGame(BaseModel):
    event_id: str
    day: date
    playoffs: bool
    note: str = ""
    team_id: str
    team: str
    opponent_id: str
    opponent: str
    home: bool
    result: str  # "W", "L", or "T"
    team_score: str
    opponent_score: str
    stats: dict[str, str]


class BoxScoreRow(BaseModel):
    player: str
    stats: list[str]


class BoxScoreTable(BaseModel):
    title: str  # "Passing", or "Players" for the NBA's one table
    labels: list[str]
    rows: list[BoxScoreRow]


class BoxScoreSide(BaseModel):
    team: str
    abbreviation: str
    tables: list[BoxScoreTable]
    did_not_play: list[str] = []  # "Draymond Green (lower back injury management)"
    team_stats: list[str] = []  # "375 total yards"


class BoxScore(BaseModel):
    sides: list[BoxScoreSide]  # away team first, as ESPN lists them
    progress: GameProgress | None = None  # None when the summary has no header, and in a box score cached before the header was read

    @property
    def has_players(self) -> bool:
        return any(table.rows for side in self.sides for table in side.tables)


@dataclass(frozen=True)
class BoxScoreColumns:
    """One table of a box score: the ESPN group, the stats kept from it and what each is called, and how many players are kept."""

    group: str | None  # ESPN's group name; None for the NBA's single, unnamed group
    title: str
    stats: tuple[tuple[str, str], ...]  # (ESPN key, label)
    most_players: int = 20


NBA_BOX_SCORE = (
    BoxScoreColumns(
        None,
        "Players",
        (
            ("minutes", "MIN"),
            ("points", "PTS"),
            ("fieldGoalsMade-fieldGoalsAttempted", "FG"),
            ("threePointFieldGoalsMade-threePointFieldGoalsAttempted", "3PT"),
            ("freeThrowsMade-freeThrowsAttempted", "FT"),
            ("rebounds", "REB"),
            ("assists", "AST"),
            ("steals", "STL"),
            ("blocks", "BLK"),
            ("turnovers", "TO"),
            ("plusMinus", "+/-"),
        ),
    ),
)
NFL_BOX_SCORE = (
    BoxScoreColumns(
        "passing",
        "Passing",
        (("completions/passingAttempts", "C/ATT"), ("passingYards", "YDS"), ("passingTouchdowns", "TD"), ("interceptions", "INT"), ("sacks-sackYardsLost", "SACKS"), ("QBRating", "RTG")),
    ),
    BoxScoreColumns("rushing", "Rushing", (("rushingAttempts", "CAR"), ("rushingYards", "YDS"), ("rushingTouchdowns", "TD"), ("longRushing", "LONG"))),
    BoxScoreColumns("receiving", "Receiving", (("receptions", "REC"), ("receivingTargets", "TGTS"), ("receivingYards", "YDS"), ("receivingTouchdowns", "TD"), ("longReception", "LONG"))),
    BoxScoreColumns("defensive", "Defense", (("totalTackles", "TOT"), ("sacks", "SACKS"), ("tacklesForLoss", "TFL"), ("passesDefended", "PD")), most_players=6),  # of about 18
    BoxScoreColumns("interceptions", "Interceptions", (("interceptions", "INT"), ("interceptionYards", "YDS"), ("interceptionTouchdowns", "TD"))),
    BoxScoreColumns("kicking", "Kicking", (("fieldGoalsMade/fieldGoalAttempts", "FG"), ("longFieldGoalMade", "LONG"), ("extraPointsMade/extraPointAttempts", "XP"), ("totalKickingPoints", "PTS"))),
)
NBA_TEAM_STATS = (("fieldGoalPct", "field goal %"), ("threePointFieldGoalPct", "3-point %"), ("totalRebounds", "rebounds"), ("assists", "assists"), ("totalTurnovers", "turnovers"))
NFL_TEAM_STATS = (
    ("totalYards", "total yards"),
    ("netPassingYards", "passing yards"),
    ("rushingYards", "rushing yards"),
    ("turnovers", "turnovers"),
    ("thirdDownEff", "third downs"),
    ("totalPenaltiesYards", "penalties-yards"),
    ("possessionTime", "possession"),
)


def read_games(body: dict[str, Any]) -> list[Game]:
    """The games of a scoreboard or a team schedule."""
    try:
        return [read_game(event) for event in body.get("events", [])]
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise EspnShapeError(f"games: {type(error).__name__} {error}") from error


def read_game(event: dict[str, Any]) -> Game:
    competition = event["competitions"][0]
    status = competition["status"]["type"]
    sides = {side["homeAway"]: side for side in competition["competitors"]}
    notes = [note.get("headline", "") for note in competition.get("notes", []) if note.get("headline")]
    return Game(
        event_id=str(event["id"]),
        day=eastern_day(event["date"]),
        state=status["state"],
        status=status_text(status),
        note=cleaned_note(notes[0]) if notes else "",
        series=cleaned_note((competition.get("series") or {}).get("summary", "")),
        playoffs=season_type_of(event) == PLAYOFFS_SEASON_TYPE,
        home=read_team_line(sides["home"]),
        away=read_team_line(sides["away"]),
        leaders=[read_nfl_leader(leader) for leader in competition.get("leaders", []) if leader.get("name") in NFL_LEADER_STATS and leader.get("leaders")],
    )


def status_text(status_type: dict[str, Any]) -> str:
    """The game's state as ESPN words it: "Final", "1:52 - 4th Quarter", or a coming game's start time."""
    return cleaned_note(status_type.get("detail") or status_type.get("description", ""))


def season_type_of(event: dict[str, Any]) -> int:
    """A scoreboard event names its season type under season, a schedule event under seasonType."""
    season_type = (event.get("seasonType") or {}).get("type") or (event.get("season") or {}).get("type")
    return int(season_type or 0)


def read_team_line(side: dict[str, Any]) -> TeamLine:
    team = side["team"]
    return TeamLine(
        name=cleaned_name(team.get("displayName") or f"{team.get('location', '')} {team.get('name', '')}"),
        abbreviation=cleaned_name(team.get("abbreviation", "")),
        espn_id=str(team.get("id", "")),
        score=read_score(side),
        winner=bool(side.get("winner")),
        leader=read_nba_leader(side),
    )


def read_score(side: dict[str, Any]) -> str:
    """A scoreboard and a summary give the score as text, a schedule as a mapping; a schedule gives none for a game not yet played or an NBA game in progress."""
    score = side.get("score") or ""
    return str(score.get("displayValue", "") if isinstance(score, dict) else score)


def read_nba_leader(side: dict[str, Any]) -> str:
    for category in side.get("leaders", []):
        if category.get("name") == NBA_LEADER_STAT and category.get("leaders"):
            top = category["leaders"][0]
            return f"{cleaned_name(top['athlete']['displayName'])} {cleaned_note(top['displayValue'])}"
    return ""


def read_nfl_leader(category: dict[str, Any]) -> str:
    top = category["leaders"][0]
    return f"{cleaned_name(top['athlete']['displayName'])} {cleaned_note(top['displayValue'])}"


def eastern_day(timestamp: str) -> date:
    """ESPN stamps games in UTC; a 7:30 PM Pacific tip-off is the next day in UTC but the same day on ESPN's scoreboard, which runs on Eastern time."""
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(LEAGUE_TIMEZONE).date()


def read_roster(body: dict[str, Any]) -> Roster:
    try:
        athletes = body["athletes"]
        grouped = bool(athletes) and "items" in athletes[0]
        players = (
            [read_roster_player(athlete, NFL_ROSTER_GROUPS[group["position"]]) for group in athletes if group.get("position") in NFL_ROSTER_GROUPS for athlete in group["items"]]
            if grouped
            else [read_roster_player(athlete, "") for athlete in athletes]
        )
        return Roster(season=cleaned_note(body.get("season", {}).get("displayName", "")), players=players)
    except (KeyError, IndexError, TypeError) as error:
        raise EspnShapeError(f"roster: {type(error).__name__} {error}") from error


def read_roster_player(athlete: dict[str, Any], group: str) -> RosterPlayer:
    injuries = athlete.get("injuries") or []
    return RosterPlayer(
        name=cleaned_name(athlete["displayName"]),
        jersey=cleaned_name(athlete.get("jersey", "")),
        position=cleaned_name((athlete.get("position") or {}).get("abbreviation", "")),
        group=group,
        injury=cleaned_note(injuries[0].get("status", "")) if injuries else "",
    )


def read_found_player(body: dict[str, Any], league: League) -> FoundPlayer | None:
    """The first player in the asked league; ESPN's search ranks the best-known first and mixes in every sport."""
    marker = f"~l:{league.espn_code}~a:"
    try:
        for group in body.get("results", []):
            for item in group.get("contents", []):
                uid = item.get("uid", "")
                if item.get("type") == "player" and marker in uid:
                    return FoundPlayer(espn_id=uid.split(marker, 1)[1], name=cleaned_name(item["displayName"]), team=cleaned_name(item.get("subtitle", "")))
        return None
    except (KeyError, TypeError) as error:
        raise EspnShapeError(f"search: {type(error).__name__} {error}") from error


def read_player_seasons(body: dict[str, Any]) -> PlayerSeasons:
    try:
        abbreviations = {str(team["id"]): cleaned_name(team.get("abbreviation", "")) for team in (body.get("teams") or {}).values()}
        return PlayerSeasons(categories=[read_stat_category(category, abbreviations) for category in body.get("categories", [])])
    except (KeyError, TypeError, ValueError) as error:
        raise EspnShapeError(f"stats: {type(error).__name__} {error}") from error


def read_stat_category(category: dict[str, Any], abbreviations: dict[str, str]) -> StatCategory:
    rows_by_season: dict[int, list[dict[str, Any]]] = {}
    for row in category.get("statistics", []):
        rows_by_season.setdefault(int(row["season"]["year"]), []).append(row)
    return StatCategory(
        name=category["name"],
        labels=category.get("labels", []),
        names=category.get("names", []),
        rows=[season_row(season, rows, abbreviations) for season, rows in sorted(rows_by_season.items())],
        career=category.get("totals", []),
    )


def season_row(espn_season: int, rows: list[dict[str, Any]], abbreviations: dict[str, str]) -> SeasonRow:
    """A traded player has one row per team and a totals row without a team; the totals row is kept, named after every team he played for."""
    teams = [abbreviations.get(str(row.get("teamId")), "") for row in rows if row.get("teamId")]
    totals = next((row for row in rows if not row.get("teamId")), None)
    chosen = totals if totals and len(rows) > 1 else rows[0]
    return SeasonRow(espn_season=espn_season, team="/".join(team for team in teams if team), stats=[str(value) for value in chosen["stats"]])


def read_game_log(body: dict[str, Any]) -> list[LoggedGame]:
    """Regular-season and playoff games of one season; preseason and All-Star games are left out."""
    try:
        names = body["names"]
        games = []
        for season_type in body.get("seasonTypes", []):
            type_name = season_type.get("displayName", "")
            if any(skipped in type_name for skipped in SKIPPED_SEASON_TYPES):
                continue
            for category in season_type.get("categories", []):
                if category.get("type") == EVENT_CATEGORY:
                    games.extend(read_logged_game(body["events"][entry["eventId"]], dict(zip(names, entry["stats"])), PLAYOFF_SEASON_TYPE_NAME in type_name) for entry in category.get("events", []))
        return games
    except (KeyError, TypeError, ValueError) as error:
        raise EspnShapeError(f"game log: {type(error).__name__} {error}") from error


def read_logged_game(event: dict[str, Any], stats: dict[str, str], playoffs: bool) -> LoggedGame:
    team_id = str(event["team"]["id"])
    home = str(event.get("homeTeamId")) == team_id
    team_score, opponent_score = (event.get("homeTeamScore", ""), event.get("awayTeamScore", "")) if home else (event.get("awayTeamScore", ""), event.get("homeTeamScore", ""))
    return LoggedGame(
        event_id=str(event["id"]),
        day=eastern_day(event["gameDate"]),
        playoffs=playoffs,
        note=cleaned_note(event.get("eventNote", "")),
        team_id=team_id,
        team=cleaned_name(event["team"].get("abbreviation", "")),
        opponent_id=str(event["opponent"]["id"]),
        opponent=cleaned_name(event["opponent"].get("abbreviation", "")),
        home=home,
        result=event.get("gameResult", ""),
        team_score=str(team_score),
        opponent_score=str(opponent_score),
        stats=stats,
    )


def read_box_score(body: dict[str, Any], league: League) -> BoxScore:
    """Both teams' players and team totals from a game's summary. ESPN has no players for older games (NBA games of 1985 have none, of 1996 do); their tables are then empty."""
    try:
        box_score = body["boxscore"]
        totals_by_team = {str(side["team"]["id"]): side.get("statistics", []) for side in box_score.get("teams", [])}
        sides = [read_box_score_side(side, totals_by_team.get(str(side["team"]["id"]), []), league) for side in box_score.get("players", [])]
        return BoxScore(sides=sides, progress=read_game_progress(body))
    except (KeyError, IndexError, TypeError) as error:
        raise EspnShapeError(f"box score: {type(error).__name__} {error}") from error


def read_game_progress(body: dict[str, Any]) -> GameProgress | None:
    competitions = (body.get("header") or {}).get("competitions") or []
    if not competitions:
        return None
    status = competitions[0]["status"]["type"]
    sides = {side["homeAway"]: side for side in competitions[0]["competitors"]}
    return GameProgress(
        state=status["state"],
        status=status_text(status),
        away_score=read_score(sides["away"]),
        home_score=read_score(sides["home"]),
    )


def read_box_score_side(side: dict[str, Any], team_totals: list[dict[str, Any]], league: League) -> BoxScoreSide:
    groups = side.get("statistics", [])
    tables = [table for wanted in box_score_columns(league) if (group := box_score_group(groups, wanted)) is not None and (table := read_box_score_table(group, wanted)).rows]
    return BoxScoreSide(
        team=cleaned_name(side["team"].get("displayName", "")),
        abbreviation=cleaned_name(side["team"].get("abbreviation", "")),
        tables=tables,
        did_not_play=[did_not_play(athlete) for group in groups[:1] for athlete in group.get("athletes", []) if athlete.get("didNotPlay")],
        team_stats=read_team_stats(team_totals, NBA_TEAM_STATS if league is League.NBA else NFL_TEAM_STATS),
    )


def box_score_columns(league: League) -> tuple[BoxScoreColumns, ...]:
    return NBA_BOX_SCORE if league is League.NBA else NFL_BOX_SCORE


def box_score_group(groups: list[dict[str, Any]], wanted: BoxScoreColumns) -> dict[str, Any] | None:
    if wanted.group is None:
        return groups[0] if groups else None
    return next((group for group in groups if group.get("name") == wanted.group), None)


def read_box_score_table(group: dict[str, Any], wanted: BoxScoreColumns) -> BoxScoreTable:
    """The kept stats of every player who played, in ESPN's order (starters first, the most-used first), up to the table's limit."""
    keys = keys_of_values(group)
    present = [(key, label) for key, label in wanted.stats if key in keys]
    rows = [
        BoxScoreRow(player=cleaned_name(athlete["athlete"]["displayName"]), stats=[cleaned_stat(athlete["stats"][keys.index(key)]) for key, _ in present])
        for athlete in group.get("athletes", [])
        if athlete.get("stats") and not athlete.get("didNotPlay")
    ]
    return BoxScoreTable(title=wanted.title, labels=[label for _, label in present], rows=rows[: wanted.most_players])


def keys_of_values(group: dict[str, Any]) -> list[str]:
    """The keys of a player row's values, one per value. A group's labels always match its rows; its keys can list a stat before it has values."""
    keys = group.get("keys", [])
    if len(keys) > len(group.get("labels", keys)):
        return [key for key in keys if key not in FINAL_ONLY_STAT_KEYS]
    return keys


def did_not_play(athlete: dict[str, Any]) -> str:
    reason = cleaned_note(athlete.get("reason", "")).lower()
    return cleaned_name(athlete["athlete"]["displayName"]) + (f" ({reason})" if reason else "")


def read_team_stats(team_totals: list[dict[str, Any]], wanted: tuple[tuple[str, str], ...]) -> list[str]:
    values = {total.get("name"): cleaned_stat(total.get("displayValue", "")) for total in team_totals}
    return [f"{values[key]} {label}" for key, label in wanted if values.get(key)]
