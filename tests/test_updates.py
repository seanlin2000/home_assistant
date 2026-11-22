"""The updates tool: its seven sections in order, which ones a call shows (skip, include, and the default-off setting the server applies on every
call), the Warriors' game and next game, popular movies new since last week, anime with newly announced ones marked, Broadway previews and closings,
a section that cannot be read, and the route, directive and filler around it.

The listings are the benchmark's own (movies and Broadway from 2026-10-25, newsletters from 2026-11-16). Last week's movie listings are the same
snapshot moved back a week, less one popular movie and one anime movie, so both read as new. ESPN's answers were recorded on 2026-11-21 for the
morning of 2026-11-20 (tests/fixtures/espn_warriors_2026-11-20/), after the Warriors lost at Memphis the night before."""

import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from mcp.server.mcpserver import MCPServer

from assistant_core.agent_loop import filler_for
from assistant_core.models import DEFAULT_UPDATES_FILLER_PHRASES, UPDATES_TOOL_NAMES, AgentPolicy, Route, RouteDecision, ToolCall, ToolSpec
from assistant_core.router import UPDATES_DIRECTIVE, directive_for, route_to_offered_tools, rule_route
from assistant_core.tools import McpToolBox, find_tool_spec
from assistant_mcp.server import build_server
from benchmark.mcp_process import BROADWAY_RECORDED_ON, BROADWAY_SNAPSHOT_PATH, MOVIES_RECORDED_ON, MOVIES_SNAPSHOT_PATH, NEWSLETTERS_DIR, NEWSLETTERS_RECORDED_ON
from broadway_mcp.settings import BroadwaySettings
from movies_mcp.archive import archive_snapshot
from movies_mcp.movies import MoviesSnapshot
from movies_mcp.settings import MoviesSettings
from newsletters_mcp.settings import NewslettersSettings
from sports_mcp.answers import TeamUpdate
from sports_mcp.espn_records import Game, TeamLine
from sports_mcp.fixtures import FixtureTransport
from sports_mcp.settings import SportsSettings
from updates_mcp.blocks import UNAVAILABLE_MESSAGE, UpdateSources, recent_game_text
from updates_mcp.register import UPDATES_TOOL_NAME, register_updates_tools
from updates_mcp.sections import SECTIONS, shown_sections
from updates_mcp.settings import UpdatesSettings, updates_settings_from_environment
from utils.snapshot_utils import read_snapshot
from web_search_mcp.settings import SearchSettings

MOVIES_DAY = date.fromisoformat(MOVIES_RECORDED_ON)
WARRIORS_MORNING = date(2026, 11, 20)
WARRIORS_FIXTURES = Path("tests/fixtures/espn_warriors_2026-11-20")
DROPPED_POPULAR_MOVIE = 246438  # Wildwood, at 5 or more theaters with a critics score over 70 on 2026-10-25
DROPPED_ANIME_MOVIE = 247616  # Crunchyroll Anime Nights: Dive In Wonderland, from 2026-11-16
WEEK = timedelta(days=7)


class RecordedEspn(httpx.AsyncBaseTransport):
    """The Warriors recordings, with a day that was not recorded answering as a scoreboard without games, as ESPN does on a day off."""

    def __init__(self) -> None:
        self.recordings = FixtureTransport(WARRIORS_FIXTURES)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self.recordings.handle_async_request(request)
        if response.status_code != 200 and request.url.path.endswith("/scoreboard"):
            return httpx.Response(200, json={"events": []}, request=request)
        return response


def moved_back_a_week(snapshot: MoviesSnapshot, dropped: set[int]) -> MoviesSnapshot:
    movies = [movie.model_copy(update={"theaters": {theater: day - WEEK for theater, day in movie.theaters.items()}}) for movie in snapshot.movies if movie.fandango_id not in dropped]
    return snapshot.model_copy(update={"first_day": snapshot.first_day - WEEK, "last_day": snapshot.last_day - WEEK, "movies": movies})


def sources_in(tmp_path: Path, archived_week_ago: bool = True, sports_today: date = WARRIORS_MORNING) -> UpdateSources:
    newsletters_dir = tmp_path / "newsletters"
    shutil.copytree(NEWSLETTERS_DIR, newsletters_dir)
    movies = MoviesSettings(snapshot_path=MOVIES_SNAPSHOT_PATH, today=MOVIES_DAY, archive_dir=tmp_path / "movies_archive")
    if archived_week_ago:
        archive_snapshot(movies, moved_back_a_week(read_snapshot(MOVIES_SNAPSHOT_PATH, MoviesSnapshot), {DROPPED_POPULAR_MOVIE, DROPPED_ANIME_MOVIE}))
    return UpdateSources(
        NewslettersSettings(dir=newsletters_dir, today=date.fromisoformat(NEWSLETTERS_RECORDED_ON)),
        SportsSettings(cache_dir=None, today=sports_today),
        movies,
        BroadwaySettings(snapshot_path=BROADWAY_SNAPSHOT_PATH, today=date.fromisoformat(BROADWAY_RECORDED_ON)),
        RecordedEspn(),
    )


async def ask(sources: UpdateSources, settings: UpdatesSettings | None = None, **arguments: Any) -> str:
    server = MCPServer("test")
    register_updates_tools(server, settings or UpdatesSettings(), sources)
    async with McpToolBox(server) as toolbox:
        return await toolbox.call(ToolCall(id="1", name=UPDATES_TOOL_NAME, arguments=arguments))


async def tool_spec(settings: UpdatesSettings, tmp_path: Path) -> ToolSpec:
    server = MCPServer("test")
    register_updates_tools(server, settings, sources_in(tmp_path, archived_week_ago=False))
    async with McpToolBox(server) as toolbox:
        spec = find_tool_spec(await toolbox.list_tools(), UPDATES_TOOL_NAME)
    assert spec is not None
    return spec


def first_lines(reply: str) -> list[str]:
    return [block.split("\n")[0] for block in reply.split("\n\n")]


async def test_by_default_every_section_but_broadway_closings_in_the_tools_order(tmp_path: Path) -> None:
    reply = await ask(sources_in(tmp_path))
    assert first_lines(reply) == [
        "Newsletters for Monday, November 16:",
        "Warriors game last night: Thu 2026-11-19 | Final | Golden State Warriors 98 at Memphis Grizzlies 126 | Top scorers: GS Charles Bassey 16; MEM Jaylen Wells 22",
        "Warriors next game: Sun 2026-11-22 | Sun, November 22nd at 8:30 PM EST | Boston Celtics at Golden State Warriors",
        "Popular movies new since October 18 (Rotten Tomatoes critics 70% or more, at 5 theaters or more):",
        'Anime movies coming to Manhattan theaters in the next two months ("newly announced": not listed on October 18):',
        "Broadway shows starting previews in the next two months:",
    ]


async def test_newsletters_give_each_publication_and_headline_without_sections(tmp_path: Path) -> None:
    newsletters = (await ask(sources_in(tmp_path))).split("\n\n")[0].split("\n")
    assert len(newsletters) == 5
    assert all(line.startswith("- ") and ', "' in line and "Sections" not in line for line in newsletters[1:])


async def test_last_nights_game_comes_with_its_recap(tmp_path: Path) -> None:
    game = (await ask(sources_in(tmp_path))).split("\n\n")[1]
    assert game.split("\n")[1] == (
        "Recap: Grizzlies roll past short-handed Warriors 126-98 for a fifth straight win. Jaylen Wells had 22 points and Cedric Coward scored 19 to lead"
        " the Memphis Grizzlies to their fifth straight win on Thursday night, 126-98 over the short-handed Golden State Warriors."
    )


async def test_a_game_two_nights_ago_is_not_last_night(tmp_path: Path) -> None:
    reply = await ask(sources_in(tmp_path, sports_today=WARRIORS_MORNING + timedelta(days=1)), skip=["newsletters", "new_movies", "anime", "broadway_previews"])
    assert reply.split("\n\n")[0] == "Warriors game today or last night: none."


async def test_once_no_game_is_left_the_next_game_is_left_out(tmp_path: Path) -> None:
    reply = await ask(sources_in(tmp_path, sports_today=date(2027, 6, 30)), skip=["newsletters", "new_movies", "anime", "broadway_previews"])
    assert reply == "Warriors game today or last night: none."


def test_a_game_under_way_today_gives_its_score_and_no_recap() -> None:
    live = Game(
        event_id="1",
        day=WARRIORS_MORNING,
        state="in",
        status="5:12 - 3rd Quarter",
        home=TeamLine(name="Golden State Warriors", abbreviation="GS", score="71"),
        away=TeamLine(name="Boston Celtics", abbreviation="BOS", score="68"),
    )
    text = recent_game_text(TeamUpdate(recent_game=live, recap=None, next_game=None), WARRIORS_MORNING)
    assert text == "Warriors game today: Fri 2026-11-20 | 5:12 - 3rd Quarter | Boston Celtics 68 at Golden State Warriors 71"


async def test_new_popular_movies_are_the_ones_not_popular_a_week_ago(tmp_path: Path) -> None:
    movies = (await ask(sources_in(tmp_path), skip=["newsletters", "warriors", "anime", "broadway_previews"])).split("\n")
    assert movies[1:] == ["- Wildwood | Action/Adventure, Animation, Sci-Fi/Fantasy | Rotten Tomatoes: critics 100%, Certified Fresh, audience 97% | playing at 12 theaters"]


async def test_without_a_copy_from_before_today_nothing_is_called_new(tmp_path: Path) -> None:
    sources = sources_in(tmp_path, archived_week_ago=False)
    archive_snapshot(sources.movies, read_snapshot(MOVIES_SNAPSHOT_PATH, MoviesSnapshot))  # the first night: only today's copy
    reply = await ask(sources, skip=["newsletters", "warriors", "broadway_previews"])
    new_movies, anime = reply.split("\n\n")
    assert new_movies == "New popular movies: there are no earlier listings to compare with yet. Tell the user this part starts working within a week."
    assert anime == "Anime movies coming to Manhattan theaters in the next two months:\n- Crunchyroll Anime Nights: Dive In Wonderland | opens November 16"


async def test_anime_not_listed_a_week_ago_is_marked_newly_announced(tmp_path: Path) -> None:
    anime = (await ask(sources_in(tmp_path), skip=["newsletters", "warriors", "new_movies", "broadway_previews"])).split("\n")
    assert anime[1:] == ["- Crunchyroll Anime Nights: Dive In Wonderland | newly announced | opens November 16"]


async def test_broadway_previews_and_closings_are_two_sections_within_sixty_days(tmp_path: Path) -> None:
    reply = await ask(sources_in(tmp_path), skip=["newsletters", "warriors", "new_movies", "anime"], include=["broadway_closings"])
    previews, closings = reply.split("\n\n")
    assert [line.split(" | ")[0] for line in previews.split("\n")[1:]] == [
        "- Much Ado About Nothing",
        "- Here There Are Blueberries",
        "- It’s A Wonderful Life: A Live Radio Play",
        "- Galileo",
        "- Inter Alia",
        "- Now You See Me Live",
        "- Blue Man Group “A New Holiday Surprise”",
        "- Clifford Odets' Awake and Sing!",
    ]
    assert previews.split("\n")[1].endswith("| first preview October 31")
    assert closings.split("\n") == [
        "Broadway shows closing in the next two months:",
        "- School Girls; Or, The African Mean Girls Play | play | at Samuel J. Friedman Theatre | closes November 15",
        "- The Imaginary Invalid | play | Comedy, History, Satire, Classic | at Todd Haimes Theatre | closes November 22",
        "- Two Strangers (Carry a Cake Across New York) | musical | Romance | at Longacre Theatre | closes November 29",
    ]


@pytest.mark.parametrize(
    ("skip", "include", "shown"),
    [
        ([], [], ["newsletters", "warriors", "new_movies", "anime", "broadway_previews"]),
        (["anime"], [], ["newsletters", "warriors", "new_movies", "broadway_previews"]),
        ([], ["broadway_closings"], list(SECTIONS)),
        (["broadway_closings"], ["broadway_closings"], ["newsletters", "warriors", "new_movies", "anime", "broadway_previews"]),
        (["broadway_previews"], ["broadway_closings"], ["newsletters", "warriors", "new_movies", "anime", "broadway_closings"]),
    ],
)
def test_default_off_sections_stay_off_whatever_is_skipped_until_included(skip: list[str], include: list[str], shown: list[str]) -> None:
    assert shown_sections(skip, include, ["broadway_closings"]) == shown  # type: ignore[arg-type]


async def test_a_skip_list_from_the_model_never_brings_closings_back(tmp_path: Path) -> None:
    reply = await ask(sources_in(tmp_path), skip=["anime"])
    assert "Broadway shows closing" not in reply and "Anime movies" not in reply and "Broadway shows starting previews" in reply


async def test_the_description_follows_the_default_off_setting(tmp_path: Path) -> None:
    default = await tool_spec(UpdatesSettings(), tmp_path / "default")
    assert default.description == (
        "The user's updates, in this order: today's newsletters; the Warriors' game today or last night, with score and recap; their next game while the"
        " season lasts; good wide-release movies new since last week; anime movies coming in the next two months; Broadway shows starting previews in"
        " the next two months. Broadway closings only when asked for."
    )
    assert "(broadway_closings)" in str(default.input_schema["properties"]["include"])
    anime_off = await tool_spec(UpdatesSettings(default_off=["anime", "broadway_closings"]), tmp_path / "anime_off")
    assert anime_off.description.endswith("Anime movies and Broadway closings only when asked for.") and "anime movies coming" not in anime_off.description


async def test_a_section_that_cannot_be_read_says_so_and_the_rest_still_answer(tmp_path: Path) -> None:
    sources = sources_in(tmp_path)
    sources.broadway = BroadwaySettings(snapshot_path=tmp_path / "missing.json")
    reply = await ask(sources, skip=["newsletters", "warriors", "new_movies"])
    anime, previews = reply.split("\n\n")
    assert anime.startswith("Anime movies coming")
    assert previews == UNAVAILABLE_MESSAGE.format(title="Broadway previews")


async def test_skipping_everything_says_there_is_nothing_to_report(tmp_path: Path) -> None:
    assert await ask(sources_in(tmp_path), skip=list(SECTIONS)) == "Every section was skipped; tell the user there is nothing to report."


def test_default_off_comes_from_a_comma_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPDATES_DEFAULT_OFF", "anime, broadway_closings")
    assert updates_settings_from_environment().default_off == ["anime", "broadway_closings"]


async def test_the_tool_server_offers_updates() -> None:
    assert UPDATES_TOOL_NAME in {tool.name for tool in await build_server(SearchSettings()).list_tools()}


@pytest.mark.parametrize(
    "question",
    ["Any updates for me?", "Give me my updates, but skip Broadway.", "Catch me up", "My updates please, skip the anime and the Broadway closings", "What's new with me?"],
)
def test_a_request_for_updates_goes_to_the_updates_tool_alone(question: str) -> None:
    decision = rule_route(question)
    assert decision is not None and (decision.route, decision.also) == (Route.UPDATES, [])


@pytest.mark.parametrize("question", ["Any updates on the Warriors trade?", "Catch me up on the news", "What musicals are on Broadway right now?"])
def test_updates_on_one_topic_are_left_to_the_other_rules(question: str) -> None:
    decision = rule_route(question)
    assert decision is None or decision.route != Route.UPDATES


def test_updates_get_their_directive_and_filler_and_fall_back_to_search_without_the_tool() -> None:
    decision = RouteDecision(route=Route.UPDATES, source="rule")
    assert directive_for(decision) == UPDATES_DIRECTIVE.rstrip() and 'updates(skip=["broadway_previews"])' in UPDATES_DIRECTIVE
    assert route_to_offered_tools(decision, [ToolSpec(name="search_and_read", description="", input_schema={})]).route == Route.SEARCH
    assert UPDATES_TOOL_NAMES == {UPDATES_TOOL_NAME}
    assert filler_for(UPDATES_TOOL_NAME, AgentPolicy()) in DEFAULT_UPDATES_FILLER_PHRASES
    assert set(DEFAULT_UPDATES_FILLER_PHRASES) <= set(AgentPolicy().every_filler_phrase)
