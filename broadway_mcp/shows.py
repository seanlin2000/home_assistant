"""The shows the nightly refresh keeps from TodayTix, and the filters and orders broadway_shows offers over them.

Every label a show carries is TodayTix's own: its category (Musicals, Plays, Comedy Shows) and its tags (Comedy, Drama, Family / Kid-friendly). The
tool's genre choices are spellings a model can pass, each standing for exactly one TodayTix tag, so nothing is labelled here.
"""

from collections.abc import Callable
from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, field_validator


class Tier(StrEnum):
    BROADWAY = "broadway"
    OFF_BROADWAY = "off_broadway"


class Show(BaseModel):
    name: str
    tier: Tier
    category: str  # TodayTix's, e.g. "Musicals" or "Comedy Shows"
    tags: list[str]  # TodayTix's, without the Broadway and Off Broadway tags that set the tier
    venue: str
    start_date: date | None  # the first preview; None when TodayTix has not announced it
    end_date: date | None  # the closing date; None when the run is open-ended or TodayTix has none
    views_count: int  # how often the show's TodayTix page was opened recently
    reviews_count: int | None  # Show-Score's audience reviews, which TodayTix shows on its pages
    audience_score: int | None  # Show-Score's, out of 100
    todaytix_rating: float | None = None  # TodayTix's own buyers' rating, out of 5; most shows have none. Defaulted so an older snapshot still reads
    todaytix_ratings_count: int | None = None
    lowest_price: float | None  # dollars, the cheapest regular ticket
    has_rush: bool
    has_lottery: bool
    description: str = ""  # TodayTix's one to three sentences, italics marks removed; empty for most Off-Broadway shows. Defaulted so an older snapshot still reads


class BroadwaySnapshot(BaseModel):
    refreshed_at: datetime
    shows: list[Show]


VenueTier = Literal["broadway", "off_broadway", "both"]
ShowType = Literal["musical", "play", "any"]
Genre = Literal[
    "",
    "comedy",
    "drama",
    "family",
    "romance",
    "thriller",
    "horror",
    "sci_fi_fantasy",
    "adventure",
    "history",
    "biography",
    "satire",
    "jukebox",
    "revival",
    "classic",
    "contemporary",
    "holiday",
    "immersive",
]
TicketDeal = Literal["any", "rush", "lottery"]
Timing = Literal["running", "upcoming"]
SortBy = Literal["views_count", "reviews_count", "audience_score", "todaytix_rating"]

GENRE_TAGS: dict[str, str] = {
    "comedy": "Comedy",
    "drama": "Drama",
    "family": "Family / Kid-friendly",
    "romance": "Romance",
    "thriller": "Crime / Thriller / Mystery",
    "horror": "Horror",
    "sci_fi_fantasy": "Sci Fi / Fantasy",
    "adventure": "Adventure",
    "history": "History",
    "biography": "Biography",
    "satire": "Satire",
    "jukebox": "Jukebox",
    "revival": "Revival",
    "classic": "Classic",
    "contemporary": "Contemporary",
    "holiday": "Holiday",
    "immersive": "Immersive",
}
SHOW_TYPE_CATEGORIES = {"musical": "Musicals", "play": "Plays"}
TIERS_BY_VENUE_TIER = {"broadway": {Tier.BROADWAY}, "off_broadway": {Tier.OFF_BROADWAY}, "both": {Tier.BROADWAY, Tier.OFF_BROADWAY}}
DEFAULT_LIMIT = 10
MAX_LIMIT = 25  # the system prompt's longest spoken list
NO_COUNT = -1  # sorts a show without reviews or a score after every show that has them


class ShowQuery(BaseModel):
    """What the user asked for. limit is held to the system prompt's longest spoken list rather than refused, since a small model asks for 50."""

    venue_tier: VenueTier = "broadway"
    show_type: ShowType = "any"
    genre: Genre = ""
    max_price: float | None = None
    ticket_deal: TicketDeal = "any"
    timing: Timing = "running"
    sort_by: SortBy = "views_count"
    limit: int = DEFAULT_LIMIT

    @field_validator("limit")
    @classmethod
    def limit_within_a_spoken_list(cls, limit: int) -> int:
        return min(max(limit, 1), MAX_LIMIT)


def matching_shows(shows: list[Show], query: ShowQuery, today: date) -> list[Show]:
    """The shows that pass every filter the query sets, in the order it asks for."""
    filters = [tier_filter(query), type_filter(query), genre_filter(query), price_filter(query), deal_filter(query), timing_filter(query, today)]
    kept = [show for show in shows if all(keeps(show) for keeps in filters)]
    return sorted(kept, key=sort_key(query.sort_by))


def tier_filter(query: ShowQuery) -> Callable[[Show], bool]:
    tiers = TIERS_BY_VENUE_TIER[query.venue_tier]
    return lambda show: show.tier in tiers


def type_filter(query: ShowQuery) -> Callable[[Show], bool]:
    category = SHOW_TYPE_CATEGORIES.get(query.show_type)
    return lambda show: category is None or show.category == category


def genre_filter(query: ShowQuery) -> Callable[[Show], bool]:
    tag = GENRE_TAGS.get(query.genre)
    return lambda show: tag is None or tag in show.tags


def price_filter(query: ShowQuery) -> Callable[[Show], bool]:
    """A show without a price on TodayTix is left out once the user names a budget, since it cannot be shown to fit."""
    ceiling = query.max_price
    return lambda show: ceiling is None or (show.lowest_price is not None and show.lowest_price <= ceiling)


def deal_filter(query: ShowQuery) -> Callable[[Show], bool]:
    deal = query.ticket_deal
    return lambda show: deal == "any" or (deal == "rush" and show.has_rush) or (deal == "lottery" and show.has_lottery)


def timing_filter(query: ShowQuery, today: date) -> Callable[[Show], bool]:
    if query.timing == "upcoming":
        return lambda show: is_upcoming(show, today)
    return lambda show: is_running(show, today)


def is_running(show: Show, today: date) -> bool:
    started = show.start_date is not None and show.start_date <= today
    return started and not has_closed(show, today)


def is_upcoming(show: Show, today: date) -> bool:
    """Not started yet, including a show TodayTix lists at a theater before announcing its first preview."""
    return (show.start_date is None or show.start_date > today) and not has_closed(show, today)


def has_closed(show: Show, today: date) -> bool:
    return show.end_date is not None and show.end_date < today


def sort_key(sort_by: SortBy) -> Callable[[Show], tuple[float, int]]:
    """Largest first, with the views count breaking ties so the order never depends on TodayTix's listing order."""
    orders: dict[str, Callable[[Show], tuple[float, int]]] = {
        "views_count": lambda show: (-show.views_count, 0),
        "reviews_count": lambda show: (-(show.reviews_count if show.reviews_count is not None else NO_COUNT), -show.views_count),
        "audience_score": lambda show: (-(show.audience_score if show.audience_score is not None else NO_COUNT), -show.views_count),
        "todaytix_rating": lambda show: (-(show.todaytix_rating if show.todaytix_rating is not None else NO_COUNT), -show.views_count),
    }
    return orders[sort_by]
