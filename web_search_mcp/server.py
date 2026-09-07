"""The agent's tool server over streamable HTTP: search_and_read (what small models should use), web_search, fetch_page, and the calculator tools."""

from pathlib import Path

from mcp.server.mcpserver import MCPServer
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from assistant_core.models import REQUIRED_TOOL_NAMES
from assistant_core.turn_record import TURNS_ROUTE, TurnRecord
from calculator_mcp.register import register_calculator_tools
from web_search_mcp.page_extractor import PageExcerpt, PageExtractor
from web_search_mcp.query_cache import QueryCache
from web_search_mcp.searxng_client import SearchResult, SearxngClient
from web_search_mcp.settings import SearchSettings, settings_from_environment
from web_search_mcp.turn_log import TurnLog
from web_search_mcp.url_guard import UnsafeUrl


def build_server(settings: SearchSettings, searxng: SearxngClient | None = None, extractor: PageExtractor | None = None) -> MCPServer:
    cache = QueryCache(settings.cache_dir)
    searxng = searxng or SearxngClient(settings, cache)
    extractor = extractor or PageExtractor(settings, cache)
    server = MCPServer(
        "assistant-tools",
        instructions="Web search backed by a local SearXNG instance plus exact calculator tools. Prefer search_and_read for questions about the world; use the calculator tools for any arithmetic.",
    )

    @server.tool()
    async def search_and_read(query: str) -> str:
        """Search the web and read the top pages. Returns numbered sources with title, URL, and the main text of each page, ready to synthesize an answer from. Use short keyword queries, e.g. "federal funds rate september 2026"."""
        results = await searxng.search(query)
        excerpts = await extractor.read_pages(results)
        return render_grounded_context(query, results, excerpts)

    @server.tool()
    async def web_search(query: str) -> str:
        """Search the web and return only the ranked result list (title, URL, snippet) without reading the pages. Use when you want to pick which page to read with fetch_page."""
        results = await searxng.search(query)
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
        return " ".join(text.split()[: settings.words_per_page * 2])

    register_calculator_tools(server)
    register_operations_routes(server, TurnLog(Path(settings.turns_dir)) if settings.turns_dir else None)
    return server


def register_operations_routes(server: MCPServer, turn_log: TurnLog | None) -> None:  # deslop: allow-comments
    """Two plain HTTP routes beside the MCP endpoint (design doc 10): the health check proves this server is ours, and the component posts its turn records.

    Custom routes bypass MCP's session handling; like the rest of the server they are reachable only on the LAN."""

    @server.custom_route("/healthz", ["GET"])
    async def healthz(request: Request) -> Response:
        names = sorted(tool.name for tool in await server.list_tools())
        missing = sorted(REQUIRED_TOOL_NAMES - set(names))
        return JSONResponse({"status": "ok" if not missing else "degraded", "tools": names, "missing": missing, "turns_dir": str(turn_log.directory) if turn_log else None})

    @server.custom_route(TURNS_ROUTE, ["POST"])
    async def turns(request: Request) -> Response:
        if turn_log is None:
            return JSONResponse({"error": "turn logging is not configured (WEB_SEARCH_TURNS_DIR unset)"}, status_code=503)
        try:
            record = TurnRecord.model_validate_json(await request.body())
        except ValidationError as error:
            return JSONResponse({"error": "not a TurnRecord", "detail": error.errors(include_input=False, include_url=False)[:3]}, status_code=400)
        turn_log.append(record)
        return Response(status_code=204)


def render_result_list(results: list[SearchResult]) -> str:
    if not results:
        return "No results."
    lines = [f"[{index}] {result.title}\n    {result.url}\n    {result.snippet}" for index, result in enumerate(results, start=1)]
    return "\n".join(lines)


def render_grounded_context(query: str, results: list[SearchResult], excerpts: list[PageExcerpt]) -> str:
    if not results:
        return f'No search results for "{query}". Tell the user you could not find anything and answer from your own knowledge with that caveat.'
    if not excerpts:
        return f'Search for "{query}" returned results but none of the pages could be read. Snippets only:\n{render_result_list(results[:5])}'
    header = f'Read {len(excerpts)} of {len(results)} results for "{query}".'
    sources = [f"[{index}] {excerpt.title}\nURL: {excerpt.url}\n{excerpt.text}" for index, excerpt in enumerate(excerpts, start=1)]
    return header + "\n\n" + "\n\n".join(sources)


def main() -> None:
    settings = settings_from_environment()
    build_server(settings).run(transport="streamable-http", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
