"""The wikipedia_lookup tool and Wikipedia pages read by search_and_read: tables kept as rows, the focus picking the part of a long article, the API etiquette,
the cache, and the fixed replies when Wikipedia cannot help. The fixtures are Wikimedia's REST answers recorded on 2026-10-07: the search for
"49ers starting quarterbacks" and the Parsoid HTML of List of San Francisco 49ers starting quarterbacks (revision 1377996695), trimmed of its page
head, all but one figure, and all but one navigation box."""

import json
import re
from pathlib import Path
from typing import Any

import httpx
import pytest
from mcp.server.mcpserver import MCPServer

from assistant_core.models import ToolCall
from assistant_core.tools import McpToolBox
from web_search_mcp.page_extractor import PageExtractor
from web_search_mcp.query_cache import QueryCache
from web_search_mcp.searxng_client import SearchResult
from web_search_mcp.server import build_server
from web_search_mcp.settings import SearchSettings
from wikipedia_mcp.article import render_article
from wikipedia_mcp.client import WikipediaClient, WikipediaUnavailable
from wikipedia_mcp.passages import select_passages
from wikipedia_mcp.register import NO_ARTICLE_MESSAGE, NO_TOPIC_MESSAGE, SERVICE_DOWN_MESSAGE, WIKIPEDIA_TOOL_NAME, register_wikipedia_tools
from wikipedia_mcp.settings import USER_AGENT, WikipediaSettings, wikipedia_settings_from_environment

ARTICLE_HTML = Path("tests/fixtures/wikipedia_49ers_starting_quarterbacks.html").read_text()
SEARCH_BODY = json.loads(Path("tests/fixtures/wikipedia_search_49ers_starting_quarterbacks.json").read_text())
ARTICLE_TITLE = "List of San Francisco 49ers starting quarterbacks"
ARTICLE_URL = "https://en.wikipedia.org/wiki/List_of_San_Francisco_49ers_starting_quarterbacks"
ARTICLE_TEXT = render_article(ARTICLE_HTML)
SEARCH_PATH = "/w/rest.php/v1/search/page"
ARTICLE_PATH = "/w/rest.php/v1/page/List_of_San_Francisco_49ers_starting_quarterbacks/html"
SEASON_ROW = re.compile(r"^(\d{4}) \| ")


class FakeWikipedia:
    """Serves the recorded search and article, and remembers every request so tests can check what was asked and how."""

    def __init__(self, search_body: dict[str, Any] = SEARCH_BODY, article_status: int = 200) -> None:
        self.search_body = search_body
        self.article_status = article_status
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == SEARCH_PATH:
            return httpx.Response(200, json=self.search_body)
        if request.url.path == ARTICLE_PATH:
            return httpx.Response(self.article_status, text=ARTICLE_HTML if self.article_status == 200 else "not found")
        return httpx.Response(404, text="not found")

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)


async def lookup(wikipedia: FakeWikipedia, store: QueryCache | None = None, **arguments: str) -> str:
    server = MCPServer("test")
    register_wikipedia_tools(server, WikipediaSettings(), store or QueryCache(None), wikipedia.transport)
    async with McpToolBox(server) as toolbox:
        return await toolbox.call(ToolCall(id="1", name=WIKIPEDIA_TOOL_NAME, arguments=arguments))


def season_years(text: str) -> list[int]:
    return [int(match.group(1)) for match in map(SEASON_ROW.match, text.split("\n")) if match]


def test_tables_come_back_one_row_per_line_under_their_headings() -> None:
    lines = ARTICLE_TEXT.split("\n")
    assert "2001 | Jeff Garcia (16)" in lines
    assert "Season(s) | Quarterback(s)" in lines
    assert "Name | Comp | Att | % | Yds | TD | Int" in lines
    assert lines.index("## Starting quarterbacks") < lines.index("### Regular season") < lines.index("2001 | Jeff Garcia (16)")


def test_citations_styles_and_closing_sections_are_left_out() -> None:
    assert "[1]" not in ARTICLE_TEXT and "mw-parser-output" not in ARTICLE_TEXT
    assert "See also" not in ARTICLE_TEXT and "Lists of NFL starting quarterbacks" not in ARTICLE_TEXT and "References" not in ARTICLE_TEXT


def test_a_year_in_the_focus_keeps_every_row_from_that_year_on_and_none_before() -> None:
    selected = select_passages(ARTICLE_TEXT, "2000", 900)
    regular_season = selected.split("### Postseason")[0]
    assert season_years(regular_season) == list(range(2000, 2027))
    assert "Season(s) | Quarterback(s)" in selected and "1999 |" not in selected
    assert len(selected.split()) <= 900


def test_a_list_cut_by_the_budget_is_unbroken_and_says_how_much_is_missing() -> None:
    selected = select_passages(ARTICLE_TEXT, "San Francisco 49ers starting quarterbacks", 900)
    years = season_years(selected.split("##", 2)[-1].split("## Most games")[0])
    assert years[0] == 1950 and years == list(range(1950, years[-1] + 1)) and years[-1] < 2026
    assert re.search(r"\[\d+ more matching lines here did not fit", selected)
    assert len(selected.split()) <= 900


def test_focus_words_find_the_section_whose_heading_names_them() -> None:
    selected = select_passages(ARTICLE_TEXT, "team passing records", 200)
    assert "## Team career passing records" in selected and "Joe Montana | 2,929 | 4,600 | 63.7 | 35,124 | 244 | 123" in selected
    assert selected.startswith("These quarterbacks have started at least one game")


def test_a_short_article_comes_back_whole() -> None:
    article = "A short lead.\n\n## Seasons\n\nSeason | Coach\n2001 | Someone"
    assert select_passages(article, "coach", 900) == article.replace("\n\n", "\n")


async def test_lookup_names_the_article_and_offers_the_runners_up() -> None:
    wikipedia = FakeWikipedia()
    reply = await lookup(wikipedia, topic="49ers starting quarterbacks", focus="2000")
    assert reply.startswith(f"Wikipedia: {ARTICLE_TITLE}\nURL: {ARTICLE_URL}\n\n")
    assert "\n2001 | Jeff Garcia (16)\n" in reply and "1999 |" not in reply
    assert reply.endswith("Other articles: Brock Purdy; List of current NFL starting quarterbacks; Alex Smith; List of Black starting NFL quarterbacks")


async def test_requests_identify_the_application_and_ask_for_five_titles() -> None:
    wikipedia = FakeWikipedia()
    await lookup(wikipedia, topic="49ers starting quarterbacks")
    assert [request.url.path for request in wikipedia.requests] == [SEARCH_PATH, ARTICLE_PATH]
    assert all(request.headers["user-agent"] == USER_AGENT for request in wikipedia.requests)
    assert dict(wikipedia.requests[0].url.params) == {"q": "49ers starting quarterbacks", "limit": "5"}


async def test_cached_lookups_do_not_ask_wikipedia_again(tmp_path: Path) -> None:
    wikipedia = FakeWikipedia()
    store = QueryCache(str(tmp_path))
    first = await lookup(wikipedia, store, topic="49ers starting quarterbacks", focus="2000")
    second = await lookup(wikipedia, store, topic="49ers starting quarterbacks", focus="2000")
    assert first == second and len(wikipedia.requests) == 2


@pytest.mark.parametrize(
    ("wikipedia", "expected"),
    [
        (FakeWikipedia(article_status=404), SERVICE_DOWN_MESSAGE),
        (FakeWikipedia(search_body={"pages": []}), NO_ARTICLE_MESSAGE.format(topic="49ers starting quarterbacks")),
    ],
)
async def test_failures_come_back_as_a_sentence_the_model_can_act_on(wikipedia: FakeWikipedia, expected: str) -> None:
    assert await lookup(wikipedia, topic="49ers starting quarterbacks") == expected


async def test_a_network_failure_or_an_empty_topic_never_raises() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    server = MCPServer("test")
    register_wikipedia_tools(server, WikipediaSettings(), QueryCache(None), httpx.MockTransport(refuse))
    async with McpToolBox(server) as toolbox:
        assert await toolbox.call(ToolCall(id="1", name=WIKIPEDIA_TOOL_NAME, arguments={"topic": "49ers"})) == SERVICE_DOWN_MESSAGE
        assert await toolbox.call(ToolCall(id="2", name=WIKIPEDIA_TOOL_NAME, arguments={"topic": " "})) == NO_TOPIC_MESSAGE


async def test_redirects_are_followed_on_wikipedia_and_refused_off_it() -> None:
    def redirect_to(location: str) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            if request.url.path == ARTICLE_PATH:
                return httpx.Response(200, text=ARTICLE_HTML)
            return httpx.Response(307, headers={"location": location})

        return httpx.MockTransport(handle)

    on_wikipedia = WikipediaClient(WikipediaSettings(), QueryCache(None), redirect_to(ARTICLE_PATH))
    assert await on_wikipedia.article_html("49ers starting quarterbacks") == ARTICLE_HTML
    off_wikipedia = WikipediaClient(WikipediaSettings(), QueryCache(None), redirect_to("https://wiki.example/page"))
    with pytest.raises(WikipediaUnavailable, match="redirected off its own host"):
        await off_wikipedia.article_html("49ers starting quarterbacks")


def test_only_english_article_addresses_are_read_through_the_api() -> None:
    client = WikipediaClient(WikipediaSettings(), QueryCache(None))
    assert client.article_title_in(f"{ARTICLE_URL}#Regular_season") == ARTICLE_TITLE
    assert client.article_title_in("https://en.wikipedia.org/wiki/AC%2FDC") == "AC/DC"
    assert client.article_title_in("https://de.wikipedia.org/wiki/San_Francisco_49ers") is None
    assert client.article_title_in("https://en.wikipedia.org/w/index.php?title=Brock_Purdy") is None


async def test_search_and_read_reads_a_wikipedia_result_through_the_api_with_the_query_as_focus() -> None:
    def no_generic_download(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"read {request.url} as an ordinary page")

    wikipedia = FakeWikipedia()
    extractor = PageExtractor(
        SearchSettings(), QueryCache(None), transport=httpx.MockTransport(no_generic_download), wikipedia=WikipediaClient(WikipediaSettings(), QueryCache(None), wikipedia.transport)
    )
    result = SearchResult(title=ARTICLE_TITLE, url=ARTICLE_URL, snippet="", engines=["wikipedia"], score=1.0)
    [excerpt] = await extractor.read_pages([result], "49ers starting quarterbacks since 2000")
    assert "\n2001 | Jeff Garcia (16)\n" in excerpt.text and "1999 |" not in excerpt.text
    assert excerpt.word_count <= SearchSettings().words_per_page


async def test_search_and_read_falls_back_to_the_page_when_the_api_fails() -> None:
    async def public_address(host: str) -> list[str]:
        return ["93.184.216.34"]

    def page(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html><body><article><p>" + "Readable article prose. " * 30 + "</p></article></body></html>")

    extractor = PageExtractor(
        SearchSettings(),
        QueryCache(None),
        resolver=public_address,
        transport=httpx.MockTransport(page),
        wikipedia=WikipediaClient(WikipediaSettings(), QueryCache(None), FakeWikipedia(article_status=503).transport),
    )
    assert (await extractor.read_page(ARTICLE_URL)).startswith("Readable article prose.")


def test_settings_come_from_wikipedia_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WIKIPEDIA_MAX_WORDS", "300")
    monkeypatch.setenv("WIKIPEDIA_TIMEOUT_SECONDS", " ")
    settings = wikipedia_settings_from_environment()
    assert settings.max_words == 300 and settings.timeout_seconds == WikipediaSettings().timeout_seconds


async def test_the_tool_server_offers_wikipedia_lookup_after_the_search_tools() -> None:
    async with McpToolBox(build_server(SearchSettings())) as toolbox:
        names = [spec.name for spec in await toolbox.list_tools()]
    assert names[:3] == ["search_and_read", "web_search", "fetch_page"] and WIKIPEDIA_TOOL_NAME in names


def test_superscripts_breaks_and_hidden_sort_keys_do_not_run_into_the_words_beside_them() -> None:
    html = (
        "<html><body><section><table class='wikitable'><tr><th>Winner</th><th>Score</th></tr>"
        "<tr><td>San Francisco 49ers<sup>N</sup>(1, 1–0)</td><td><span style='display: none'>026</span>26<br>final</td></tr></table>"
        "<section><h2>Works cited</h2><p>Shugart, Matthew S. (2004).</p></section></section></body></html>"
    )
    assert render_article(html) == "Winner | Score\nSan Francisco 49ers N (1, 1–0) | 26 final"
