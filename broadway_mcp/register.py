"""Expose what is playing on Broadway and Off-Broadway, and what one show is about, as MCP tools on the existing server, so the agent sees one
tool list.

The tools read only the snapshot the nightly refresh writes (ops/listings_refresh.py); they never call TodayTix while the user waits. Every failure is
one sentence telling the model what to do next, never an exception, as the weather and sports tools do.
"""

import logging
from collections.abc import Callable
from datetime import date

from mcp.server.mcpserver import MCPServer

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
        venue_tier: VenueTier = "broadway",
        show_type: ShowType = "any",
        genre: Genre = "",
        max_price: float | None = None,
        ticket_deal: TicketDeal = "any",
        timing: Timing = "running",
        sort_by: SortBy = "views_count",
        limit: int = DEFAULT_LIMIT,
    ) -> str:
        """What is playing on Broadway and Off-Broadway in New York, from TodayTix's listings: each show's name, musical or play, genres, theater, cheapest ticket, audience score out of 100 from Show-Score's reviews, TodayTix's own rating out of 5 where it has one, and rush or lottery tickets. No performance times. venue_tier: "broadway", "off_broadway", or "both". show_type: "musical", "play", or "any". genre: empty for every genre, or one of comedy, drama, family, romance, thriller, horror, sci_fi_fantasy, adventure, history, biography, satire, jukebox, revival, classic, contemporary, holiday, immersive. max_price: the most the user will pay for one ticket, in dollars. ticket_deal: "rush" or "lottery" for shows with those cheap same-day tickets, or "any". timing: "running" for shows playing now, "upcoming" for shows that have not started. sort_by: "views_count" for what people are looking at now, "reviews_count" for the most reviewed, "audience_score" for the best reviewed on Show-Score, "todaytix_rating" for the best rated by TodayTix buyers (most shows have no rating and come last). limit: how many shows to list."""
        query = ShowQuery(venue_tier=venue_tier, show_type=show_type, genre=genre, max_price=max_price, ticket_deal=ticket_deal, timing=timing, sort_by=sort_by, limit=limit)
        return snapshot_answer(settings, lambda snapshot, today: clip_to_whole_lines(shows_text(matching_shows(snapshot.shows, query, today), query, today), settings.max_words))

    @server.tool(name=BROADWAY_DETAILS_TOOL_NAME)
    async def broadway_show_details(show: str) -> str:
        """What one Broadway or Off-Broadway show in New York is about, from TodayTix: its description, musical or play, genres, theater, cheapest ticket, audience score and TodayTix rating, rush or lottery tickets, and whether it is running. No performance times. show: the show's title alone, as the user said it, such as "Hadestown" or "Rocky Horror"; part of a title is enough."""
        return snapshot_answer(settings, lambda snapshot, today: show_details_text(shows_named(snapshot.shows, show), show, today))


def snapshot_answer(settings: BroadwaySettings, answer: Callable[[BroadwaySnapshot, date], str]) -> str:
    try:
        return answered_from_snapshot(settings, BroadwaySnapshot, answer)
    except SnapshotMissing as error:
        _LOGGER.warning("the Broadway tools have no snapshot: %s", error)
        return NO_SNAPSHOT_MESSAGE
