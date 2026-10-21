"""ESPN's JSON turned into the few fields the sports tools speak from: games, rosters, players, season rows and game logs.

ESPN does not document these answers, so every reader here takes only the fields it needs, and a missing one raises EspnShapeError, which the
client reports as ESPN not answering. Every name and note goes through sports_mcp.names on the way in.
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from sports_mcp.leagues import LEAGUE_TIMEZONE, League
from sports_mcp.names import cleaned_name, cleaned_note

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


class EspnShapeError(ValueError):
    """An ESPN answer lacked a field the tools read."""


class TeamLine(BaseModel):
    name: str
    abbreviation: str
    score: str = ""
    winner: bool = False
    leader: str = ""  # the NBA's top scorer, such as "LeBron James 27"


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
        status=cleaned_note(status.get("detail") or status.get("description", "")),
        note=cleaned_note(notes[0]) if notes else "",
        series=cleaned_note((competition.get("series") or {}).get("summary", "")),
        playoffs=season_type_of(event) == PLAYOFFS_SEASON_TYPE,
        home=read_team_line(sides["home"]),
        away=read_team_line(sides["away"]),
        leaders=[read_nfl_leader(leader) for leader in competition.get("leaders", []) if leader.get("name") in NFL_LEADER_STATS and leader.get("leaders")],
    )


def season_type_of(event: dict[str, Any]) -> int:
    """A scoreboard event names its season type under season, a schedule event under seasonType."""
    season_type = (event.get("seasonType") or {}).get("type") or (event.get("season") or {}).get("type")
    return int(season_type or 0)


def read_team_line(side: dict[str, Any]) -> TeamLine:
    team = side["team"]
    score = side.get("score") or ""  # a schedule gives no score for a game not yet played
    return TeamLine(
        name=cleaned_name(team.get("displayName") or f"{team.get('location', '')} {team.get('name', '')}"),
        abbreviation=cleaned_name(team.get("abbreviation", "")),
        score=str(score.get("displayValue", "") if isinstance(score, dict) else score),
        winner=bool(side.get("winner")),
        leader=read_nba_leader(side),
    )


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
