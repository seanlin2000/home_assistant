"""Expose web search as MCP tools on the existing server, so the agent sees one tool list: search_and_read (what small models should use), web_search, and
fetch_page. The server builds the search client and the page reader and hands them in, because reddit_search shares the same search client."""

import html
import re

from mcp.server.mcpserver import MCPServer

from utils.text_utils import clip_to_words, word_count
from web_search_mcp.page_extractor import PageExcerpt, PageExtractor
from web_search_mcp.page_failures import PageUnreadable
from web_search_mcp.search_engines import SearchEngine
from web_search_mcp.searxng_client import SearchResult
from web_search_mcp.settings import SearchSettings
from web_search_mcp.url_guard import UnsafeUrl

HTML_TAG = re.compile(r"<[^>]+>")
NOT_FOUND_INSTRUCTION = "If these sources do not answer the question, say plainly that you could not find it."


def register_web_search_tools(server: MCPServer, settings: SearchSettings, search: SearchEngine, extractor: PageExtractor) -> None:
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
