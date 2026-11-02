"""The agent's tool server over streamable HTTP. Every tool package registers its tools on this one server: web search, the calculator tools, the home weather
forecast, Wikipedia lookups, NBA and NFL scores and statistics, Broadway and movie listings, and what people on Reddit say."""

from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from assistant_core.models import REQUIRED_TOOL_NAMES
from assistant_mcp.settings import ToolServerSettings, allowed_host_list, tool_server_settings_from_environment
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
from weather_mcp.register import register_weather_tools
from weather_mcp.settings import WeatherSettings, weather_settings_from_environment
from web_search_mcp.fixtures import FIXTURE_ROUTE, FixturePages, FixtureSearch, fixture_route
from web_search_mcp.page_extractor import PageExtractor
from web_search_mcp.query_cache import QueryCache
from web_search_mcp.register import register_web_search_tools
from web_search_mcp.search_engines import SearchEngine, configured_search
from web_search_mcp.settings import SearchSettings, settings_from_environment
from wikipedia_mcp.client import WikipediaClient
from wikipedia_mcp.register import register_wikipedia_tools
from wikipedia_mcp.settings import WikipediaSettings, wikipedia_settings_from_environment


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
    tool_server: ToolServerSettings | None = None,
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
    register_web_search_tools(server, settings, search, extractor)
    register_calculator_tools(server)
    register_weather_tools(server, weather or WeatherSettings(), cache)
    register_wikipedia_tools(server, wikipedia, cache)
    register_sports_tools(server, sports or SportsSettings(cache_dir=None))  # a server built without settings, as in tests, leaves the real cache alone
    register_broadway_tools(server, broadway or BroadwaySettings())
    register_movies_tools(server, movies or MoviesSettings())
    register_reddit_tools(server, reddit or RedditSettings(), search)  # reddit_search searches through the same client as web search
    register_operations_routes(server, allowed_host_list(tool_server or ToolServerSettings()))
    if fixture_pages:
        server.custom_route(FIXTURE_ROUTE, ["POST"])(fixture_route(fixture_pages))
    return server


def transport_security_for(settings: ToolServerSettings) -> TransportSecuritySettings | None:
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


def main() -> None:
    tool_server = tool_server_settings_from_environment()
    build_server(
        settings_from_environment(),
        weather=weather_settings_from_environment(),
        wikipedia=wikipedia_settings_from_environment(),
        sports=sports_settings_from_environment(),
        broadway=broadway_settings_from_environment(),
        movies=movies_settings_from_environment(),
        reddit=reddit_settings_from_environment(),
        tool_server=tool_server,
    ).run(transport="streamable-http", host=tool_server.host, port=tool_server.port, transport_security=transport_security_for(tool_server))


if __name__ == "__main__":
    main()
