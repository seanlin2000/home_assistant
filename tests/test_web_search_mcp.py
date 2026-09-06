from assistant_core.models import ToolCall
from assistant_core.tools import McpToolBox
from web_search_mcp.page_extractor import PageExcerpt, PageExtractor, apply_total_budget
from web_search_mcp.query_cache import QueryCache
from web_search_mcp.searxng_client import SearchResult
from web_search_mcp.server import build_server, render_grounded_context
from web_search_mcp.settings import SearchSettings


class FakeSearxng:
    async def search(self, query: str) -> list[SearchResult]:
        return [SearchResult(title=f"Result for {query}", url="http://example.com/a", snippet="snippet", engines=["google"], score=1.0)]


class FakeExtractor:
    async def read_pages(self, results: list[SearchResult]) -> list[PageExcerpt]:
        return [PageExcerpt(title=result.title, url=result.url, text="Body text of the page.", word_count=5) for result in results]

    async def read_page(self, url: str) -> str:
        return "Fetched page text."


async def test_tools_are_listed_and_callable_in_process() -> None:
    server = build_server(SearchSettings(), searxng=FakeSearxng(), extractor=FakeExtractor())
    async with McpToolBox(server) as toolbox:
        names = [spec.name for spec in await toolbox.list_tools()]
        assert names == ["search_and_read", "web_search", "fetch_page"]
        assert "query" in (await toolbox.list_tools())[0].input_schema["properties"]
        grounded = await toolbox.call(ToolCall(id="1", name="search_and_read", arguments={"query": "fed funds rate"}))
        assert grounded.startswith('Read 1 of 1 results for "fed funds rate".')
        assert "Body text of the page." in grounded
        assert await toolbox.call(ToolCall(id="2", name="fetch_page", arguments={"url": "http://example.com"})) == "Fetched page text."


def test_grounded_context_explains_empty_results() -> None:
    assert render_grounded_context("q", [], []).startswith('No search results for "q"')


def test_total_word_budget_trims_later_excerpts() -> None:
    excerpts = [PageExcerpt(title="a", url="u", text="one two three", word_count=3), PageExcerpt(title="b", url="v", text="four five six", word_count=3)]
    kept = apply_total_budget(excerpts, total_word_budget=4)
    assert [excerpt.text for excerpt in kept] == ["one two three", "four"]


def test_blocked_and_binary_urls_are_not_fetched() -> None:
    extractor = PageExtractor(SearchSettings(), QueryCache(None))
    assert extractor.is_fetchable("https://www.example.com/article") is True
    assert extractor.is_fetchable("https://www.facebook.com/post") is False
    assert extractor.is_fetchable("https://example.com/report.pdf") is False
