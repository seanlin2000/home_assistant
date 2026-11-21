"""movies_showing's reply as the model reads it: a heading saying which period, which filters, and in what order, then one "a | b" line per movie.

A movie at three theaters or fewer names them; a wider release says how many, since 17 theater names are not something to say aloud. When the user
asked about one movie or one theater, the theaters are always named. The heading says how many horror movies, and how many movies without a critics
score, were left out, so the model can offer them. A revival says so right after its title.
"""

from datetime import date

from movies_mcp.movies import GENRE_LABELS, LIMITED_RELEASE_MAX_THEATERS, WIDE_RELEASE_MIN_THEATERS, Movie, MovieQuery, MoviesFound, MoviesSnapshot, Period, is_revival
from utils.text_utils import spoken_month_day

MOST_THEATERS_NAMED = 3
RATING_LABELS = {"PG13": "rated PG-13", "NC17": "rated NC-17", "Not Rated": "not rated", "NR": "not rated"}
NO_TITLE_ADVICE = {
    "this_week": 'Tell the user it is not in these theaters this week; when="coming_up" says whether it opens later.',
    "coming_up": "Tell the user no Manhattan theater sells tickets for it yet.",
}
RELEASE_SIZE_LABELS = {
    "any": "",
    "wide": f"wide-release (at {WIDE_RELEASE_MIN_THEATERS} theaters or more) ",
    "limited": f"limited-release (at {LIMITED_RELEASE_MAX_THEATERS} theaters or fewer) ",
}
REVIVALS_LABELS = {"any": "", "only": "revival ", "none": "non-revival "}


def movies_text(found: MoviesFound, query: MovieQuery, snapshot: MoviesSnapshot, today: date) -> str:
    if query.theater and not found.theaters:
        return f'No Manhattan theater on Fandango matches "{query.theater}". The theaters it lists are: {", ".join(snapshot.theaters)}.'
    listed = found.movies[: query.limit]
    lines = [heading(found, query, snapshot, today, shown=len(listed))]
    lines.extend(movie_line(rank, movie, query, found, today) for rank, movie in enumerate(listed, start=1))
    return "\n".join(lines)


def heading(found: MoviesFound, query: MovieQuery, snapshot: MoviesSnapshot, today: date, shown: int) -> str:
    what = f"{movies_label(query)} at {theaters_label(found)}, {period_label(found.period, snapshot, today)}"
    left_out = left_out_note(found)
    if not found.movies and query.title:
        return f'No movie titled like "{query.title}" is showing at {theaters_label(found)} on Fandango, {period_label(found.period, snapshot, today)}{left_out}. {NO_TITLE_ADVICE[query.when]}'
    if not found.movies:
        return f"No {what} on Fandango{left_out}. Tell the user, and offer to drop a filter."
    return f"{what[0].upper()}{what[1:]}, {order_label(query)} ({shown} of {len(found.movies)}){left_out}:"


def left_out_note(found: MoviesFound) -> str:
    horror = [f"{found.horror_left_out} horror {plural('movie', found.horror_left_out)} left out, which movies_showing lists with include_horror=true"] if found.horror_left_out else []
    unscored = (
        [f"{found.unscored_left_out} {plural('movie', found.unscored_left_out)} with no critics score yet left out, which movies_showing lists with min_critics_score=0"]
        if found.unscored_left_out
        else []
    )
    return "".join(f"; {note}" for note in horror + unscored)


def movies_label(query: MovieQuery) -> str:
    genre = f"{query.genre.replace('_', ' ')} " if query.genre else ""
    titled = f' titled like "{query.title}"' if query.title else ""
    scored = f" with a critics score of {query.min_critics_score}% or more" if query.min_critics_score else ""
    return f"{RELEASE_SIZE_LABELS[query.release_size]}{REVIVALS_LABELS[query.revivals]}{genre}movies{titled}{scored}"


def theaters_label(found: MoviesFound) -> str:
    return " or ".join(found.theaters) if found.theaters else "Manhattan theaters"


def period_label(period: Period, snapshot: MoviesSnapshot, today: date) -> str:
    if period.when == "this_week":
        return spoken_day_range(today, period.week_ends)
    return f"first showing after {spoken_month_day(period.week_ends, today)}, with tickets on sale through {spoken_month_day(snapshot.last_day, today)}"


def spoken_day_range(first: date, last: date) -> str:
    """ "October 25 to 31", or "October 29 to November 4" across a month."""
    last_said = str(last.day) if (last.year, last.month) == (first.year, first.month) else spoken_month_day(last, first)
    return f"{spoken_month_day(first, first)} to {last_said}"


def order_label(query: MovieQuery) -> str:
    release_order = "newest releases first" if query.when == "this_week" else "soonest first"
    labels = {
        "most_theaters": "showing at the most theaters first",
        "release_date": release_order,
        "critics_score": "best reviewed by critics on Rotten Tomatoes first",
        "audience_score": "best rated by audiences on Rotten Tomatoes first",
    }
    return labels[query.sort_by]


def movie_line(rank: int, movie: Movie, query: MovieQuery, found: MoviesFound, today: date) -> str:
    parts = [
        f"{rank}. {movie.title}",
        *revival_parts(movie, today),
        *genre_parts(movie),
        *rating_parts(movie),
        *runtime_parts(movie),
        *score_parts(movie),
        where_part(movie, query, found),
        *date_parts(movie, query, today),
    ]
    return " | ".join(parts)


def revival_parts(movie: Movie, today: date) -> list[str]:
    return ["revival of an older film"] if is_revival(movie, today) else []


def genre_parts(movie: Movie) -> list[str]:
    """One label per genre choice, in the choices' order, since the theaters listing a movie each send their own spelling ("Animation", "Animated")."""
    labels = [labels[0] for labels in GENRE_LABELS.values() if set(labels) & set(movie.genres)]
    return [", ".join(labels)] if labels else []


def rating_parts(movie: Movie) -> list[str]:
    return [RATING_LABELS.get(movie.rating, f"rated {movie.rating}")] if movie.rating else []


def runtime_parts(movie: Movie) -> list[str]:
    if not movie.runtime_minutes:
        return []
    hours, minutes = divmod(movie.runtime_minutes, 60)
    spoken = [f"{hours} {plural('hour', hours)}"] if hours else []
    return [" ".join(spoken + ([f"{minutes} {plural('minute', minutes)}"] if minutes else []))]


def score_parts(movie: Movie) -> list[str]:
    """ "Rotten Tomatoes: critics 75%, Certified Fresh, audience 94%", with only the scores it has."""
    scores = movie.scores
    if not scores:
        return []
    critics = [f"critics {scores.critics_score}%"] if scores.critics_score is not None else []
    fresh = ["Certified Fresh"] if scores.certified_fresh and critics else []
    audience = [f"audience {scores.audience_score}%"] if scores.audience_score is not None else []
    return [f"Rotten Tomatoes: {', '.join(critics + fresh + audience)}"]


def where_part(movie: Movie, query: MovieQuery, found: MoviesFound) -> str:
    theaters = found.period.theaters(movie)
    shown = [theater for theater in theaters if theater in found.theaters] if found.theaters else theaters
    if len(shown) <= MOST_THEATERS_NAMED or query.title or query.theater:
        return f"at {', '.join(shown)}"
    return f"playing at {len(shown)} theaters"


def date_parts(movie: Movie, query: MovieQuery, today: date) -> list[str]:
    """When the movie opens or starts showing here, or, listed newest first, when it was released."""
    released = [f"released {spoken_month_day(movie.release_date, today)}"] if query.sort_by == "release_date" and movie.release_date else []
    return opening_parts(movie, today) or released


def opening_parts(movie: Movie, today: date) -> list[str]:
    if movie.release_date and movie.release_date > today:
        return [opening_part(movie, movie.release_date, today)]
    if movie.first_showing > today:
        return [f"showings from {spoken_month_day(movie.first_showing, today)}"]
    return []


def opening_part(movie: Movie, release_date: date, today: date) -> str:
    """A movie can show before it opens: Thursday previews, or a week of early screenings (Wild Horse Nine on 2026-10-30, opening November 6). It
    can also reach Manhattan after it opens elsewhere (De Gaulle - Part Two: Liberty, opening November 7, here from December 4)."""
    opens = f"opens {spoken_month_day(release_date, today)}"
    if movie.first_showing > release_date:
        return f"{opens}, in Manhattan from {spoken_month_day(movie.first_showing, today)}"
    if movie.first_showing == release_date:
        return opens
    return f"{opens}, early showings {'now' if movie.first_showing <= today else 'from ' + spoken_month_day(movie.first_showing, today)}"


def plural(word: str, count: int) -> str:
    return word if count == 1 else f"{word}s"
