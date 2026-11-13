"""Expose what movies are showing at Manhattan theaters, and what one movie is about, as MCP tools on the existing server, so the agent sees one
tool list.

The tools read only the snapshot the nightly refresh writes (ops/listings_refresh.py); they never call Fandango while the user waits. Every failure is
one sentence telling the model what to do next, never an exception, as the other tools do.
"""

import logging
from collections.abc import Callable
from datetime import date
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

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
        when: Annotated[MovieWhen, Field(description="this_week: next 7 days; coming_up: opening later")] = "this_week",
        genre: Annotated[MovieGenre, Field(description="empty for all")] = "",
        include_horror: Annotated[bool, Field(description="true if the user asks for horror")] = False,
        title: Annotated[str, Field(description='part of a title, e.g. "Clayface", to see where it shows')] = "",
        theater: Annotated[str, Field(description='part of a theater name, e.g. "Angelika"')] = "",
        sort_by: Annotated[
            MovieSortBy,
            Field(description="most_theaters: widest; release_date: newest or soonest; critics_score, audience_score: best reviewed"),
        ] = "most_theaters",
        limit: Annotated[int, Field(description="how many")] = DEFAULT_LIMIT,
    ) -> str:
        """Movies at Manhattan theaters, from Fandango, with rating, length, Rotten Tomatoes scores and theaters. Use this first for what is showing or coming up, before searching the web. Name movies in the order given; say scores as given. Horror is left out unless asked for; if the reply says how many were left out, mention they can be included. No showtimes: tell the user to check Fandango or the theater."""
        query = MovieQuery(when=when, genre=genre, include_horror=include_horror, title=title, theater=theater, sort_by=sort_by, limit=limit)
        return snapshot_answer(settings, lambda snapshot, today: clip_to_whole_lines(movies_text(found_movies(snapshot, query, today), query, snapshot, today), settings.max_words))

    @server.tool(name=MOVIE_DETAILS_TOOL_NAME)
    async def movie_details(title: Annotated[str, Field(description='title as the user said it, e.g. "Clayface"; part is enough')]) -> str:
        """What one movie at Manhattan theaters is about, from Fandango, with cast, Rotten Tomatoes scores, opening date and theaters. Use this first for any one movie in theaters. No showtimes: tell the user to check Fandango or the theater. If it is not found or has no synopsis, search the web."""
        return snapshot_answer(settings, lambda snapshot, today: movie_details_text(movies_named(snapshot.movies, title), title, snapshot, today))


def snapshot_answer(settings: MoviesSettings, answer: Callable[[MoviesSnapshot, date], str]) -> str:
    try:
        return answered_from_snapshot(settings, MoviesSnapshot, answer)
    except SnapshotMissing as error:
        _LOGGER.warning("the movies tools have no snapshot: %s", error)
        return NO_SNAPSHOT_MESSAGE
