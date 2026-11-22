"""Each updates section's text, read from the same sources as the tool family it belongs to: the pulled newsletters, ESPN, and the nightly movie
and Broadway snapshots. A section that cannot be read becomes one line saying so, and the other sections still answer."""

import logging
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from pathlib import Path

import httpx

from broadway_mcp.render import label_parts
from broadway_mcp.settings import BroadwaySettings
from broadway_mcp.shows import BroadwaySnapshot, Show, closings_within, first_previews_within
from movies_mcp.archive import ArchivedSnapshot, snapshot_from_before
from movies_mcp.changes import is_earlier, new_popular_movies, newly_listed_ids, upcoming_anime
from movies_mcp.movies import POPULAR_MIN_CRITICS_SCORE, WIDE_RELEASE_MIN_THEATERS, Movie, MoviesSnapshot, Period
from movies_mcp.render import genre_parts, opening_parts, revival_parts, score_parts
from movies_mcp.settings import MoviesSettings
from newsletters_mcp.answers import NewsletterAnswers
from newsletters_mcp.settings import NewslettersSettings
from sports_mcp.answers import TeamUpdate, team_update
from sports_mcp.cache import SportsCache
from sports_mcp.espn_client import EspnSession, EspnUnavailable
from sports_mcp.fixtures import FixtureTransport
from sports_mcp.leagues import League
from sports_mcp.register import SportsRequestError, one_team
from sports_mcp.render import dated_game_line
from sports_mcp.settings import SportsSettings, sports_today
from updates_mcp.sections import FOLLOWED_TEAM, NEW_SINCE_DAYS, SECTION_TITLES, UPCOMING_DAYS, UPCOMING_SPOKEN, UpdateSection
from utils.snapshot_utils import SnapshotMissing, answered_from_snapshot
from utils.text_utils import spoken_month_day

FOLLOWED_LEAGUE = League.NBA
SECTION_FAILURES = (EspnUnavailable, SportsRequestError, SnapshotMissing, OSError)
UNAVAILABLE_MESSAGE = "{title}: could not be read right now. Tell the user this part is unavailable."
_LOGGER = logging.getLogger(__name__)


class UpdateSources:
    """The settings of every tool family the updates come from, with ESPN read through the sports tools' own cache and recordings."""

    def __init__(
        self,
        newsletters: NewslettersSettings,
        sports: SportsSettings,
        movies: MoviesSettings,
        broadway: BroadwaySettings,
        espn_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.newsletter_answers = NewsletterAnswers(newsletters)
        self.sports = sports
        self.sports_cache = SportsCache(sports.cache_dir)
        self.espn_transport = espn_transport or (FixtureTransport(Path(sports.fixtures_dir)) if sports.fixtures_dir else None)
        self.movies = movies
        self.broadway = broadway

    def espn_session(self) -> EspnSession:
        return EspnSession(self.sports, self.sports_cache, sports_today(self.sports), self.espn_transport)


SectionBlocks = Callable[[UpdateSources], Awaitable[list[str]]]


async def section_blocks(section: UpdateSection, sources: UpdateSources) -> list[str]:
    try:
        return await BLOCKS_BY_SECTION[section](sources)
    except SECTION_FAILURES as error:
        _LOGGER.warning("updates: the %s section could not be read: %s", section, error)
        return [UNAVAILABLE_MESSAGE.format(title=SECTION_TITLES[section])]


async def newsletters_blocks(sources: UpdateSources) -> list[str]:
    return [sources.newsletter_answers.headlines("today")]


async def team_blocks(sources: UpdateSources) -> list[str]:
    """The game today or last night, then the next game; the next game is left out once the season is over for the team."""
    async with sources.espn_session() as espn:
        update = await team_update(espn, FOLLOWED_LEAGUE, one_team(FOLLOWED_LEAGUE, FOLLOWED_TEAM))
    next_game = [f"{FOLLOWED_TEAM} next game: {dated_game_line(update.next_game)}"] if update.next_game else []
    return [recent_game_text(update, sports_today(sources.sports)), *next_game]


def recent_game_text(update: TeamUpdate, today: date) -> str:
    game = update.recent_game
    if game is None:
        return f"{FOLLOWED_TEAM} game today or last night: none."
    when = "today" if game.day == today else "last night"
    lines = [f"{FOLLOWED_TEAM} game {when}: {dated_game_line(game)}"]
    if update.recap:
        lines.append(f"Recap: {update.recap.headline}. {update.recap.summary}")
    return "\n".join(lines)


async def new_movies_blocks(sources: UpdateSources) -> list[str]:
    return [movies_answer(sources, new_movies_text)]


async def anime_blocks(sources: UpdateSources) -> list[str]:
    return [movies_answer(sources, anime_text)]


def movies_answer(sources: UpdateSources, text: Callable[[MoviesSnapshot, ArchivedSnapshot | None, date], str]) -> str:
    """Today's listings beside the copy from a week ago, with the listings' stale note when the refresh has not run for days."""

    def answer(snapshot: MoviesSnapshot, today: date) -> str:
        return text(snapshot, snapshot_from_before(sources.movies, today - timedelta(days=NEW_SINCE_DAYS)), today)

    return answered_from_snapshot(sources.movies, MoviesSnapshot, answer)


def new_movies_text(snapshot: MoviesSnapshot, archived: ArchivedSnapshot | None, today: date) -> str:
    if archived is None or not is_earlier(archived, today):
        return "New popular movies: there are no earlier listings to compare with yet. Tell the user this part starts working within a week."
    since = spoken_month_day(archived.day, today)
    movies = new_popular_movies(snapshot, archived, today)
    if not movies:
        return f"New popular movies: none since {since}."
    heading = f"Popular movies new since {since} (Rotten Tomatoes critics {POPULAR_MIN_CRITICS_SCORE}% or more, at {WIDE_RELEASE_MIN_THEATERS} theaters or more):"
    week = Period.starting(today, "this_week")
    return "\n".join([heading, *(" | ".join([f"- {movie.title}", *genre_parts(movie), *score_parts(movie), f"playing at {len(week.theaters(movie))} theaters"]) for movie in movies)])


def anime_text(snapshot: MoviesSnapshot, archived: ArchivedSnapshot | None, today: date) -> str:
    movies = upcoming_anime(snapshot, today, UPCOMING_DAYS)
    if not movies:
        return f"Anime movies: none listed for Manhattan theaters in {UPCOMING_SPOKEN}."
    newly_listed = newly_listed_ids(snapshot, archived) if archived is not None and is_earlier(archived, today) else set()
    marking = f' ("newly announced": not listed on {spoken_month_day(archived.day, today)})' if newly_listed and archived else ""
    return "\n".join([f"Anime movies coming to Manhattan theaters in {UPCOMING_SPOKEN}{marking}:", *(anime_line(movie, movie.fandango_id in newly_listed, today) for movie in movies)])


def anime_line(movie: Movie, is_newly_listed: bool, today: date) -> str:
    return " | ".join([f"- {movie.title}", *(["newly announced"] if is_newly_listed else []), *revival_parts(movie, today), *opening_parts(movie, today)])


async def broadway_previews_blocks(sources: UpdateSources) -> list[str]:
    return [broadway_answer(sources, previews_text)]


async def broadway_closings_blocks(sources: UpdateSources) -> list[str]:
    return [broadway_answer(sources, closings_text)]


def broadway_answer(sources: UpdateSources, text: Callable[[list[Show], date], str]) -> str:
    return answered_from_snapshot(sources.broadway, BroadwaySnapshot, lambda snapshot, today: text(snapshot.shows, today))


def previews_text(shows: list[Show], today: date) -> str:
    starting = first_previews_within(shows, today, UPCOMING_DAYS)
    return shows_text("starting previews", [show_line(show, f"first preview {spoken_month_day(show.start_date, today)}") for show in starting if show.start_date])


def closings_text(shows: list[Show], today: date) -> str:
    closing = closings_within(shows, today, UPCOMING_DAYS)
    return shows_text("closing", [show_line(show, f"closes {spoken_month_day(show.end_date, today)}") for show in closing if show.end_date])


def shows_text(happening: str, lines: list[str]) -> str:
    heading = f"Broadway shows {happening} in {UPCOMING_SPOKEN}"
    return "\n".join([f"{heading}:", *lines]) if lines else f"{heading}: none."


def show_line(show: Show, when: str) -> str:
    return " | ".join([f"- {show.name}", *label_parts(show), f"at {show.venue}", when])


BLOCKS_BY_SECTION: dict[UpdateSection, SectionBlocks] = {
    "newsletters": newsletters_blocks,
    "warriors": team_blocks,
    "new_movies": new_movies_blocks,
    "anime": anime_blocks,
    "broadway_previews": broadway_previews_blocks,
    "broadway_closings": broadway_closings_blocks,
}
