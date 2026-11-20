"""The movies the nightly refresh keeps from Fandango's Manhattan listings, and the filters and orders movies_showing offers over them.

Every label a movie carries is Fandango's own: its genres (Drama, Action/Adventure, Kids & Family) and its MPAA rating. The tool's genre choices are
spellings a model can pass, each standing for the Fandango genres of that name (thriller is both of Fandango's thriller genres), so nothing is
labelled here. Horror is left out unless it is asked for.

The listings reach weeks ahead, as far as theaters have put tickets on sale, so a question is about one of two periods: the movies showing this
week, or the ones whose first Manhattan showing comes after it (anniversary re-releases, concerts, the next big openings).
"""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, field_validator

from utils.snapshot_utils import DatedSnapshot
from utils.title_matching_utils import TitleMatcher


class MoviePage(BaseModel):
    """What a movie's own Fandango page says about it. It rarely changes, so the refresh reads it once and carries it forward night to night."""

    description: str  # Fandango's synopsis; empty when it has none
    directors: list[str]
    cast: list[str]  # the first actors Fandango lists, in its order


class RottenTomatoesScores(BaseModel):
    """Rotten Tomatoes' scores as Fandango shows them, read every night, since they move while a movie is new. Either is None before it has one."""

    critics_score: int | None  # the Tomatometer: the percentage of critics' reviews that are positive
    audience_score: int | None  # the Popcornmeter: the percentage of audience ratings that are positive
    certified_fresh: bool


class Movie(BaseModel):
    fandango_id: int
    page_path: str  # the movie's page on fandango.com: "/clayface-2026-244768/movie-overview"
    title: str  # Fandango's, without the "(2026)" it adds to some titles
    genres: list[str]  # Fandango's, from every theater that lists the movie
    rating: str  # Fandango's MPAA code: "R", "PG13", "Not Rated"; empty when it gives none
    release_date: date | None
    runtime_minutes: int | None
    theaters: dict[str, date]  # each Manhattan theater with a showing on a day read, and the first such day
    page: MoviePage | None = None  # None until the movie's page has been read
    scores: RottenTomatoesScores | None = None  # None when Fandango had no scores for it

    @property
    def first_showing(self) -> date:
        return min(self.theaters.values())

    def theaters_showing_by(self, last_day: date) -> list[str]:
        return sorted(theater for theater, first_day in self.theaters.items() if first_day <= last_day)


class MoviesSnapshot(DatedSnapshot):
    first_day: date
    last_day: date
    theaters: list[str]  # every Manhattan theater Fandango listed, for the theater filter
    movies: list[Movie]


MovieGenre = Literal[
    "",
    "action",
    "animation",
    "anime",
    "biography",
    "comedy",
    "concert_or_event",
    "documentary",
    "drama",
    "family",
    "foreign",
    "history",
    "holiday",
    "horror",
    "lgbtq",
    "music",
    "romance",
    "sci_fi_fantasy",
    "sports",
    "thriller",
    "war",
    "western",
]
MovieWhen = Literal["this_week", "coming_up"]
MovieSortBy = Literal["most_theaters", "release_date", "critics_score", "audience_score"]

# Every genre Fandango gave a Manhattan movie in the listings of 2026-10-25, under the choice that stands for it, its usual label first.
GENRE_LABELS: dict[str, tuple[str, ...]] = {
    "action": ("Action/Adventure",),
    "animation": ("Animation", "Animated"),
    "anime": ("Anime",),
    "biography": ("Biography",),
    "comedy": ("Comedy",),
    "concert_or_event": ("Concert/Special Events",),
    "documentary": ("Documentary",),
    "drama": ("Drama",),
    "family": ("Kids & Family", "Family"),
    "foreign": ("Art House/Foreign",),
    "history": ("Historical Film",),
    "holiday": ("Holiday",),
    "horror": ("Horror",),
    "lgbtq": ("LGBTQ+",),
    "music": ("Music/Performing Arts",),
    "romance": ("Romance",),
    "sci_fi_fantasy": ("Sci-Fi/Fantasy",),
    "sports": ("Sports",),
    "thriller": ("Mystery & Thriller", "Suspense/Thriller"),
    "war": ("War",),
    "western": ("Western",),
}
HORROR_LABELS = frozenset(GENRE_LABELS["horror"])
DAYS_IN_A_WEEK = 7
DEFAULT_LIMIT = 10
MAX_LIMIT = 25  # the longest list the system prompt lets the model read out
NO_SCORE = -1  # sorts after a score of 0
MOVIE_TITLES = TitleMatcher(frozenset({"the", "a", "an", "movie", "film", "new"}))
THEATER_NAMES = TitleMatcher(frozenset({"the", "theater", "theatre", "theaters", "cinema", "cinemas", "movie"}))


class MovieQuery(BaseModel):
    when: MovieWhen = "this_week"
    genre: MovieGenre = ""
    include_horror: bool = False
    title: str = ""
    theater: str = ""
    sort_by: MovieSortBy = "most_theaters"
    limit: int = DEFAULT_LIMIT

    @field_validator("limit")
    @classmethod
    def limit_to_a_spoken_list(cls, limit: int) -> int:
        return max(1, min(limit, MAX_LIMIT))


class Period(BaseModel):
    """This week (today and the six days after it) or what comes after it, and which of a movie's theaters belong to it."""

    when: MovieWhen
    week_ends: date

    @classmethod
    def starting(cls, today: date, when: MovieWhen) -> "Period":
        return cls(when=when, week_ends=today + timedelta(days=DAYS_IN_A_WEEK - 1))

    def includes(self, movie: Movie) -> bool:
        return (movie.first_showing <= self.week_ends) == (self.when == "this_week")

    def theaters(self, movie: Movie) -> list[str]:
        """This week, only the theaters showing the movie by the week's end; coming up, every theater that has put it on sale."""
        return movie.theaters_showing_by(self.week_ends) if self.when == "this_week" else sorted(movie.theaters)

    def release_order(self, movie: Movie) -> int:
        """This week, the newest release first; coming up, the soonest first Manhattan showing first."""
        return -release_ordinal(movie) if self.when == "this_week" else movie.first_showing.toordinal()


class MoviesFound(BaseModel):
    movies: list[Movie]  # in the order asked for
    period: Period
    theaters: list[str]  # the theaters a theater filter matched; empty when no theater was asked for
    horror_left_out: int  # horror movies that fit every other filter and were left out by default


def found_movies(snapshot: MoviesSnapshot, query: MovieQuery, today: date) -> MoviesFound:
    period = Period.starting(today, query.when)
    theaters = THEATER_NAMES.matches(query.theater, snapshot.theaters).titles if query.theater else []
    candidates = [movie for movie in snapshot.movies if period.includes(movie) and (not query.theater or set(period.theaters(movie)) & set(theaters))]
    if query.title:
        titles = set(MOVIE_TITLES.matches(query.title, [movie.title for movie in candidates]).titles)
        candidates = [movie for movie in candidates if movie.title in titles]
    candidates = [movie for movie in candidates if has_genre(movie, query.genre)]
    shown = [movie for movie in candidates if horror_is_shown(movie, query)]
    ordered = sorted(shown, key=sort_key(query.sort_by, period))
    return MoviesFound(movies=ordered, period=period, theaters=theaters, horror_left_out=len(candidates) - len(shown))


def has_genre(movie: Movie, genre: MovieGenre) -> bool:
    return not genre or bool(set(GENRE_LABELS[genre]) & set(movie.genres))


def horror_is_shown(movie: Movie, query: MovieQuery) -> bool:
    """Horror is left out by default; asking for horror, for every genre with include_horror, or for one title by name shows it."""
    asked_for = query.include_horror or query.genre == "horror" or bool(query.title)
    return asked_for or not HORROR_LABELS & set(movie.genres)


def sort_key(sort_by: MovieSortBy, period: Period) -> Callable[[Movie], tuple[int, int, str]]:
    """Largest first; the number of theaters or the release, then the title, break ties, so the order never depends on Fandango's listing order.
    A movie without the score asked for comes after every movie with one."""
    orders: dict[str, Callable[[Movie], tuple[int, int, str]]] = {
        "most_theaters": lambda movie: (-len(period.theaters(movie)), period.release_order(movie), movie.title),
        "release_date": lambda movie: (period.release_order(movie), -len(period.theaters(movie)), movie.title),
        "critics_score": lambda movie: (-critics_score(movie), -len(period.theaters(movie)), movie.title),
        "audience_score": lambda movie: (-audience_score(movie), -len(period.theaters(movie)), movie.title),
    }
    return orders[sort_by]


def release_ordinal(movie: Movie) -> int:
    return movie.release_date.toordinal() if movie.release_date else 0  # no release date sorts as the oldest


def critics_score(movie: Movie) -> int:
    return movie.scores.critics_score if movie.scores and movie.scores.critics_score is not None else NO_SCORE


def audience_score(movie: Movie) -> int:
    return movie.scores.audience_score if movie.scores and movie.scores.audience_score is not None else NO_SCORE
