"""The agent's tool server over streamable HTTP: search_and_read (what small models should use), web_search, fetch_page, the calculator tools, the home weather
forecast, and Wikipedia lookups."""

import html
import re
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from assistant_core.exchange_record import EXCHANGES_ROUTE, ExchangeRecord
from assistant_core.models import REQUIRED_TOOL_NAMES
from calculator_mcp.register import register_calculator_tools
from utils.text_utils import clip_to_words
from weather_mcp.register import register_weather_tools
from weather_mcp.settings import WeatherSettings, weather_settings_from_environment
from web_search_mcp.exchange_log import ExchangeLog
from web_search_mcp.page_extractor import PageExcerpt, PageExtractor
from web_search_mcp.query_cache import QueryCache
from web_search_mcp.searxng_client import SearchResult, SearxngClient, TimeRange
from web_search_mcp.settings import SearchSettings, allowed_host_list, settings_from_environment
from web_search_mcp.url_guard import UnsafeUrl
from wikipedia_mcp.client import WikipediaClient
from wikipedia_mcp.register import register_wikipedia_tools
from wikipedia_mcp.settings import WikipediaSettings, wikipedia_settings_from_environment

HTML_TAG = re.compile(r"<[^>]+>")
NOT_FOUND_INSTRUCTION = "If these sources do not answer the question, say plainly that you could not find it."


def build_server(
    settings: SearchSettings,
    searxng: SearxngClient | None = None,
    extractor: PageExtractor | None = None,
    weather: WeatherSettings | None = None,
    wikipedia: WikipediaSettings | None = None,
) -> MCPServer:
    cache = QueryCache(settings.cache_dir)
    wikipedia = wikipedia or WikipediaSettings()
    searxng = searxng or SearxngClient(settings, cache)
    extractor = extractor or PageExtractor(settings, cache, wikipedia=WikipediaClient(wikipedia, cache))
    server = MCPServer(
        "assistant-tools",
        instructions=(
            "Web search backed by a local SearXNG instance, Wikipedia articles, exact calculator tools, and the forecast for home. Prefer search_and_read for questions"
            " about the world and wikipedia_lookup for settled facts, lists, and records; use the calculator tools for any arithmetic and weather_forecast for the weather at home."
        ),
    )

    @server.tool()
    async def search_and_read(query: str, time_range: TimeRange | None = None) -> str:
        """Search the web and read the top pages. Returns the ranked results, numbered, with the parts of each readable page that best match the query and the snippet of each page that could not be read, ready to synthesize an answer from. Use short keyword queries, e.g. "federal funds rate september 2026". time_range: optional "day", "week", "month", or "year" to keep only recent pages; use it for "latest" or "this week" questions."""
        results = await searxng.search(query, time_range)
        excerpts = await extractor.read_pages(results, query)
        return render_grounded_context(query, results, excerpts, settings.results_to_return)

    @server.tool()
    async def web_search(query: str, time_range: TimeRange | None = None) -> str:
        """Search the web and return only the ranked result list (title, URL, snippet) without reading the pages. Use when you want to pick which page to read with fetch_page. time_range: optional "day", "week", "month", or "year" to keep only recent pages; use it for "latest" or "this week" questions."""
        results = await searxng.search(query, time_range)
        return render_result_list(results[: settings.results_to_return])

    @server.tool()
    async def fetch_page(url: str) -> str:
        """Fetch one public web page and return its main text, trimmed to a readable length. Only public http(s) addresses are allowed."""
        try:
            text = await extractor.read_page(url)
        except UnsafeUrl as error:
            return f"Refused to fetch {url}: {error}. Only public web addresses can be read."
        if not text:
            return f"Could not extract readable text from {url}."
        return clip_to_words(text, settings.words_per_page * 2)

    register_calculator_tools(server)
    register_weather_tools(server, weather or WeatherSettings(), cache)
    register_wikipedia_tools(server, wikipedia, cache)
    register_operations_routes(server, ExchangeLog(Path(settings.exchanges_dir)) if settings.exchanges_dir else None, allowed_host_list(settings))
    return server


def transport_security_for(settings: SearchSettings) -> TransportSecuritySettings | None:
    """When the server is bound to the LAN, only requests naming this machine in their Host header are served, and none that carry a browser
    Origin. That stops a web page from reaching the server through DNS rebinding. With no allow-list (localhost binds) the library's default applies.
    The library takes this on run() and streamable_http_app(), not on the constructor, so build_server's callers pass it themselves."""
    allowed_hosts = allowed_host_list(settings)
    if not allowed_hosts:
        return None
    return TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=allowed_hosts, allowed_origins=[])


def host_allowed(request: Request, allowed_hosts: list[str]) -> bool:
    if not allowed_hosts:
        return True
    if request.headers.get("origin"):
        return False
    host = request.headers.get("host", "")
    return host in allowed_hosts or any(pattern.endswith(":*") and host.startswith(pattern[:-1]) for pattern in allowed_hosts)


def register_operations_routes(server: MCPServer, exchange_log: ExchangeLog | None, allowed_hosts: list[str]) -> None:  # deslop: allow-comments
    """Two plain HTTP routes beside the MCP endpoint (design doc 10): the health check proves this server is ours, and the component posts its exchange records.

    Custom routes bypass MCP's session handling; like the rest of the server they are reachable only on the LAN."""

    @server.custom_route("/healthz", ["GET"])
    async def healthz(request: Request) -> Response:
        if not host_allowed(request, allowed_hosts):
            return misdirected(request)
        names = sorted(tool.name for tool in await server.list_tools())
        missing = sorted(REQUIRED_TOOL_NAMES - set(names))
        return JSONResponse({"status": "ok" if not missing else "degraded", "tools": names, "missing": missing, "exchanges_dir": str(exchange_log.directory) if exchange_log else None})

    @server.custom_route(EXCHANGES_ROUTE, ["POST"])
    async def exchanges(request: Request) -> Response:
        if not host_allowed(request, allowed_hosts):
            return misdirected(request)
        if exchange_log is None:
            return JSONResponse({"error": "exchange logging is not configured (WEB_SEARCH_EXCHANGES_DIR unset)"}, status_code=503)
        try:
            record = ExchangeRecord.model_validate_json(await request.body())
        except ValidationError as error:
            return JSONResponse({"error": "not an ExchangeRecord", "detail": error.errors(include_input=False, include_url=False)[:3]}, status_code=400)
        exchange_log.append(record)
        return Response(status_code=204)


def misdirected(request: Request) -> Response:
    return JSONResponse({"error": f"host {request.headers.get('host', '')!r} is not this server"}, status_code=421)


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
    build_server(settings, weather=weather_settings_from_environment(), wikipedia=wikipedia_settings_from_environment()).run(
        transport="streamable-http", host=settings.host, port=settings.port, transport_security=transport_security_for(settings)
    )


if __name__ == "__main__":
    main()
