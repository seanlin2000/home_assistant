"""The agent's tool server over streamable HTTP: search_and_read (what small models should use), web_search, fetch_page, the calculator tools, the home weather
forecast, Wikipedia lookups, NBA and NFL scores and statistics, Broadway and movie listings, and what people on Reddit say."""

import html
import re
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from assistant_core.models import REQUIRED_TOOL_NAMES
from broadway_mcp.register import register_broadway_tools
from broadway_mcp.settings import BroadwaySettings, broadway_settings_from_environment
from calculator_mcp.register import register_calculator_tools
from movies_mcp.register import register_movies_tools
from movies_mcp.settings import MoviesSettings, movies_settings_from_environment
from reddit_mcp.register import register_reddit_tools
from reddit_mcp.settings import RedditSettings, reddit_settings_from_environment
from sports_mcp.register import register_sports_tools
from sports_mcp.settings import SportsSettings, sports_settings_from_environment
from utils.http_access_utils import host_allowed, misdirected
from utils.text_utils import clip_to_words, word_count
from weather_mcp.register import register_weather_tools
from weather_mcp.settings import WeatherSettings, weather_settings_from_environment
from web_search_mcp.fixtures import FIXTURE_ROUTE, FixturePages, FixtureSearch, fixture_route
from web_search_mcp.page_extractor import PageExcerpt, PageExtractor
from web_search_mcp.page_failures import PageUnreadable
from web_search_mcp.query_cache import QueryCache
from web_search_mcp.search_engines import SearchEngine, configured_search
from web_search_mcp.searxng_client import SearchResult
from web_search_mcp.settings import SearchSettings, allowed_host_list, settings_from_environment
from web_search_mcp.url_guard import UnsafeUrl
from wikipedia_mcp.client import WikipediaClient
from wikipedia_mcp.register import register_wikipedia_tools
from wikipedia_mcp.settings import WikipediaSettings, wikipedia_settings_from_environment

HTML_TAG = re.compile(r"<[^>]+>")
NOT_FOUND_INSTRUCTION = "If these sources do not answer the question, say plainly that you could not find it."


def build_server(
    settings: SearchSettings,
    search: SearchEngine | None = None,
    extractor: PageExtractor | None = None,
    weather: WeatherSettings | None = None,
    wikipedia: WikipediaSettings | None = None,
    sports: SportsSettings | None = None,
    broadway: BroadwaySettings | None = None,
    movies: MoviesSettings | None = None,
    reddit: RedditSettings | None = None,
) -> MCPServer:
    cache = QueryCache(settings.cache_dir)
    wikipedia = wikipedia or WikipediaSettings()
    fixture_pages = FixturePages(Path(settings.fixtures_dir)) if settings.fixtures_dir else None
    search = search or configured_search(settings, cache)
    if fixture_pages:
        search = FixtureSearch(search, fixture_pages)
    extractor = extractor or PageExtractor(settings, cache, wikipedia=WikipediaClient(wikipedia, cache), fixture_pages=fixture_pages)
    server = MCPServer(
        "assistant-tools",
        instructions=(
            "Web search through Brave's API, falling back to a local SearXNG instance, Wikipedia articles, exact calculator tools, the forecast for home, NBA and NFL statistics from ESPN, what is playing on Broadway, what movies are showing in Manhattan, and what people on Reddit say. Prefer"
            " search_and_read for questions about the world and wikipedia_lookup for settled facts, lists, and records; use the calculator tools for any arithmetic,"
            " weather_forecast for the weather, and game_scores, box_score, team_roster, player_stats, and player_matchup for NBA and NFL scores, rosters, and statistics,"
            " broadway_shows for what is playing on Broadway and Off-Broadway, movies_showing and movie_details for what movies are showing in Manhattan theaters and what one is about,"
            " and reddit_search when the user asks what people on Reddit or a subreddit say."
        ),
    )

    @server.tool()
    async def search_and_read(query: str, time_range: str | None = None) -> str:
        """Search the web and read the top pages. Returns the ranked results, numbered, with the parts of each readable page that best match the query and the snippet of each page that could not be read, ready to synthesize an answer from. Use short keyword queries, e.g. "federal funds rate september 2026". time_range: optional "day", "week", "month", or "year" to keep only recent pages; use it for "latest" or "this week" questions."""
        results = await search.search(query, time_range)
        excerpts = await extractor.read_pages(results, query)
        return render_grounded_context(query, results, excerpts, settings.results_to_return)

    @server.tool()
    async def web_search(query: str, time_range: str | None = None) -> str:
        """Search the web and return only the ranked result list (title, URL, snippet) without reading the pages. Use when you want to pick which page to read with fetch_page. time_range: optional "day", "week", "month", or "year" to keep only recent pages; use it for "latest" or "this week" questions."""
        results = await search.search(query, time_range)
        return render_result_list(results[: settings.results_to_return])

    @server.tool()
    async def fetch_page(url: str) -> str:
        """Fetch one public web page and return its main text, trimmed to a readable length. Only public http(s) addresses are allowed."""
        try:
            text = await extractor.read_page(url)
        except UnsafeUrl as error:
            return f"Refused to fetch {url}: {error}. Only public web addresses can be read."
        except PageUnreadable as unreadable:
            return f"Could not read {url} ({unreadable.code}): {unreadable}."
        return clipped_with_note(text, settings.fetch_page_words)

    register_calculator_tools(server)
    register_weather_tools(server, weather or WeatherSettings(), cache)
    register_wikipedia_tools(server, wikipedia, cache)
    register_sports_tools(server, sports or SportsSettings(cache_dir=None))  # a server built without settings, as in tests, leaves the real cache alone
    register_broadway_tools(server, broadway or BroadwaySettings())
    register_movies_tools(server, movies or MoviesSettings())
    register_reddit_tools(server, reddit or RedditSettings(), search)
    register_operations_routes(server, allowed_host_list(settings))
    if fixture_pages:
        server.custom_route(FIXTURE_ROUTE, ["POST"])(fixture_route(fixture_pages))
    return server


def transport_security_for(settings: SearchSettings) -> TransportSecuritySettings | None:
    """When the server is bound to the LAN, only requests naming this machine in their Host header are served, and none that carry a browser
    Origin. That stops a web page from reaching the server through DNS rebinding. With no allow-list (localhost binds) the library's default applies.
    The library takes this on run() and streamable_http_app(), not on the constructor, so build_server's callers pass it themselves."""
    allowed_hosts = allowed_host_list(settings)
    if not allowed_hosts:
        return None
    return TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=allowed_hosts, allowed_origins=[])


def register_operations_routes(server: MCPServer, allowed_hosts: list[str]) -> None:
    """A plain HTTP route beside the MCP endpoint for the health check, which proves this server is ours by its tools (design doc 10)."""

    @server.custom_route("/healthz", ["GET"])
    async def healthz(request: Request) -> Response:
        if not host_allowed(request, allowed_hosts):
            return misdirected(request)
        names = sorted(tool.name for tool in await server.list_tools())
        missing = sorted(REQUIRED_TOOL_NAMES - set(names))
        return JSONResponse({"status": "ok" if not missing else "degraded", "tools": names, "missing": missing})


def clipped_with_note(text: str, word_limit: int) -> str:
    """The top of a page, saying where it was cut, so the model knows the rest exists rather than taking the top for the whole."""
    total_words = word_count(text)
    if total_words <= word_limit:
        return text
    return f"{clip_to_words(text, word_limit)}\n[The page continues: this is the first {word_limit:,} of its {total_words:,} words.]"


def render_result_list(results: list[SearchResult]) -> str:
    if not results:
        return "No results."
    lines = [f"[{index}] {result.title}\n    {result.url}\n    {result.snippet}" for index, result in enumerate(results, start=1)]
    return "\n".join(lines)


def render_grounded_context(query: str, results: list[SearchResult], excerpts: list[PageExcerpt], results_to_list: int) -> str:
    """Every result keeps its search rank, read or not: a page that could not be read (a video, a forum behind a login) often names the answer in its
    title or snippet, and the rank tells the model how far down the evidence sits."""
    if not results:
        return f'No search results for "{query}". Tell the user you could not find anything and answer from your own knowledge with that caveat.'
    if not excerpts:
        return f'Search for "{query}" returned results but none of the pages could be read. Snippets only:\n{render_result_list(results[:5])}'
    excerpts_by_url = {excerpt.url: excerpt for excerpt in excerpts}
    listed = [(rank, result) for rank, result in enumerate(results, start=1) if rank <= results_to_list or result.url in excerpts_by_url]
    sources = [read_source(rank, excerpts_by_url[result.url]) if result.url in excerpts_by_url else unread_source(rank, result) for rank, result in listed]
    header = f'Read {len(excerpts)} of {len(results)} results for "{query}".'
    return "\n\n".join([header, *sources, NOT_FOUND_INSTRUCTION])


def read_source(rank: int, excerpt: PageExcerpt) -> str:
    return f"[{rank}] {excerpt.title}\nURL: {excerpt.url}\n{excerpt.text}"


def unread_source(rank: int, result: SearchResult) -> str:
    return "\n".join(line for line in (f"[{rank}] {result.title} (not read)", plain_snippet(result.snippet)) if line)


def plain_snippet(snippet: str) -> str:
    """Engines return snippets with their own highlighting tags and HTML entities, such as "<b>Roy</b> &amp; Chrom"."""
    return " ".join(html.unescape(HTML_TAG.sub("", snippet)).split())


def main() -> None:
    settings = settings_from_environment()
    build_server(
        settings,
        weather=weather_settings_from_environment(),
        wikipedia=wikipedia_settings_from_environment(),
        sports=sports_settings_from_environment(),
        broadway=broadway_settings_from_environment(),
        movies=movies_settings_from_environment(),
        reddit=reddit_settings_from_environment(),
    ).run(transport="streamable-http", host=settings.host, port=settings.port, transport_security=transport_security_for(settings))


if __name__ == "__main__":
    main()
