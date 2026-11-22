"""What changed in the movie listings since last week, for the updates tool: popular movies that were not popular then, and anime movies coming to
Manhattan, marked when they were not listed then. "Last week" is the dated copy the nightly refresh keeps (movies_mcp/archive.py)."""

from datetime import date, timedelta

from movies_mcp.archive import ArchivedSnapshot
from movies_mcp.movies import MAX_LIMIT, Movie, MovieQuery, MoviesSnapshot, found_movies, has_genre

ANIME = "anime"


def is_earlier(archived: ArchivedSnapshot | None, today: date) -> bool:
    """A copy from today, the only one there is on the first night, has nothing earlier to compare with."""
    return archived is not None and archived.day < today


def new_popular_movies(snapshot: MoviesSnapshot, archived: ArchivedSnapshot, today: date) -> list[Movie]:
    """On popular_movies' list today but not on the list the copy gave on its own day, widest first. A movie that went wide or rose past the score
    counts as new, as does a new release."""
    before = {movie.fandango_id for movie in popular_movies(archived.snapshot, archived.day)}
    return [movie for movie in popular_movies(snapshot, today) if movie.fandango_id not in before]


def popular_movies(snapshot: MoviesSnapshot, today: date) -> list[Movie]:
    return found_movies(snapshot, MovieQuery.popular(genre="", sort_by="most_theaters", limit=MAX_LIMIT), today).movies


def upcoming_anime(snapshot: MoviesSnapshot, today: date, days: int) -> list[Movie]:
    """Anime movies whose first Manhattan showing is after today and within the days given, soonest first."""
    last_day = today + timedelta(days=days)
    coming = [movie for movie in snapshot.movies if has_genre(movie, ANIME) and today < movie.first_showing <= last_day]
    return sorted(coming, key=lambda movie: (movie.first_showing, movie.title))


def newly_listed_ids(snapshot: MoviesSnapshot, archived: ArchivedSnapshot) -> set[int]:
    before = {movie.fandango_id for movie in archived.snapshot.movies}
    return {movie.fandango_id for movie in snapshot.movies if movie.fandango_id not in before}
