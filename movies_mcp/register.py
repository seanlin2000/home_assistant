"""Expose what movies are showing at Manhattan theaters, and what one movie is about, as MCP tools on the existing server, so the agent sees one
tool list.

The tools read only the snapshot the nightly refresh writes (ops/listings_refresh.py); they never call Fandango while the user waits. Every failure is
one sentence telling the model what to do next, never an exception, as the other tools do.
"""

import logging
from collections.abc import Callable
from datetime import date

from mcp.server.mcpserver import MCPServer

from movies_mcp.details import movie_details_text, movies_named
from movies_mcp.movies import DEFAULT_LIMIT, MovieGenre, MovieQuery, MovieSortBy, MoviesSnapshot, MovieWhen, found_movies
from movies_mcp.render import movies_text
from movies_mcp.settings import MoviesSettings
from utils.snapshot_utils import SnapshotMissing, answered_from_snapshot
from utils.text_utils import clip_to_whole_lines

MOVIES_TOOL_NAME = "movies_showing"
MOVIE_DETAILS_TOOL_NAME = "movie_details"
NO_SNAPSHOT_MESSAGE = "Movies error: the movie listings have not been fetched yet. Tell the user the movie listings are not available right now."
_LOGGER = logging.getLogger(__name__)


def register_movies_tools(server: MCPServer, settings: MoviesSettings) -> None:
    @server.tool(name=MOVIES_TOOL_NAME)
    async def movies_showing(
        when: MovieWhen = "this_week",
        genre: MovieGenre = "",
        include_horror: bool = False,
        title: str = "",
        theater: str = "",
        sort_by: MovieSortBy = "most_theaters",
        limit: int = DEFAULT_LIMIT,
    ) -> str:
        """What movies are showing at Manhattan movie theaters, from Fandango: each movie's genres, rating, running time, Rotten Tomatoes critics and audience scores, and how many theaters show it, or which ones when three or fewer do. No showtimes. when: "this_week" for today through the next six days, "coming_up" for movies whose first Manhattan showing is later, as far ahead as theaters sell tickets (new releases, anniversary re-releases, concerts, opera). genre: empty for every genre, or one of action, animation, anime, biography, comedy, concert_or_event, documentary, drama, family, foreign, history, holiday, horror, lgbtq, music, romance, sci_fi_fantasy, sports, thriller, war, western. include_horror: horror movies are left out unless this is true, genre is "horror", or a title is asked for. title: part of a movie's title, to ask whether and where it is showing, such as "Clayface". theater: part of a theater's name, for what one theater shows, such as "Angelika" or "AMC Empire". sort_by: "most_theaters" for the widest releases first, "release_date" for the newest releases first this week or the soonest first coming up, "critics_score" for the best reviewed by critics, "audience_score" for the best rated by audiences (movies without a score come last). limit: how many movies to list."""
        query = MovieQuery(when=when, genre=genre, include_horror=include_horror, title=title, theater=theater, sort_by=sort_by, limit=limit)
        return snapshot_answer(settings, lambda snapshot, today: clip_to_whole_lines(movies_text(found_movies(snapshot, query, today), query, snapshot, today), settings.max_words))

    @server.tool(name=MOVIE_DETAILS_TOOL_NAME)
    async def movie_details(title: str) -> str:
        """What one movie showing or on sale at Manhattan theaters is about, from Fandango: its synopsis, director, lead actors, genres, rating, running time, Rotten Tomatoes critics and audience scores, when it opens, and every Manhattan theater showing it. No showtimes. title: the movie's title alone, as the user said it, such as "Clayface" or "Avengers Doomsday"; part of a title is enough."""
        return snapshot_answer(settings, lambda snapshot, today: movie_details_text(movies_named(snapshot.movies, title), title, snapshot, today))


def snapshot_answer(settings: MoviesSettings, answer: Callable[[MoviesSnapshot, date], str]) -> str:
    try:
        return answered_from_snapshot(settings, MoviesSnapshot, answer)
    except SnapshotMissing as error:
        _LOGGER.warning("the movies tools have no snapshot: %s", error)
        return NO_SNAPSHOT_MESSAGE
