"""A page that cannot be read raises PageUnreadable naming the cause, fetch_page tells the model what to do next, search_and_read skips the page, and a
failure is never cached."""

from pathlib import Path

import httpx
import pytest

from assistant_core.models import ToolCall
from assistant_core.tools import McpToolBox
from tests.test_url_guard import HTML, extractor_with, fake_resolver
from web_search_mcp.page_extractor import PageExtractor
from web_search_mcp.page_failures import PageFailure, PageUnreadable
from web_search_mcp.query_cache import QueryCache
from web_search_mcp.searxng_client import SearchResult
from web_search_mcp.server import build_server
from web_search_mcp.settings import SearchSettings

PUBLIC = {"site.example": ["93.184.216.34"]}
URL = "http://site.example/page"
ARTICLE = "<html><body><article><p>" + "A sentence a reader came for. " * 30 + "</p></article></body></html>"


def answering(status: int, headers: dict[str, str] | None = None, body: str = "") -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(status, headers={**HTML, **(headers or {})}, text=body))


def raising(error: httpx.HTTPError) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return httpx.MockTransport(handler)


async def failure_reading(transport: httpx.MockTransport) -> PageFailure:
    extractor = PageExtractor(SearchSettings(), QueryCache(None), resolver=fake_resolver(PUBLIC), transport=transport)
    with pytest.raises(PageUnreadable) as unreadable:
        await extractor.read_page(URL)
    return unreadable.value.failure


@pytest.mark.parametrize(
    ("transport", "expected"),
    [
        (answering(202, {"x-amzn-waf-action": "challenge"}), PageFailure.CHALLENGED),
        (answering(403, {"cf-mitigated": "challenge"}), PageFailure.CHALLENGED),
        (answering(403), PageFailure.REFUSED),
        (answering(404), PageFailure.NOT_FOUND),
        (answering(410), PageFailure.NOT_FOUND),
        (answering(429), PageFailure.RATE_LIMITED),
        (answering(503), PageFailure.SITE_ERROR),
        (answering(200, {"content-type": "application/json"}, "{}"), PageFailure.NOT_A_PAGE),
        (answering(200, body="<html><body></body></html>"), PageFailure.NO_TEXT),
        (answering(302, {"location": URL}), PageFailure.REDIRECT_LOOP),
        (raising(httpx.ReadTimeout("slow")), PageFailure.TIMED_OUT),
        (raising(httpx.ConnectError("refused")), PageFailure.UNREACHABLE),
    ],
)
async def test_each_unreadable_page_names_its_cause(transport: httpx.MockTransport, expected: PageFailure) -> None:
    assert await failure_reading(transport) is expected


async def test_a_failure_is_not_cached_so_the_page_is_tried_again(tmp_path: Path) -> None:
    statuses = iter([503, 200])

    def flaky(request: httpx.Request) -> httpx.Response:
        return httpx.Response(next(statuses), headers=HTML, text=ARTICLE)

    extractor = PageExtractor(SearchSettings(), QueryCache(str(tmp_path)), resolver=fake_resolver(PUBLIC), transport=httpx.MockTransport(flaky))
    with pytest.raises(PageUnreadable):
        await extractor.read_page(URL)

    assert "A sentence a reader came for." in await extractor.read_page(URL)


async def test_fetch_page_tells_the_model_the_cause_and_what_to_do() -> None:
    extractor = PageExtractor(SearchSettings(), QueryCache(None), resolver=fake_resolver(PUBLIC), transport=answering(202, {"x-amzn-waf-action": "challenge"}))
    async with McpToolBox(build_server(SearchSettings(), extractor=extractor)) as toolbox:
        reply = await toolbox.call(ToolCall(id="fetch", name="fetch_page", arguments={"url": URL}))

    assert reply == f"Could not read {URL} (challenged): {PageFailure.CHALLENGED}."


async def test_search_and_read_skips_an_unreadable_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers=HTML) if request.headers["host"] == "busy.example" else httpx.Response(200, headers=HTML, text=ARTICLE)

    extractor = extractor_with(handler, {"busy.example": ["93.184.216.34"], "good.example": ["93.184.216.35"]})
    results = [SearchResult(title=host, url=f"http://{host}/", snippet="", engines=["x"], score=1.0) for host in ("busy.example", "good.example")]

    assert [excerpt.title for excerpt in await extractor.read_pages(results, "sentence")] == ["good.example"]
