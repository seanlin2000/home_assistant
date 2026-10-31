"""movies_showing, movie_details, and the nightly Fandango refresh behind them: which theaters count as Manhattan, one entry per movie across
theaters and days, the session Fandango asks for and the snapshot kept when it fails, each movie's scores read nightly and its page read once, every
filter and order the tools offer, this week and coming up, horror left out unless asked for, the replies when nothing matches or there is no snapshot,
and the router, filler, and refresh command around them. The listings are the benchmark's own (benchmark/fixtures/movies/movies.json, 60 days from
2026-10-25); tests/fixtures/fandango_theaters.json is a trimmed copy of two of its raw days, and tests/fixtures/fandango_movie_details.json two
movies' trimmed pages and three movies' scores."""

import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, get_args

import httpx
import pytest
from mcp.server.mcpserver import MCPServer

from assistant_core.agent_loop import filler_for
from assistant_core.models import DEFAULT_MOVIES_FILLER_PHRASES, MOVIES_TOOL_NAMES, AgentPolicy, Route, RouteDecision, ToolCall, ToolSpec
from assistant_core.router import MOVIES_DIRECTIVE, directive_for, route_to_offered_tools, rule_route
from assistant_core.tools import McpToolBox
from benchmark.mcp_process import MOVIES_RECORDED_ON, MOVIES_SNAPSHOT_PATH
from movies_mcp.fandango import FandangoUnavailable, refresh_movies_snapshot
from movies_mcp.movies import GENRE_LABELS, MovieGenre, MoviesSnapshot, RottenTomatoesScores
from movies_mcp.register import MOVIE_DETAILS_TOOL_NAME, MOVIES_TOOL_NAME, NO_SNAPSHOT_MESSAGE, register_movies_tools
from movies_mcp.settings import MoviesSettings, movies_settings_from_environment
from utils.snapshot_utils import read_snapshot, write_snapshot

RECORDED_ON = date.fromisoformat(MOVIES_RECORDED_ON)
RAW_DAYS = json.loads(Path("tests/fixtures/fandango_theaters.json").read_text())
MOVIE_DETAILS = json.loads(Path("tests/fixtures/fandango_movie_details.json").read_text())
MOVIE_LINE = re.compile(r"^\d+\. ")


async def resolve_public(host: str) -> list[str]:
    return ["93.184.216.34"]


def recorded_settings(today: date = RECORDED_ON) -> MoviesSettings:
    return MoviesSettings(snapshot_path=MOVIES_SNAPSHOT_PATH, today=today)


async def ask(settings: MoviesSettings | None = None, **arguments: Any) -> str:
    return await call_tool(MOVIES_TOOL_NAME, settings or recorded_settings(), arguments)


async def ask_details(title: str) -> str:
    return await call_tool(MOVIE_DETAILS_TOOL_NAME, recorded_settings(), {"title": title})


async def call_tool(name: str, settings: MoviesSettings, arguments: dict[str, Any]) -> str:
    server = MCPServer("test")
    register_movies_tools(server, settings)
    async with McpToolBox(server) as toolbox:
        return await toolbox.call(ToolCall(id="1", name=name, arguments=arguments))


def movie_lines(reply: str) -> list[str]:
    return [line for line in reply.split("\n") if MOVIE_LINE.match(line)]


def listed_titles(reply: str) -> list[str]:
    return [MOVIE_LINE.sub("", line).split(" | ")[0] for line in movie_lines(reply)]


class FandangoServer:
    """Serves the zip-code page, the trimmed raw days a page at a time, and the scores and pages of the movies in the details fixture, as Fandango
    does, and records each request. Every other movie's scores and page are not found."""

    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith("_movietimes"):
            return httpx.Response(200, text="<html></html>")
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "FORBIDDEN", "errorMessage": "Session expired or invalid token"})
        if path.startswith("/napi/fanAndCriticRatings/"):
            scores = MOVIE_DETAILS["ratings"].get(path.rsplit("/", 1)[1])
            return httpx.Response(200, json=scores) if scores else httpx.Response(404)
        if path.endswith("/movie-overview"):
            page = MOVIE_DETAILS["pages"].get(path)
            return httpx.Response(200, text=page) if page else httpx.Response(404)
        day, page_number = request.url.params["date"], int(request.url.params["page"])
        return httpx.Response(200, json=RAW_DAYS.get(day, [{"theaters": [], "pagination": {"totalPages": 1}}])[page_number - 1])

    def paths_requested(self, prefix: str) -> list[str]:
        return [request.url.path for request in self.requests if request.url.path.startswith(prefix)]

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)


def fixture_settings(tmp_path: Path) -> MoviesSettings:
    """Two of the raw days, the 25th and the 30th, read as a week that starts on the 25th."""
    return MoviesSettings(snapshot_path=tmp_path / "movies.json", today=RECORDED_ON, days=6, seconds_between_requests=0)


async def test_the_refresh_opens_the_zip_page_first_then_reads_every_page_of_every_day(tmp_path: Path) -> None:
    server = FandangoServer()
    await refresh_movies_snapshot(fixture_settings(tmp_path), server.transport, resolve_public)
    assert server.requests[0].url.path == "/10036_movietimes"
    listing_requests = [request for request in server.requests if request.url.path == "/napi/theaterswithshowtimes"]
    assert [(request.url.params["date"], request.url.params["page"]) for request in listing_requests[:3]] == [("2026-10-25", "1"), ("2026-10-25", "2"), ("2026-10-26", "1")]
    assert server.requests[1 : len(listing_requests) + 1] == listing_requests  # the listing first, then each movie's details
    assert all(request.headers["referer"] == "https://www.fandango.com/10036_movietimes" for request in server.requests[1:])
    assert [path.name for path in tmp_path.iterdir()] == ["movies.json"]


async def test_only_manhattan_theaters_are_kept_and_each_movie_once_across_theaters_and_days(tmp_path: Path) -> None:
    snapshot = await refresh_movies_snapshot(fixture_settings(tmp_path), FandangoServer().transport, resolve_public)
    assert "AMC Newport Centre 11" not in snapshot.theaters and "Regal UA Kaufman Astoria" not in snapshot.theaters  # Jersey City, Astoria
    assert "Cross County Multiplex Cinemas" not in snapshot.theaters  # Yonkers, 10704: a 10 zip code that is not Manhattan
    assert "Quad Cinema" in snapshot.theaters and "New Plaza Cinema" in snapshot.theaters  # open, with nothing posted on some days
    movies = {movie.title: movie for movie in snapshot.movies}
    assert len(movies) == len(snapshot.movies) and "Clayface (2026)" not in movies  # the year Fandango adds is taken off
    clayface = movies["Clayface"]
    assert (clayface.rating, clayface.runtime_minutes, clayface.release_date) == ("R", 108, date(2026, 10, 23))
    assert "Horror" in clayface.genres and set(clayface.theaters) == {"AMC Empire 25", "Regal Times Square"}
    assert (clayface.fandango_id, clayface.page_path) == (244768, "/clayface-2026-244768/movie-overview")
    assert movies["Wild Horse Nine"].first_showing == date(2026, 10, 30) and set(movies["Wild Horse Nine"].theaters.values()) == {date(2026, 10, 30)}
    assert (snapshot.first_day, snapshot.last_day) == (date(2026, 10, 25), date(2026, 10, 30))


async def test_each_movie_gets_its_scores_and_page_and_a_page_is_read_only_the_first_night(tmp_path: Path) -> None:
    settings = fixture_settings(tmp_path)
    server = FandangoServer()
    snapshot = await refresh_movies_snapshot(settings, server.transport, resolve_public)
    movies = {movie.title: movie for movie in snapshot.movies}
    clayface = movies["Clayface"]
    assert clayface.scores == RottenTomatoesScores(critics_score=75, audience_score=94, certified_fresh=True)
    assert clayface.page and clayface.page.directors == ["James Watkins"] and clayface.page.cast[:2] == ["Tom Rhys Harries", "Naomi Ackie"]
    assert "Executive Producer" not in str(clayface.page) and "Chantal Nong" not in clayface.page.cast  # the crew after the actors is left out
    assert clayface.page.description.startswith('"Clayface" unravels one man\'s horrifying descent')
    without_details = [movie for movie in snapshot.movies if movie.fandango_id not in {244768, 247346}]
    assert without_details and all(movie.scores is None and movie.page is None for movie in without_details)  # not found: kept without them
    assert len(server.paths_requested("/napi/fanAndCriticRatings/")) == len(movie_pages_requested(server)) == len(snapshot.movies)
    next_night = FandangoServer()
    tomorrow = await refresh_movies_snapshot(settings, next_night.transport, resolve_public)
    assert len(next_night.paths_requested("/napi/fanAndCriticRatings/")) == len(snapshot.movies)  # scores every night
    assert set(movie_pages_requested(next_night)) == {movie.page_path for movie in without_details}  # only the pages not read yet
    assert {movie.title: movie.page for movie in tomorrow.movies}["Clayface"] == clayface.page


def movie_pages_requested(server: FandangoServer) -> list[str]:
    return [path for path in server.paths_requested("/") if path.endswith("/movie-overview")]


class RedirectingFandango(FandangoServer):
    """Fandango that first sends the zip-code page somewhere else, then serves as usual."""

    def __init__(self, location: str) -> None:
        super().__init__()
        self.location = location

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("_movietimes") and "moved" not in request.url.params:
            self.requests.append(request)
            return httpx.Response(302, headers={"location": self.location})
        return super().handle(request)


async def test_a_redirect_within_fandango_is_followed(tmp_path: Path) -> None:
    server = RedirectingFandango(location="?moved=1")
    await refresh_movies_snapshot(fixture_settings(tmp_path), server.transport, resolve_public)

    assert sum(request.url.path.endswith("_movietimes") for request in server.requests) == 2


async def test_a_redirect_to_the_home_network_fails_the_refresh_and_keeps_the_last_snapshot(tmp_path: Path) -> None:
    settings = fixture_settings(tmp_path)
    await refresh_movies_snapshot(settings, FandangoServer().transport, resolve_public)
    kept = settings.snapshot_path.read_bytes()
    with pytest.raises(FandangoUnavailable, match="must not read"):
        await refresh_movies_snapshot(settings, RedirectingFandango(location="http://192.168.1.1/admin").transport, resolve_public)
    assert settings.snapshot_path.read_bytes() == kept


async def test_a_refused_session_writes_nothing_and_keeps_the_last_snapshot(tmp_path: Path) -> None:
    settings = fixture_settings(tmp_path)
    await refresh_movies_snapshot(settings, FandangoServer().transport, resolve_public)
    kept = settings.snapshot_path.read_bytes()
    with pytest.raises(FandangoUnavailable, match="403"):
        await refresh_movies_snapshot(settings, FandangoServer(status=403).transport, resolve_public)
    assert settings.snapshot_path.read_bytes() == kept


async def test_by_default_the_widest_releases_this_week_horror_left_out_and_counted() -> None:
    reply = await ask()
    assert reply.split("\n")[0] == ("Movies at Manhattan theaters, October 25 to 31, showing at the most theaters first (10 of 81); 37 horror movies left out, which include_horror=true lists:")
    assert movie_lines(reply)[0] == ("1. You Can See Everything | Documentary | rated R | 2 hours 54 minutes | Rotten Tomatoes: critics 98%, Certified Fresh, audience 96% | playing at 17 theaters")
    assert "Clayface" not in reply
    with_horror = await ask(include_horror=True, limit=3)
    assert listed_titles(with_horror) == ["You Can See Everything", "Clayface", "Street Fighter"] and "left out" not in with_horror


async def test_three_theaters_or_fewer_are_named_and_early_showings_are_said() -> None:
    lines = movie_lines(await ask(genre="animation"))
    assert lines[1].endswith("| at AMC 34th Street 14, AMC Empire 25, AMC Magic Johnson Harlem 9")
    assert lines[0].startswith("1. Wildwood | Action/Adventure, Animation, Sci-Fi/Fantasy |") and lines[0].endswith("| playing at 12 theaters")  # Animated is Animation
    newest = movie_lines(await ask(sort_by="release_date", limit=2))
    assert newest[0].endswith("| playing at 9 theaters | opens November 6, early showings from October 30")
    assert newest[1].endswith("| at AMC Lincoln Square 13 | opens November 6, early showings now")


async def test_a_title_shows_horror_and_every_theater_and_a_missing_title_says_so() -> None:
    clayface = movie_lines(await ask(title="clayface"))
    assert len(clayface) == 1 and clayface[0].count("AMC") == 8 and "Horror" in clayface[0]
    assert (await ask(title="Dune")) == (
        'No movie titled like "Dune" is showing at Manhattan theaters on Fandango, October 25 to 31. Tell the user it is not in these theaters this week;'
        ' when="coming_up" says whether it opens later.'
    )


async def test_coming_up_lists_what_starts_after_this_week_soonest_first_and_finds_a_title_there() -> None:
    soonest = await ask(when="coming_up", sort_by="release_date", limit=3)
    assert soonest.startswith("Movies at Manhattan theaters, first showing after October 31, with tickets on sale through December 23, soonest first (3 of 168)")
    assert listed_titles(soonest) == ["V for Vendetta 20th Anniversary", "The Irregular at Magic High School THE MOVIE -Yotsuba Succession Arc-", "JIMMY"]
    assert movie_lines(soonest)[2].endswith("| at AMC Empire 25, AMC Kips Bay 15 | opens November 6, early showings from November 1")
    dune = movie_lines(await ask(when="coming_up", title="Dune"))
    assert dune[0].startswith("1. Dune: Part Three |") and dune[0].endswith("Village East By Angelika | opens December 18, early showings from December 17")
    this_week = set(listed_titles(await ask(limit=25, include_horror=True)))
    assert not this_week & set(listed_titles(await ask(when="coming_up", limit=25, include_horror=True)))


async def test_the_score_orders_put_the_best_reviewed_first_and_movies_without_a_score_last() -> None:
    critics = await ask(sort_by="critics_score", limit=2)
    assert "best reviewed by critics on Rotten Tomatoes first" in critics.split("\n")[0]
    assert listed_titles(critics) == ["Wildwood", "Making Marie Antoinette"]  # 100% each; Wildwood at more theaters
    audience = [int(score) for score in re.findall(r"audience (\d+)%", await ask(sort_by="audience_score", limit=25, include_horror=True))]
    assert len(audience) == 25 and audience == sorted(audience, reverse=True)
    action = movie_lines(await ask(when="coming_up", sort_by="critics_score", genre="action", limit=25))
    scored = ["critics" in line for line in action]
    assert scored == sorted(scored, reverse=True) and scored.count(True) == 9 < len(action)  # every scored movie before every unscored one


async def test_details_say_what_one_movie_is_about_who_made_it_and_where_it_opens() -> None:
    clayface = (await ask_details("clayface")).split("\n")
    assert clayface[0] == "Clayface, from Fandango:"
    assert "| directed by James Watkins | starring Tom Rhys Harries, Naomi Ackie, David Dencik, Max Minghella, Eddie Marsan |" in clayface[1]
    assert clayface[1].endswith("| Rotten Tomatoes: critics 75%, Certified Fresh, audience 94% | showing now")
    assert clayface[2].startswith("Showing now at AMC 34th Street 14, AMC 84th Street 6,") and clayface[3].startswith('About: "Clayface" unravels')
    avengers = (await ask_details("the new avengers doomsday movie")).split("\n")
    assert avengers[0] == "Avengers: Doomsday, from Fandango:" and avengers[1].endswith("| opens December 18, early showings from December 17")
    assert avengers[2].startswith("Showing from December 17 at AMC 19th St. East 6, AMC 34th Street 14,") and avengers[2].count("from December 17") == 1


async def test_details_ask_which_movie_when_several_match_and_say_when_none_or_no_synopsis_does() -> None:
    rocky = await ask_details("rocky")
    assert rocky.split("\n") == [
        '3 movies on Fandango\'s Manhattan listings match "rocky". Ask the user which one they mean:',
        "1. Rocky 50th Anniversary | opens November 7",
        "2. I Play Rocky | opens November 6, early showings now",
        "3. The Rocky Horror Picture Show | showings from October 30",
    ]
    assert (await ask_details("Your Name")).startswith('No movie on Fandango\'s Manhattan listings through December 23 matches "Your Name", so no Manhattan theater')
    snapshot = read_snapshot(MOVIES_SNAPSHOT_PATH, MoviesSnapshot)
    no_synopsis = next(movie for movie in snapshot.movies if movie.page and not movie.page.description)
    assert (await ask_details(no_synopsis.title)).endswith("Fandango has no synopsis of this movie; if the user wants to know what it is about, search the web.")


async def test_a_theater_lists_what_it_shows_and_an_unknown_one_lists_the_theaters() -> None:
    angelika = await ask(theater="Angelika", limit=3)
    assert angelika.startswith("Movies at Cinema 123 by Angelika or Village East By Angelika or Angelika Film Center & Cafe, October 25 to 31")
    assert movie_lines(angelika)[0].endswith("| at Cinema 123 by Angelika, Village East By Angelika")
    unknown = await ask(theater="Film Forum")
    assert unknown.startswith('No Manhattan theater on Fandango matches "Film Forum". The theaters it lists are: AMC 19th St. East 6,') and "Quad Cinema" in unknown


async def test_horror_alone_and_a_genre_with_nothing_left_say_so() -> None:
    horror = await ask(genre="horror", limit=3)
    assert horror.startswith("Horror movies at Manhattan theaters, October 25 to 31, showing at the most theaters first (3 of 37):")
    assert listed_titles(horror) == ["Clayface", "Other Mommy", "Resident Evil"]
    assert (await ask(genre="war", theater="Paris Theater")).startswith("No war movies at Paris Theater, October 25 to 31 on Fandango. Tell the user, and offer to drop a filter.")


async def test_the_limit_is_held_to_a_spoken_list_inside_the_word_budget() -> None:
    reply = await ask(limit=100, include_horror=True)
    assert len(movie_lines(reply)) == 25 and len(reply.split()) <= MoviesSettings().max_words


async def test_no_snapshot_and_an_old_snapshot_are_said_plainly(tmp_path: Path) -> None:
    assert await ask(MoviesSettings(snapshot_path=tmp_path / "missing.json")) == NO_SNAPSHOT_MESSAGE
    snapshot = read_snapshot(MOVIES_SNAPSHOT_PATH, MoviesSnapshot)
    write_snapshot(tmp_path / "old.json", snapshot.model_copy(update={"refreshed_at": datetime(2026, 10, 20, 12, tzinfo=UTC)}))
    reply = await ask(MoviesSettings(snapshot_path=tmp_path / "old.json", today=RECORDED_ON))
    assert reply.endswith("These listings were last refreshed 5 days ago, on October 20; tell the user they may be out of date.")
    assert "refreshed" not in await ask(recorded_settings(today=RECORDED_ON + timedelta(days=3)))


def test_every_genre_choice_names_fandango_genres_and_every_fandango_genre_has_a_choice() -> None:
    assert set(get_args(MovieGenre)) - {""} == set(GENRE_LABELS)
    listed = {genre for movie in read_snapshot(MOVIES_SNAPSHOT_PATH, MoviesSnapshot).movies for genre in movie.genres}
    assert listed == {label for labels in GENRE_LABELS.values() for label in labels}


def test_settings_come_from_movies_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOVIES_SNAPSHOT_PATH", "/tmp/listings/movies.json")
    monkeypatch.setenv("MOVIES_TODAY", "2026-10-25")
    monkeypatch.setenv("MOVIES_MAX_WORDS", "")
    settings = movies_settings_from_environment()
    assert (settings.snapshot_path, settings.today, settings.max_words) == (Path("/tmp/listings/movies.json"), RECORDED_ON, MoviesSettings().max_words)


def test_the_movies_rule_fires_on_what_is_showing_and_not_on_trivia_or_streaming() -> None:
    for movies in (
        "What movies are playing this weekend?",
        "Any good films in theaters right now?",
        "What's playing at the Angelika?",
        "What's showing at AMC Empire tonight?",
        "What movies are coming soon to theaters?",
    ):
        assert rule_route(movies).tool_routes == [Route.MOVIES], movies
    for other in ("What was Warren Beatty's first movie?", "Who directed the film Jaws?", "What good movies are streaming on Netflix this weekend?", "Is the AMC stock price up today?"):
        assert rule_route(other) is None or Route.MOVIES not in rule_route(other).tool_routes, other


def test_a_movies_question_gets_the_movies_directive_and_is_searched_when_the_server_has_no_listings() -> None:
    decision = RouteDecision(route=Route.MOVIES, source="rule")
    assert directive_for(decision) == MOVIES_DIRECTIVE.rstrip() and MOVIES_TOOL_NAME in MOVIES_DIRECTIVE
    assert route_to_offered_tools(decision, [ToolSpec(name="search_and_read", description="", input_schema={})]).route == Route.SEARCH


def test_movies_get_their_own_filler_line_and_it_is_stripped_from_replays() -> None:
    policy = AgentPolicy()
    assert MOVIES_TOOL_NAMES == {MOVIES_TOOL_NAME, MOVIE_DETAILS_TOOL_NAME}
    assert filler_for(MOVIES_TOOL_NAME, policy) in DEFAULT_MOVIES_FILLER_PHRASES
    assert set(DEFAULT_MOVIES_FILLER_PHRASES) <= set(policy.every_filler_phrase)
