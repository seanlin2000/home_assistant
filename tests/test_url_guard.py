"""The fetch path must refuse private addresses at every hop and stop reading oversized pages."""

from collections.abc import Callable

import httpx
import pytest

from web_search_mcp.page_extractor import PageExtractor
from web_search_mcp.query_cache import QueryCache
from web_search_mcp.settings import SearchSettings
from web_search_mcp.url_guard import UnsafeUrl, ensure_public_url, is_public_address

HTML = {"content-type": "text/html; charset=utf-8"}


def fake_resolver(table: dict[str, list[str]]):
    async def resolve(host: str) -> list[str]:
        return table[host]

    return resolve


@pytest.mark.parametrize(
    "address, public",
    [
        ("93.184.216.34", True),
        ("2606:2800:220:1:248:1893:25c8:1946", True),
        ("127.0.0.1", False),
        ("10.0.0.5", False),
        ("192.168.1.1", False),
        ("172.16.3.4", False),
        ("169.254.169.254", False),
        ("::1", False),
        ("::ffff:192.168.1.5", False),
        ("fe80::1", False),
        ("0.0.0.0", False),
        ("224.0.0.1", False),
    ],
)
def test_public_address_classification(address: str, public: bool) -> None:
    assert is_public_address(address) is public


@pytest.mark.asyncio
async def test_ensure_public_url_rejects_schemes_names_and_private_resolutions() -> None:
    resolver = fake_resolver({"example.com": ["93.184.216.34"], "evil.example": ["93.184.216.34", "192.168.1.152"], "printer": ["10.0.0.9"]})
    await ensure_public_url("https://example.com/page", resolver)
    for bad in (
        "file:///etc/passwd",
        "ftp://example.com/x",
        "http://localhost:8123/",
        "http://homeassistant.local/",
        "http://192.168.1.152:11434/api/tags",
        "http://[::1]/",
        "http://evil.example/",
        "http://printer/",
        "http://metadata.google.internal/",
    ):
        with pytest.raises(UnsafeUrl):
            await ensure_public_url(bad, resolver)


def extractor_with(handler: Callable[[httpx.Request], httpx.Response], resolver_table: dict[str, list[str]], **settings: int) -> PageExtractor:
    return PageExtractor(SearchSettings(**settings), QueryCache(None), resolver=fake_resolver(resolver_table), transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_redirect_to_a_private_address_is_refused_even_after_a_public_first_hop() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "public.example":
            return httpx.Response(302, headers={"location": "http://192.168.1.1/admin"})
        return httpx.Response(200, headers=HTML, text="<html><body><p>router admin</p></body></html>")

    extractor = extractor_with(handler, {"public.example": ["93.184.216.34"]})
    with pytest.raises(UnsafeUrl):
        await extractor.read_page("http://public.example/start")


@pytest.mark.asyncio
async def test_public_redirects_are_followed_and_text_extracted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return httpx.Response(200, headers=HTML, text="<html><body><article><p>" + "The federal funds rate held steady this month. " * 20 + "</p></article></body></html>")

    extractor = extractor_with(handler, {"news.example": ["93.184.216.34"]})
    text = await extractor.read_page("http://news.example/old")
    assert "federal funds rate" in text


@pytest.mark.asyncio
async def test_oversized_pages_are_dropped_by_declared_length_and_by_stream() -> None:
    big = b"<html><body><p>" + b"x" * 5000 + b"</p></body></html>"

    def declared(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={**HTML, "content-length": "999999"}, content=b"<html></html>")

    def streamed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers=HTML, content=big)

    assert await extractor_with(declared, {"a.example": ["93.184.216.34"]}, max_page_bytes=1000).read_page("http://a.example/") == ""
    assert await extractor_with(streamed, {"b.example": ["93.184.216.34"]}, max_page_bytes=1000).read_page("http://b.example/") == ""
    assert await extractor_with(streamed, {"c.example": ["93.184.216.34"]}, max_page_bytes=100000).read_page("http://c.example/") != ""


@pytest.mark.asyncio
async def test_search_batches_skip_unsafe_urls_instead_of_failing() -> None:
    from web_search_mcp.searxng_client import SearchResult

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers=HTML, text="<html><body><article><p>" + "Useful public text. " * 30 + "</p></article></body></html>")

    extractor = extractor_with(handler, {"good.example": ["93.184.216.34"], "nas.example": ["192.168.1.20"]})
    results = [SearchResult(title="nas", url="http://nas.example/", snippet="", engines=["x"], score=1.0), SearchResult(title="good", url="http://good.example/", snippet="", engines=["x"], score=1.0)]
    excerpts = await extractor.read_pages(results)
    assert [excerpt.title for excerpt in excerpts] == ["good"]
