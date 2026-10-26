"""broadway_shows and the nightly refresh behind it: which TodayTix entries count as shows, the snapshot written in one piece and kept when TodayTix
fails, every filter and order the tool offers, the replies when there is no snapshot or an old one, and the router, filler, and refresh command around
it. The listing is the benchmark's own (benchmark/fixtures/broadway/broadway.json, TodayTix's New York listing kept on 2026-10-25), so these tests also
prove the benchmark's snapshot answers the calls it expects; tests/fixtures/todaytix_shows.json is a trimmed copy of the raw listing it came from."""

import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, get_args

import httpx
import pytest
from mcp.server.mcpserver import MCPServer

from assistant_core.agent_loop import filler_for
from assistant_core.models import DEFAULT_SHOWS_FILLER_PHRASES, SHOWS_TOOL_NAMES, AgentPolicy, Route, RouteDecision, ToolCall, ToolSpec
from assistant_core.router import SHOWS_DIRECTIVE, directive_for, route_to_offered_tools, rule_route
from assistant_core.tools import McpToolBox
from benchmark.mcp_process import BROADWAY_RECORDED_ON, BROADWAY_SNAPSHOT_PATH
from broadway_mcp.register import NO_SNAPSHOT_MESSAGE, register_broadway_tools
from broadway_mcp.settings import BroadwaySettings, broadway_settings_from_environment
from broadway_mcp.shows import GENRE_TAGS, BroadwaySnapshot, Genre, Tier
from broadway_mcp.todaytix import TodayTixUnavailable, refresh_broadway_snapshot, show_from_product
from ops.listings_refresh import failed_refreshes
from utils.snapshot_utils import SnapshotMissing, read_snapshot, write_snapshot

RECORDED_ON = date.fromisoformat(BROADWAY_RECORDED_ON)
RAW_LISTING = json.loads(Path("tests/fixtures/todaytix_shows.json").read_text())
SHOW_LINE = re.compile(r"^\d+\. ")


def recorded_settings(today: date = RECORDED_ON) -> BroadwaySettings:
    return BroadwaySettings(snapshot_path=BROADWAY_SNAPSHOT_PATH, today=today)


async def ask(settings: BroadwaySettings | None = None, **arguments: Any) -> str:
    server = MCPServer("test")
    register_broadway_tools(server, settings or recorded_settings())
    async with McpToolBox(server) as toolbox:
        return await toolbox.call(ToolCall(id="1", name="broadway_shows", arguments=arguments))


def show_lines(reply: str) -> list[str]:
    return [line for line in reply.split("\n") if SHOW_LINE.match(line)]


def listed_names(reply: str) -> list[str]:
    return [SHOW_LINE.sub("", line).split(" | ")[0] for line in show_lines(reply)]


class ListingServer:
    """Serves the trimmed raw listing a page at a time, as TodayTix pages it, and counts the requests."""

    def __init__(self, page_size: int, status: int = 200) -> None:
        self.page_size, self.status = page_size, status
        self.offsets: list[int] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        self.offsets.append(offset)
        if self.status != 200:
            return httpx.Response(self.status)
        products = RAW_LISTING["data"]
        return httpx.Response(200, json={"data": products[offset : offset + self.page_size], "pagination": {"total": len(products)}})

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)


def test_only_shows_at_a_theater_are_kept_with_todaytix_labels_and_the_tier_tags_taken_out() -> None:
    shows = {show.name: show for product in RAW_LISTING["data"] if (show := show_from_product(product)) is not None}
    assert {"Private Lives", "Second Stage 2026/27 Subscriptions", "The Museum of Broadway"}.isdisjoint(shows)  # no theater, or an attraction
    wicked = shows["Wicked"]
    assert (wicked.tier, wicked.category, wicked.venue, wicked.end_date) == (Tier.BROADWAY, "Musicals", "Gershwin Theatre", None)  # endDate "null"
    assert "Broadway" not in wicked.tags and "Family / Kid-friendly" in wicked.tags
    assert shows["Midnight"].tier == Tier.OFF_BROADWAY
    assert shows["Montauk"].start_date is None  # listed at a theater before its first preview is announced


async def test_the_refresh_reads_every_page_and_writes_the_snapshot_in_one_piece(tmp_path: Path) -> None:
    server = ListingServer(page_size=8)
    settings = BroadwaySettings(snapshot_path=tmp_path / "broadway.json")
    snapshot = await refresh_broadway_snapshot(settings, server.transport)
    assert server.offsets == [0, 8, 16]
    assert read_snapshot(settings.snapshot_path, BroadwaySnapshot) == snapshot
    assert [path.name for path in tmp_path.iterdir()] == ["broadway.json"]


async def test_a_failed_refresh_keeps_the_last_snapshot(tmp_path: Path) -> None:
    settings = BroadwaySettings(snapshot_path=tmp_path / "broadway.json")
    await refresh_broadway_snapshot(settings, ListingServer(page_size=50).transport)
    kept = settings.snapshot_path.read_bytes()
    with pytest.raises(TodayTixUnavailable, match="503"):
        await refresh_broadway_snapshot(settings, ListingServer(page_size=50, status=503).transport)
    assert settings.snapshot_path.read_bytes() == kept


def test_a_missing_or_unreadable_snapshot_is_reported_as_missing(tmp_path: Path) -> None:
    with pytest.raises(SnapshotMissing, match="not been written"):
        read_snapshot(tmp_path / "broadway.json", BroadwaySnapshot)
    (tmp_path / "broadway.json").write_text('{"shows": "not a list"}')
    with pytest.raises(SnapshotMissing, match="does not read as a BroadwaySnapshot"):
        read_snapshot(tmp_path / "broadway.json", BroadwaySnapshot)


async def test_by_default_the_most_viewed_broadway_shows_running_now_horror_included() -> None:
    reply = await ask()
    assert reply.startswith("Broadway shows running now, most viewed on TodayTix first (10 of 32):")
    assert listed_names(reply)[:3] == ["The Rocky Horror Show", "Paranormal Activity", "& Juliet"]
    assert (
        "1. The Rocky Horror Show | musical | Comedy, Horror, Sci Fi / Fantasy, Revival | at Studio 54 | from $62 | 23,896 recent views | audience score 94 from 4,336 reviews | TodayTix lottery"
        in reply
    )


async def test_off_broadway_and_both_tiers_label_each_show_only_when_both_are_asked_for() -> None:
    off_broadway = await ask(venue_tier="off_broadway")
    assert listed_names(off_broadway)[0] == "Midnight" and "Off-Broadway |" not in off_broadway
    both = show_lines(await ask(venue_tier="both", limit=25))
    assert any("| Off-Broadway |" in line for line in both) and any("| Broadway |" in line for line in both)


async def test_each_order_puts_the_largest_first_and_shows_without_a_score_last() -> None:
    by_score = await ask(show_type="musical", sort_by="audience_score", limit=25)
    scores = [int(match.group(1)) if (match := re.search(r"audience score (\d+)", line)) else -1 for line in show_lines(by_score)]
    assert scores == sorted(scores, reverse=True) and scores[0] > 0
    assert all(" | musical | " in line for line in show_lines(by_score))
    by_reviews = await ask(sort_by="reviews_count", limit=3)
    assert listed_names(by_reviews) == ["Wicked", "The Book of Mormon", "Hamilton"]
    assert "audience score 94 from 27,162 reviews" in show_lines(by_reviews)[0] and "recent views" not in by_reviews


async def test_genre_price_and_deal_filters_keep_only_the_shows_that_fit() -> None:
    horror = await ask(genre="horror", venue_tier="both")
    assert "The Rocky Horror Show" in listed_names(horror) and "genre horror" in horror.split("\n")[0]
    cheap = show_lines(await ask(max_price=80, limit=25))
    assert cheap and all(float(re.search(r"from \$(\d+)", line).group(1)) <= 80 for line in cheap)
    lottery = show_lines(await ask(ticket_deal="lottery", venue_tier="both", limit=25))
    assert lottery and all("lottery" in line for line in lottery)


async def test_upcoming_lists_shows_that_have_not_started_with_their_first_date() -> None:
    reply = await ask(timing="upcoming", limit=25)
    assert reply.startswith("Broadway shows not started yet")
    assert any(line.startswith(f"{rank}. Evita") and "starts February 27, 2027" in line for rank, line in enumerate(show_lines(reply), start=1))


async def test_no_match_says_so_and_the_limit_is_held_to_a_spoken_list() -> None:
    assert (await ask(genre="holiday", max_price=1)).startswith("No Broadway shows running now, genre holiday, tickets from $1 or less on TodayTix. Tell the user")
    assert len(show_lines(await ask(venue_tier="both", limit=100))) == 25


async def test_no_snapshot_and_an_old_snapshot_are_said_plainly(tmp_path: Path) -> None:
    assert await ask(BroadwaySettings(snapshot_path=tmp_path / "missing.json")) == NO_SNAPSHOT_MESSAGE
    old = BroadwaySnapshot(refreshed_at=datetime(2026, 10, 1, 12, tzinfo=UTC), shows=read_snapshot(BROADWAY_SNAPSHOT_PATH, BroadwaySnapshot).shows)
    write_snapshot(tmp_path / "old.json", old)
    reply = await ask(BroadwaySettings(snapshot_path=tmp_path / "old.json", today=RECORDED_ON))
    assert reply.endswith("These listings were last refreshed 24 days ago, on October 1; tell the user they may be out of date.")
    assert "refreshed" not in await ask(recorded_settings(today=RECORDED_ON + timedelta(days=3)))


def test_every_genre_choice_stands_for_one_todaytix_tag() -> None:
    assert set(get_args(Genre)) - {""} == set(GENRE_TAGS)


def test_settings_come_from_broadway_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROADWAY_SNAPSHOT_PATH", "/tmp/listings/broadway.json")
    monkeypatch.setenv("BROADWAY_TODAY", "2026-10-25")
    monkeypatch.setenv("BROADWAY_MAX_WORDS", "")
    settings = broadway_settings_from_environment()
    assert (settings.snapshot_path, settings.today, settings.max_words) == (Path("/tmp/listings/broadway.json"), RECORDED_ON, BroadwaySettings().max_words)


def test_the_shows_rule_fires_on_theater_questions_and_not_on_the_street() -> None:
    for shows in ("What musicals are on Broadway right now?", "Anything good off-Broadway this week?", "Which Broadway shows have a lottery?", "What should I see on Broadway?"):
        assert rule_route(shows).tool_routes == [Route.SHOWS], shows
    for street in ("What's the best pizza on Broadway?", "How do I get to Broadway and 42nd street?"):
        assert rule_route(street) is None, street


def test_a_shows_question_gets_the_shows_directive_and_is_searched_when_the_server_has_no_listings() -> None:
    decision = RouteDecision(route=Route.SHOWS, source="rule")
    assert directive_for(decision) == SHOWS_DIRECTIVE.rstrip()
    assert route_to_offered_tools(decision, [ToolSpec(name="search_and_read", description="", input_schema={})]).route == Route.SEARCH


def test_the_listings_get_their_own_filler_line_and_it_is_stripped_from_replays() -> None:
    policy = AgentPolicy()
    assert filler_for(next(iter(SHOWS_TOOL_NAMES)), policy) in DEFAULT_SHOWS_FILLER_PHRASES
    assert set(DEFAULT_SHOWS_FILLER_PHRASES) <= set(policy.every_filler_phrase)


async def test_the_refresh_command_tries_every_source_and_names_the_ones_that_failed() -> None:
    async def fails() -> str:
        raise TodayTixUnavailable("TodayTix answered 503")

    async def succeeds() -> str:
        return "12 shows"

    assert await failed_refreshes({"broadway": fails, "movies": succeeds}) == ["broadway"]
