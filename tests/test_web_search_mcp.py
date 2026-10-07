"""The search tools in process: listing and calling them, the ranked list of results read and unread, and pages read for the passages that answer the
query. The SmashWiki fixture is the "Kill confirm" page (revision 2034943) as served on 2026-10-07, trimmed to its article: the lead, the Smash 64,
Melee, and Brawl sections, and the first 40 rows of the Ultimate table, which hold the answer."""

import json
from pathlib import Path

import httpx

from assistant_core.models import ToolCall
from assistant_core.tools import McpToolBox
from web_search_mcp.page_extractor import PageExcerpt, PageExtractor, apply_total_budget
from web_search_mcp.page_markdown import to_passage_format
from web_search_mcp.query_cache import QueryCache
from web_search_mcp.searxng_client import SearchResult, TimeRange
from web_search_mcp.server import NOT_FOUND_INSTRUCTION, build_server, render_grounded_context
from web_search_mcp.settings import SearchSettings

SMASHWIKI_PAGE = Path("tests/fixtures/smashwiki_kill_confirm.html").read_text()
SMASH_QUERY = "Super Smash Bros character jab back air kill confirm"
KILL_CONFIRM_RESULT = SearchResult(title="Kill confirm - SmashWiki, the Super Smash Bros. wiki", url="https://www.ssbwiki.com/Kill_confirm", snippet="", engines=["google"], score=1.0)


class FakeSearxng:
    async def search(self, query: str, time_range: TimeRange | None = None) -> list[SearchResult]:
        return [SearchResult(title=f"Result for {query}", url="http://example.com/a", snippet="snippet", engines=["google"], score=1.0)]


class FakeExtractor:
    async def read_pages(self, results: list[SearchResult], focus: str) -> list[PageExcerpt]:
        return [PageExcerpt(title=result.title, url=result.url, text="Body text of the page.", word_count=5) for result in results]

    async def read_page(self, url: str) -> str:
        return "Fetched page text."


async def test_tools_are_listed_and_callable_in_process() -> None:
    server = build_server(SearchSettings(), searxng=FakeSearxng(), extractor=FakeExtractor())
    async with McpToolBox(server) as toolbox:
        names = [spec.name for spec in await toolbox.list_tools()]
        assert names[:3] == ["search_and_read", "web_search", "fetch_page"]
        assert "calculate" in names and "convert" in names
        assert "query" in (await toolbox.list_tools())[0].input_schema["properties"]
        grounded = await toolbox.call(ToolCall(id="1", name="search_and_read", arguments={"query": "fed funds rate"}))
        assert grounded.startswith('Read 1 of 1 results for "fed funds rate".')
        assert "Body text of the page." in grounded
        assert await toolbox.call(ToolCall(id="2", name="fetch_page", arguments={"url": "http://example.com"})) == "Fetched page text."


def test_grounded_context_explains_empty_results() -> None:
    assert render_grounded_context("q", [], [], 8).startswith('No search results for "q"')


def test_total_word_budget_trims_later_excerpts() -> None:
    excerpts = [PageExcerpt(title="a", url="u", text="one two three", word_count=3), PageExcerpt(title="b", url="v", text="four five six", word_count=3)]
    kept = apply_total_budget(excerpts, total_word_budget=4)
    assert [excerpt.text for excerpt in kept] == ["one two three", "four"]


def test_blocked_and_binary_urls_are_not_fetched() -> None:
    extractor = PageExtractor(SearchSettings(), QueryCache(None))
    assert extractor.is_fetchable("https://www.example.com/article") is True
    assert extractor.is_fetchable("https://www.facebook.com/post") is False
    assert extractor.is_fetchable("https://example.com/report.pdf") is False


async def test_search_tools_take_an_optional_time_range() -> None:
    async with McpToolBox(build_server(SearchSettings(), searxng=FakeSearxng(), extractor=FakeExtractor())) as toolbox:
        specs = {spec.name: spec for spec in await toolbox.list_tools()}
    for name in ("search_and_read", "web_search"):
        assert "week" in json.dumps(specs[name].input_schema["properties"]["time_range"]) and specs[name].input_schema["required"] == ["query"]


def search_result(rank: int, title: str, snippet: str = "") -> SearchResult:
    return SearchResult(title=title, url=f"https://example.com/{rank}", snippet=snippet, engines=["google"], score=1.0)


def test_unread_results_keep_their_rank_title_and_snippet() -> None:
    results = [
        search_result(1, "Kill confirm - SmashWiki"),
        search_result(2, "Roy jab back air kill confirm - YouTube", "<b>Roy</b> &amp; Chrom&#39;s jab to back air"),
        search_result(3, "Lock - SmashWiki"),
        search_result(4, "Smash tier list - Reddit", "Unread and past the list's length"),
    ]
    excerpts = [
        PageExcerpt(title=results[0].title, url=results[0].url, text="Roy | Jab to back aerial", word_count=5),
        PageExcerpt(title=results[2].title, url=results[2].url, text="Lock text", word_count=2),
    ]
    assert render_grounded_context("q", results, excerpts, results_to_list=2).split("\n\n") == [
        'Read 2 of 4 results for "q".',
        "[1] Kill confirm - SmashWiki\nURL: https://example.com/1\nRoy | Jab to back aerial",
        "[2] Roy jab back air kill confirm - YouTube (not read)\nRoy & Chrom's jab to back air",
        "[3] Lock - SmashWiki\nURL: https://example.com/3\nLock text",
        NOT_FOUND_INSTRUCTION,
    ]


async def public_address(host: str) -> list[str]:
    return ["93.184.216.34"]


def smashwiki_extractor() -> PageExtractor:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=SMASHWIKI_PAGE))
    return PageExtractor(SearchSettings(), QueryCache(None), resolver=public_address, transport=transport)


async def test_the_rows_that_answer_are_found_deep_in_a_long_page() -> None:
    """The exchange of 2026-10-07: the answer sits about 3,000 words into the page, below Melee rows that also say "jab" and "back"."""
    [excerpt] = await smashwiki_extractor().read_pages([KILL_CONFIRM_RESULT], SMASH_QUERY)
    assert "\nRoy | *Jab to sweetspotted back aerial *Up aerial to sweetspotted back aerial" in excerpt.text
    assert "\nChrom | *Jab to back aerial *Up aerial to back aerial" in excerpt.text
    assert "### In Super Smash Bros. Ultimate\nCharacter | Description\n" in excerpt.text
    assert excerpt.word_count <= SearchSettings().words_per_page


async def test_an_ordinary_page_keeps_its_headings_and_rows() -> None:
    text = await smashwiki_extractor().read_page(KILL_CONFIRM_RESULT.url)
    assert text.startswith("# Kill confirm\n\nA kill confirm, also known as a KO setup,")
    assert "\n\n### In Super Smash Bros. Melee\n\nCharacter | Description\nCaptain Falcon | *Down throw and up throw" in text


def test_markdown_comes_back_in_the_shared_passage_format() -> None:
    markdown = "#\n## Moves[edit]\n| Character | Setup | \n|---|---|\n| **Roy** | *Jab to back aerial *Up aerial | \n\n- A *weak* attack\n* A strong throw\n\n#1 seller, a <sub>$</sub>69 paragraph\nthat wraps."
    assert to_passage_format(markdown) == "## Moves\n\nCharacter | Setup\nRoy | *Jab to back aerial *Up aerial\n\n- A weak attack\n- A strong throw\n\n#1 seller, a $69 paragraph that wraps."
