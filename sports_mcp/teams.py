"""Every NBA and NFL team as ESPN numbers it, and how a spoken team name finds one.

A team is found by its nickname ("Warriors"), its city and nickname ("Golden State Warriors"), its abbreviation ("GSW"), a common short form
("Niners"), or its city alone when only one team plays there. Checked in rather than fetched, so most team lookups need no network call; the
lists come from ESPN's teams endpoint (site.api.espn.com/apis/site/v2/sports/{league}/teams), read 2026-10-20.
"""

import re

from pydantic import BaseModel

from sports_mcp.leagues import League

SPOKEN_FILLER = re.compile(r"\b(the|team|football|basketball|club)\b")
NOT_A_NAME_CHARACTER = re.compile(r"[^0-9a-z ]+")
CITY_SPELLINGS = {"la": "los angeles", "ny": "new york"}


class Team(BaseModel):
    espn_id: str
    abbreviation: str
    location: str
    name: str

    @property
    def display_name(self) -> str:
        return f"{self.location} {self.name}"


def team(espn_id: str, abbreviation: str, location: str, name: str) -> Team:
    return Team(espn_id=espn_id, abbreviation=abbreviation, location=location, name=name)


NBA_TEAMS = (
    team("1", "ATL", "Atlanta", "Hawks"),
    team("2", "BOS", "Boston", "Celtics"),
    team("17", "BKN", "Brooklyn", "Nets"),
    team("30", "CHA", "Charlotte", "Hornets"),
    team("4", "CHI", "Chicago", "Bulls"),
    team("5", "CLE", "Cleveland", "Cavaliers"),
    team("6", "DAL", "Dallas", "Mavericks"),
    team("7", "DEN", "Denver", "Nuggets"),
    team("8", "DET", "Detroit", "Pistons"),
    team("9", "GS", "Golden State", "Warriors"),
    team("10", "HOU", "Houston", "Rockets"),
    team("11", "IND", "Indiana", "Pacers"),
    team("12", "LAC", "LA", "Clippers"),
    team("13", "LAL", "Los Angeles", "Lakers"),
    team("29", "MEM", "Memphis", "Grizzlies"),
    team("14", "MIA", "Miami", "Heat"),
    team("15", "MIL", "Milwaukee", "Bucks"),
    team("16", "MIN", "Minnesota", "Timberwolves"),
    team("3", "NO", "New Orleans", "Pelicans"),
    team("18", "NY", "New York", "Knicks"),
    team("25", "OKC", "Oklahoma City", "Thunder"),
    team("19", "ORL", "Orlando", "Magic"),
    team("20", "PHI", "Philadelphia", "76ers"),
    team("21", "PHX", "Phoenix", "Suns"),
    team("22", "POR", "Portland", "Trail Blazers"),
    team("23", "SAC", "Sacramento", "Kings"),
    team("24", "SA", "San Antonio", "Spurs"),
    team("28", "TOR", "Toronto", "Raptors"),
    team("26", "UTAH", "Utah", "Jazz"),
    team("27", "WSH", "Washington", "Wizards"),
)

NFL_TEAMS = (
    team("22", "ARI", "Arizona", "Cardinals"),
    team("1", "ATL", "Atlanta", "Falcons"),
    team("33", "BAL", "Baltimore", "Ravens"),
    team("2", "BUF", "Buffalo", "Bills"),
    team("29", "CAR", "Carolina", "Panthers"),
    team("3", "CHI", "Chicago", "Bears"),
    team("4", "CIN", "Cincinnati", "Bengals"),
    team("5", "CLE", "Cleveland", "Browns"),
    team("6", "DAL", "Dallas", "Cowboys"),
    team("7", "DEN", "Denver", "Broncos"),
    team("8", "DET", "Detroit", "Lions"),
    team("9", "GB", "Green Bay", "Packers"),
    team("34", "HOU", "Houston", "Texans"),
    team("11", "IND", "Indianapolis", "Colts"),
    team("30", "JAX", "Jacksonville", "Jaguars"),
    team("12", "KC", "Kansas City", "Chiefs"),
    team("13", "LV", "Las Vegas", "Raiders"),
    team("24", "LAC", "Los Angeles", "Chargers"),
    team("14", "LAR", "Los Angeles", "Rams"),
    team("15", "MIA", "Miami", "Dolphins"),
    team("16", "MIN", "Minnesota", "Vikings"),
    team("17", "NE", "New England", "Patriots"),
    team("18", "NO", "New Orleans", "Saints"),
    team("19", "NYG", "New York", "Giants"),
    team("20", "NYJ", "New York", "Jets"),
    team("21", "PHI", "Philadelphia", "Eagles"),
    team("23", "PIT", "Pittsburgh", "Steelers"),
    team("25", "SF", "San Francisco", "49ers"),
    team("26", "SEA", "Seattle", "Seahawks"),
    team("27", "TB", "Tampa Bay", "Buccaneers"),
    team("10", "TEN", "Tennessee", "Titans"),
    team("28", "WSH", "Washington", "Commanders"),
)

TEAMS = {League.NBA: NBA_TEAMS, League.NFL: NFL_TEAMS}

# Short forms people say, and the abbreviations other sites use, mapped to ESPN's abbreviation.
NICKNAMES = {
    League.NBA: {
        "gsw": "GS",
        "dubs": "GS",
        "sixers": "PHI",
        "cavs": "CLE",
        "mavs": "DAL",
        "wolves": "MIN",
        "t wolves": "MIN",
        "blazers": "POR",
        "pels": "NO",
        "nop": "NO",
        "nyk": "NY",
        "la lakers": "LAL",
        "los angeles clippers": "LAC",
        "sas": "SA",
        "uta": "UTAH",
        "was": "WSH",
    },
    League.NFL: {
        "niners": "SF",
        "sf 49ers": "SF",
        "forty niners": "SF",
        "pats": "NE",
        "bucs": "TB",
        "jags": "JAX",
        "jac": "JAX",
        "was": "WSH",
        "la rams": "LAR",
        "la chargers": "LAC",
        "ny giants": "NYG",
        "ny jets": "NYJ",
        "gnb": "GB",
        "kan": "KC",
        "nwe": "NE",
        "sfo": "SF",
        "tam": "TB",
        "nor": "NO",
        "lvr": "LV",
    },
}


def find_teams(league: League, spoken: str) -> list[Team]:
    """The teams a spoken name could mean: one when it is clear, several when only a shared city was said ("Los Angeles"), none when nothing matches."""
    wanted = normalized(spoken)
    teams = TEAMS[league]
    by_abbreviation = {item.abbreviation.lower(): item for item in teams}
    nickname = NICKNAMES[league].get(wanted)
    if nickname:
        return [by_abbreviation[nickname.lower()]]
    exact = [item for item in teams if wanted in names_for(item)]
    if exact:
        return exact
    return [item for item in teams if same_city(item.location, wanted)]


def same_city(location: str, wanted: str) -> bool:
    """ESPN writes the Clippers' city as "LA" and the Lakers' as "Los Angeles"; said aloud they are the same city."""
    return CITY_SPELLINGS.get(normalized(location), normalized(location)) == CITY_SPELLINGS.get(wanted, wanted)


def names_for(item: Team) -> set[str]:
    return {item.abbreviation.lower(), normalized(item.name), normalized(item.display_name), normalized(f"{item.abbreviation} {item.name}")}


def normalized(spoken: str) -> str:
    plain = NOT_A_NAME_CHARACTER.sub(" ", spoken.lower().replace("-", " "))
    return " ".join(SPOKEN_FILLER.sub(" ", plain).split())


def team_by_id(league: League, espn_id: str) -> Team | None:
    return next((item for item in TEAMS[league] if item.espn_id == espn_id), None)
