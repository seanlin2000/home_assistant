"""Expose what is playing on Broadway and Off-Broadway as an MCP tool on the existing server, so the agent sees one tool list.

The tool reads only the snapshot the nightly refresh writes (ops/listings_refresh.py); it never calls TodayTix while the user waits. Every failure is
one sentence telling the model what to do next, never an exception, as the weather and sports tools do.
"""

import logging

from mcp.server.mcpserver import MCPServer

from broadway_mcp.render import age_note, shows_text
from broadway_mcp.settings import BroadwaySettings, broadway_today
from broadway_mcp.shows import DEFAULT_LIMIT, BroadwaySnapshot, Genre, ShowQuery, ShowType, SortBy, TicketDeal, Timing, VenueTier, matching_shows
from utils.snapshot_utils import SnapshotMissing, read_snapshot
from utils.text_utils import clip_to_whole_lines

BROADWAY_TOOL_NAME = "broadway_shows"
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
        """What is playing on Broadway and Off-Broadway in New York, from TodayTix's listings: each show's name, musical or play, genres, theater, cheapest ticket, audience score out of 100 from Show-Score's reviews, TodayTix's own rating out of 5 where it has one, and rush or lottery tickets. No performance times. venue_tier: "broadway", "off_broadway", or "both". show_type: "musical", "play", or "any". genre: empty for every genre, or one of comedy, drama, family, romance, thriller, horror, sci_fi_fantasy, adventure, history, biography, satire, jukebox, revival, classic, contemporary, holiday, immersive. max_price: the most the user will pay for one ticket, in dollars. ticket_deal: "rush" or "lottery" for shows with those cheap same-day tickets, or "any". timing: "running" for shows playing now, "upcoming" for shows that have not started. sort_by: "views_count" for what people are looking at now, "reviews_count" for the most reviewed, "audience_score" for the best reviewed on Show-Score. limit: how many shows to list."""
        query = ShowQuery(venue_tier=venue_tier, show_type=show_type, genre=genre, max_price=max_price, ticket_deal=ticket_deal, timing=timing, sort_by=sort_by, limit=limit)
        return broadway_answer(settings, query)


def broadway_answer(settings: BroadwaySettings, query: ShowQuery) -> str:
    try:
        return listing_answer(read_snapshot(settings.snapshot_path, BroadwaySnapshot), query, settings)
    except SnapshotMissing as error:
        _LOGGER.warning("%s has no snapshot: %s", BROADWAY_TOOL_NAME, error)
        return NO_SNAPSHOT_MESSAGE


def listing_answer(snapshot: BroadwaySnapshot, query: ShowQuery, settings: BroadwaySettings) -> str:
    """The matching shows, then a note when the nightly refresh has not run for days, which the word budget never cuts."""
    today = broadway_today(settings)
    listing = clip_to_whole_lines(shows_text(matching_shows(snapshot.shows, query, today), query, today), settings.max_words)
    stale_note = age_note(snapshot.refreshed_at, today, settings.stale_after_days)
    return f"{listing}\n{stale_note}" if stale_note else listing
