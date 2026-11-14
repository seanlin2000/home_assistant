"""The statistics player_rankings and team_rankings order by, and where each lives in ESPN's league-wide lists.

The tools' arguments name a statistic in plain words ("passing_interceptions"); this table turns it into ESPN's category and sort key, so the model
never needs ESPN's names. A statistic is added here and nowhere else.
"""

from dataclasses import dataclass
from typing import Literal

from sports_mcp.espn_records import RankedPlayer
from sports_mcp.leagues import League

PlayerStat = Literal[
    "points_per_game",
    "rebounds_per_game",
    "assists_per_game",
    "steals_per_game",
    "blocks_per_game",
    "threes_made",
    "field_goal_pct",
    "three_point_pct",
    "free_throw_pct",
    "turnovers_per_game",
    "passing_yards",
    "passing_touchdowns",
    "passing_interceptions",
    "passer_rating",
    "completion_pct",
    "rushing_yards",
    "rushing_touchdowns",
    "receiving_yards",
    "receptions",
    "receiving_touchdowns",
    "total_tackles",
    "sacks_made",
    "defensive_interceptions",
]
TeamStat = Literal[
    "points_per_game",
    "points_allowed_per_game",
    "point_differential",
    "rebounds_per_game",
    "assists_per_game",
    "field_goal_pct",
    "three_point_pct",
    "turnovers_per_game",
    "total_yards_per_game",
    "yards_allowed_per_game",
    "passing_yards_per_game",
    "rushing_yards_per_game",
    "passing_yards_allowed_per_game",
    "rushing_yards_allowed_per_game",
    "interceptions_thrown",
    "takeaways",
    "turnover_differential",
    "third_down_pct",
]
Position = Literal[
    "",
    "guard",
    "forward",
    "center",
    "quarterback",
    "running_back",
    "wide_receiver",
    "tight_end",
    "linebacker",
    "defensive_end",
    "defensive_tackle",
    "cornerback",
    "safety",
]
POSITION_CODES = {
    League.NBA: {"guard": "G", "forward": "F", "center": "C"},
    League.NFL: {
        "quarterback": "QB",
        "running_back": "RB",
        "wide_receiver": "WR",
        "tight_end": "TE",
        "linebacker": "LB",
        "defensive_end": "DE",
        "defensive_tackle": "DT",
        "cornerback": "CB",
        "safety": "S",
    },
}
OWN = "own"
OPPONENT = "opponent"  # ESPN's "Opponent" split: what a team allowed


@dataclass(frozen=True)
class StatField:
    """One figure in a parsed ESPN row, keyed "category.name" as ESPN groups it; `side` picks a team's own or its opponents' figures."""

    category: str
    name: str
    label: str
    side: str = OWN

    @property
    def key(self) -> str:
        return f"{self.category}.{self.name}"


@dataclass(frozen=True)
class PlayerRankedStat:
    """A player statistic: the ESPN list it is read from, its sort key, who is on that list, and the columns shown beside it."""

    league: League
    espn_category: str  # "" for the NBA, whose list holds every statistic
    ranked: StatField
    pool: str  # who ESPN's qualified list holds, as the heading says it
    context: tuple[StatField, ...]
    sort_group: str = ""  # ESPN's sort spells a few groups differently from its rows, such as defensiveInterceptions

    def sort(self, ascending: bool) -> str:
        return f"{self.sort_group or self.ranked.category}.{self.ranked.name}:{'asc' if ascending else 'desc'}"


@dataclass(frozen=True)
class TeamRankedStat:
    league: League
    ranked: StatField
    context: tuple[StatField, ...]


NBA_GAMES = StatField("general", "gamesPlayed", "games")
NBA_PLAYER_CONTEXT = (
    NBA_GAMES,
    StatField("offensive", "avgPoints", "points"),
    StatField("general", "avgRebounds", "rebounds"),
    StatField("offensive", "avgAssists", "assists"),
)
NFL_GAMES = StatField("general", "gamesPlayed", "games")
PASSING_CONTEXT = (
    NFL_GAMES,
    StatField("passing", "passingAttempts", "attempts"),
    StatField("passing", "passingYards", "yards"),
    StatField("passing", "passingTouchdowns", "touchdowns"),
    StatField("passing", "interceptions", "interceptions"),
    StatField("passing", "QBRating", "rating"),
)
RUSHING_CONTEXT = (
    NFL_GAMES,
    StatField("rushing", "rushingAttempts", "carries"),
    StatField("rushing", "rushingYards", "yards"),
    StatField("rushing", "rushingTouchdowns", "touchdowns"),
)
RECEIVING_CONTEXT = (
    NFL_GAMES,
    StatField("receiving", "receptions", "catches"),
    StatField("receiving", "receivingYards", "yards"),
    StatField("receiving", "receivingTouchdowns", "touchdowns"),
)
DEFENSIVE_CONTEXT = (
    NFL_GAMES,
    StatField("defensive", "totalTackles", "tackles"),
    StatField("defensive", "sacks", "sacks"),
    StatField("defensiveinterceptions", "interceptions", "interceptions"),
)


def nba_player_stat(category: str, name: str, label: str) -> PlayerRankedStat:
    return PlayerRankedStat(League.NBA, "", StatField(category, name, label), "players", NBA_PLAYER_CONTEXT)


def nfl_player_stat(espn_category: str, category: str, name: str, label: str, pool: str, context: tuple[StatField, ...], sort_group: str = "") -> PlayerRankedStat:
    return PlayerRankedStat(League.NFL, espn_category, StatField(category, name, label), pool, context, sort_group)


PLAYER_RANKED_STATS: dict[str, PlayerRankedStat] = {
    "points_per_game": nba_player_stat("offensive", "avgPoints", "points per game"),
    "rebounds_per_game": nba_player_stat("general", "avgRebounds", "rebounds per game"),
    "assists_per_game": nba_player_stat("offensive", "avgAssists", "assists per game"),
    "steals_per_game": nba_player_stat("defensive", "avgSteals", "steals per game"),
    "blocks_per_game": nba_player_stat("defensive", "avgBlocks", "blocks per game"),
    "threes_made": nba_player_stat("offensive", "threePointFieldGoalsMade", "threes made"),
    "field_goal_pct": nba_player_stat("offensive", "fieldGoalPct", "field goal %"),
    "three_point_pct": nba_player_stat("offensive", "threePointFieldGoalPct", "3-point %"),
    "free_throw_pct": nba_player_stat("offensive", "freeThrowPct", "free throw %"),
    "turnovers_per_game": nba_player_stat("offensive", "avgTurnovers", "turnovers per game"),
    "passing_yards": nfl_player_stat("offense:passing", "passing", "passingYards", "passing yards", "passers", PASSING_CONTEXT),
    "passing_touchdowns": nfl_player_stat("offense:passing", "passing", "passingTouchdowns", "passing touchdowns", "passers", PASSING_CONTEXT),
    "passing_interceptions": nfl_player_stat("offense:passing", "passing", "interceptions", "interceptions thrown", "passers", PASSING_CONTEXT),
    "passer_rating": nfl_player_stat("offense:passing", "passing", "QBRating", "passer rating", "passers", PASSING_CONTEXT),
    "completion_pct": nfl_player_stat("offense:passing", "passing", "completionPct", "completion %", "passers", PASSING_CONTEXT),
    "rushing_yards": nfl_player_stat("offense:rushing", "rushing", "rushingYards", "rushing yards", "rushers", RUSHING_CONTEXT),
    "rushing_touchdowns": nfl_player_stat("offense:rushing", "rushing", "rushingTouchdowns", "rushing touchdowns", "rushers", RUSHING_CONTEXT),
    "receiving_yards": nfl_player_stat("offense:receiving", "receiving", "receivingYards", "receiving yards", "receivers", RECEIVING_CONTEXT),
    "receptions": nfl_player_stat("offense:receiving", "receiving", "receptions", "catches", "receivers", RECEIVING_CONTEXT),
    "receiving_touchdowns": nfl_player_stat("offense:receiving", "receiving", "receivingTouchdowns", "receiving touchdowns", "receivers", RECEIVING_CONTEXT),
    "total_tackles": nfl_player_stat("defense", "defensive", "totalTackles", "tackles", "defenders", DEFENSIVE_CONTEXT),
    "sacks_made": nfl_player_stat("defense", "defensive", "sacks", "sacks", "defenders", DEFENSIVE_CONTEXT),
    "defensive_interceptions": nfl_player_stat("defense", "defensiveinterceptions", "interceptions", "interceptions caught", "defenders", DEFENSIVE_CONTEXT, sort_group="defensiveInterceptions"),
}

NBA_TEAM_CONTEXT = (
    NBA_GAMES,
    StatField("offensive", "avgPoints", "points"),
    StatField("offensive", "avgPoints", "allowed", OPPONENT),
)
NFL_TEAM_CONTEXT = (
    NFL_GAMES,
    StatField("passing", "totalPointsPerGame", "points"),
    StatField("passing", "totalPointsPerGame", "allowed", OPPONENT),
)


def nba_team_stat(category: str, name: str, label: str, side: str = OWN) -> TeamRankedStat:
    return TeamRankedStat(League.NBA, StatField(category, name, label, side), NBA_TEAM_CONTEXT)


def nfl_team_stat(category: str, name: str, label: str, side: str = OWN) -> TeamRankedStat:
    return TeamRankedStat(League.NFL, StatField(category, name, label, side), NFL_TEAM_CONTEXT)


# A name both leagues use maps per league; team_rankings looks a statistic up with the league it was asked for.
TEAM_RANKED_STATS: dict[League, dict[str, TeamRankedStat]] = {
    League.NBA: {
        "points_per_game": nba_team_stat("offensive", "avgPoints", "points per game"),
        "points_allowed_per_game": nba_team_stat("offensive", "avgPoints", "points allowed per game", OPPONENT),
        "point_differential": nba_team_stat("differential", "avgPointsDifferential", "point differential per game"),
        "rebounds_per_game": nba_team_stat("general", "avgRebounds", "rebounds per game"),
        "assists_per_game": nba_team_stat("offensive", "avgAssists", "assists per game"),
        "field_goal_pct": nba_team_stat("offensive", "fieldGoalPct", "field goal %"),
        "three_point_pct": nba_team_stat("offensive", "threePointFieldGoalPct", "3-point %"),
        "turnovers_per_game": nba_team_stat("offensive", "avgTurnovers", "turnovers per game"),
    },
    League.NFL: {
        "points_per_game": nfl_team_stat("passing", "totalPointsPerGame", "points per game"),
        "points_allowed_per_game": nfl_team_stat("passing", "totalPointsPerGame", "points allowed per game", OPPONENT),
        "total_yards_per_game": nfl_team_stat("passing", "yardsPerGame", "yards per game"),
        "yards_allowed_per_game": nfl_team_stat("passing", "yardsPerGame", "yards allowed per game", OPPONENT),
        "passing_yards_per_game": nfl_team_stat("passing", "passingYardsPerGame", "passing yards per game"),
        "rushing_yards_per_game": nfl_team_stat("rushing", "rushingYardsPerGame", "rushing yards per game"),
        "passing_yards_allowed_per_game": nfl_team_stat("passing", "passingYardsPerGame", "passing yards allowed per game", OPPONENT),
        "rushing_yards_allowed_per_game": nfl_team_stat("rushing", "rushingYardsPerGame", "rushing yards allowed per game", OPPONENT),
        "interceptions_thrown": nfl_team_stat("passing", "interceptions", "interceptions thrown"),
        "takeaways": nfl_team_stat("miscellaneous", "totalTakeaways", "takeaways"),
        "turnover_differential": nfl_team_stat("miscellaneous", "turnOverDifferential", "turnover differential"),
        "third_down_pct": nfl_team_stat("miscellaneous", "thirdDownConvPct", "third-down %"),
    },
}


@dataclass(frozen=True)
class PlayerRankingAsk:
    """What player_rankings was asked, already checked against the league."""

    league: League
    ranked: PlayerRankedStat
    ascending: bool
    position: str  # as spoken ("tight_end"); "" for every position
    count: int


@dataclass(frozen=True)
class RankedList:
    """The players a ranking shows, how many ESPN qualified, and how far down its list was read to find them."""

    players: list[RankedPlayer]
    qualified_count: int
    read_count: int


@dataclass(frozen=True)
class TeamRankingAsk:
    league: League
    ranked: TeamRankedStat
    ascending: bool
    count: int


def position_plural(position: str) -> str:
    words = position.replace("_", " ")
    return f"{words[:-1]}ies" if words.endswith("y") else f"{words}s"


def counted_position(position: str, number: int) -> str:
    return f"{number} {position.replace('_', ' ') if number == 1 else position_plural(position)}"
