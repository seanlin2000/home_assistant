"""movie_details' reply as the model reads it: everything the snapshot holds about the one movie the user named, with Fandango's synopsis, its
directors and first actors, its Rotten Tomatoes scores, and every Manhattan theater showing it.

The movie is looked for among everything on sale, this week and later, since "is the new Avengers out yet" is a question about both. When the name
was matched loosely, the reply says which movie it matched. When several match, it lists them and asks the model to ask the user. A movie missing
from the listing or without a synopsis sends the model to the web.
"""

from datetime import date

from pydantic import BaseModel

from movies_mcp.movies import MOVIE_TITLES, Movie, MoviesSnapshot
from movies_mcp.render import genre_parts, opening_parts, rating_parts, runtime_parts, score_parts
from utils.text_utils import spoken_month_day
from utils.title_matching_utils import MatchRule

MAX_LISTED_MATCHES = 5
NOT_LISTED = (
    'No movie on Fandango\'s Manhattan listings through {last_day} matches "{asked}", so no Manhattan theater shows it or sells tickets for it yet. '
    "Tell the user; if they want to know what it is about, search the web."
)
NO_DESCRIPTION = "Fandango has no synopsis of this movie; if the user wants to know what it is about, search the web."


class MoviesNamed(BaseModel):
    rule: MatchRule | None  # None when no movie matched
    movies: list[Movie]  # shortest title first, then the most theaters


def movies_named(movies: list[Movie], asked: str) -> MoviesNamed:
    widest_first = sorted(movies, key=lambda movie: (-len(movie.theaters), movie.title))
    matches = MOVIE_TITLES.matches(asked, [movie.title for movie in widest_first])
    position = {title: index for index, title in enumerate(matches.titles)}
    found = sorted((movie for movie in widest_first if movie.title in position), key=lambda movie: position[movie.title])
    return MoviesNamed(rule=matches.rule, movies=found)


def movie_details_text(named: MoviesNamed, asked: str, snapshot: MoviesSnapshot, today: date) -> str:
    if not named.movies:
        return NOT_LISTED.format(asked=asked, last_day=spoken_month_day(snapshot.last_day, today))
    if len(named.movies) > 1:
        return several_matches_text(named.movies, asked, today)
    movie = named.movies[0]
    about = f"About: {movie.page.description}" if movie.page and movie.page.description else NO_DESCRIPTION
    return "\n".join([one_movie_heading(movie, named.rule, asked), facts_line(movie, today), f"Showing {theaters_text(movie, today)}", about])


def several_matches_text(movies: list[Movie], asked: str, today: date) -> str:
    listed = movies[:MAX_LISTED_MATCHES]
    more = f" ({len(movies) - len(listed)} more not listed)" if len(movies) > len(listed) else ""
    lines = [f'{len(movies)} movies on Fandango\'s Manhattan listings match "{asked}"{more}. Ask the user which one they mean:']
    lines.extend(f"{rank}. {movie.title} | {first_showing_text(movie, today)}" for rank, movie in enumerate(listed, start=1))
    return "\n".join(lines)


def one_movie_heading(movie: Movie, rule: MatchRule | None, asked: str) -> str:
    if rule == MatchRule.SAME_WORDS:
        return f"{movie.title}, from Fandango:"
    return f'Fandango\'s closest match for "{asked}" is {movie.title}:'


def facts_line(movie: Movie, today: date) -> str:
    people = people_parts(movie)
    return " | ".join([*genre_parts(movie), *rating_parts(movie), *runtime_parts(movie), *people, *score_parts(movie), first_showing_text(movie, today)])


def people_parts(movie: Movie) -> list[str]:
    if not movie.page:
        return []
    directed = [f"directed by {' and '.join(movie.page.directors)}"] if movie.page.directors else []
    starring = [f"starring {', '.join(movie.page.cast)}"] if movie.page.cast else []
    return directed + starring


def first_showing_text(movie: Movie, today: date) -> str:
    opening = opening_parts(movie, today)
    return opening[0] if opening else "showing now"


def theaters_text(movie: Movie, today: date) -> str:
    """Every theater, grouped by the day it starts showing the movie: "now at Quad Cinema; from November 6 at AMC Empire 25, Regal Times Square"."""
    starts: dict[str, list[str]] = {}
    for theater, first_day in sorted(movie.theaters.items(), key=lambda item: (item[1], item[0])):
        starts.setdefault("now" if first_day <= today else f"from {spoken_month_day(first_day, today)}", []).append(theater)
    return "; ".join(f"{start} at {', '.join(theaters)}" for start, theaters in starts.items())
