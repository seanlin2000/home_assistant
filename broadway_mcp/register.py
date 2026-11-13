"""Expose what is playing on Broadway and Off-Broadway, and what one show is about, as MCP tools on the existing server, so the agent sees one
tool list.

The tools read only the snapshot the nightly refresh writes (ops/listings_refresh.py); they never call TodayTix while the user waits. Every failure is
one sentence telling the model what to do next, never an exception, as the weather and sports tools do.
"""

import logging
from collections.abc import Callable
from datetime import date
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from broadway_mcp.details import show_details_text
from broadway_mcp.render import shows_text
from broadway_mcp.settings import BroadwaySettings
from broadway_mcp.show_names import shows_named
from broadway_mcp.shows import DEFAULT_LIMIT, BroadwaySnapshot, Genre, ShowQuery, ShowType, SortBy, TicketDeal, Timing, VenueTier, matching_shows
from utils.snapshot_utils import SnapshotMissing, answered_from_snapshot
from utils.text_utils import clip_to_whole_lines

BROADWAY_TOOL_NAME = "broadway_shows"
BROADWAY_DETAILS_TOOL_NAME = "broadway_show_details"
NO_SNAPSHOT_MESSAGE = "Broadway error: the show listings have not been fetched yet. Tell the user the Broadway listings are not available right now."
_LOGGER = logging.getLogger(__name__)


def register_broadway_tools(server: MCPServer, settings: BroadwaySettings) -> None:
    @server.tool(name=BROADWAY_TOOL_NAME)
    async def broadway_shows(
        venue_tier: Annotated[VenueTier, Field(description="off_broadway or both only if the user says Off-Broadway")] = "broadway",
        show_type: Annotated[ShowType, Field(description="kind of show")] = "any",
        genre: Annotated[Genre, Field(description="empty for all")] = "",
        max_price: Annotated[float | None, Field(description="top price per ticket, in dollars")] = None,
        ticket_deal: Annotated[TicketDeal, Field(description="cheap same-day tickets")] = "any",
        timing: Annotated[Timing, Field(description="playing now, or not open yet")] = "running",
        sort_by: Annotated[
            SortBy,
            Field(description="views_count: popular now; reviews_count: most reviewed; audience_score: Show-Score; todaytix_rating: TodayTix buyers"),
        ] = "views_count",
        limit: Annotated[int, Field(description="how many")] = DEFAULT_LIMIT,
    ) -> str:
        """Broadway and Off-Broadway shows in New York, from TodayTix, with theater, cheapest ticket, scores, and rush or lottery. Use this first for what is playing or worth seeing, before searching the web. Name shows in the order given, saying musical or play; say prices and scores as given. No performance times: tell the user to pick one on TodayTix."""
        query = ShowQuery(venue_tier=venue_tier, show_type=show_type, genre=genre, max_price=max_price, ticket_deal=ticket_deal, timing=timing, sort_by=sort_by, limit=limit)
        return snapshot_answer(settings, lambda snapshot, today: clip_to_whole_lines(shows_text(matching_shows(snapshot.shows, query, today), query, today), settings.max_words))

    @server.tool(name=BROADWAY_DETAILS_TOOL_NAME)
    async def broadway_show_details(show: Annotated[str, Field(description='title as the user said it, e.g. "Hadestown"; part is enough')]) -> str:
        """What one Broadway or Off-Broadway show is about, from TodayTix, with theater, cheapest ticket and scores. Use this first for any one show. No performance times: tell the user to pick one on TodayTix. If the show is not found or has no description, search the web."""
        return snapshot_answer(settings, lambda snapshot, today: show_details_text(shows_named(snapshot.shows, show), show, today))


def snapshot_answer(settings: BroadwaySettings, answer: Callable[[BroadwaySnapshot, date], str]) -> str:
    try:
        return answered_from_snapshot(settings, BroadwaySnapshot, answer)
    except SnapshotMissing as error:
        _LOGGER.warning("the Broadway tools have no snapshot: %s", error)
        return NO_SNAPSHOT_MESSAGE
