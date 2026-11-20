"""Finds and fetches English Wikipedia articles through Wikimedia's REST API (https://api.wikimedia.org/wiki/Core_REST_API), the way its etiquette asks.

The etiquette, and how this client meets it: identify the application in the User-Agent; make one request at a time per question rather than crawling;
keep what was fetched instead of asking again. The host is fixed by settings, not chosen by the model, so requests skip the public-address guard that
fetch_page applies, as the SearXNG and Met.no clients do; a redirect that would leave that host is refused instead.
"""

from typing import Any, Protocol
from urllib.parse import quote, unquote, urljoin, urlparse

import httpx

from wikipedia_mcp.settings import WikipediaSettings

SEARCH_PATH = "/w/rest.php/v1/search/page"
ARTICLE_HTML_PATH = "/w/rest.php/v1/page/{title}/html"
ARTICLE_PATH_PREFIX = "/wiki/"
MAX_REDIRECTS = 3
OK = 200


class WikipediaUnavailable(RuntimeError):
    """Wikipedia did not answer, or answered with something other than the article or search asked for."""


class ArticleStore(Protocol):
    """Pins search results and article HTML for the life of the store. The benchmark passes its per-run cache so every candidate reads the same
    revision; the product passes a disabled cache and fetches each time."""

    def get_article_titles(self, topic: str) -> list[str] | None: ...

    def put_article_titles(self, topic: str, titles: list[str]) -> None: ...

    def get_article_html(self, title: str) -> str | None: ...

    def put_article_html(self, title: str, html: str) -> None: ...


class WikipediaClient:
    def __init__(self, settings: WikipediaSettings, store: ArticleStore, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._settings = settings
        self._store = store
        self._transport = transport  # injectable so tests can serve canned responses without a socket

    async def search_titles(self, topic: str) -> list[str]:
        """Titles of the articles that best match the topic, best first; empty when nothing matches."""
        pinned = self._store.get_article_titles(topic)
        if pinned is not None:
            return pinned
        body = (await self._get(SEARCH_PATH, {"q": topic, "limit": self._settings.titles_to_offer})).json()
        titles = [page["title"] for page in body.get("pages", []) if page.get("title")]
        self._store.put_article_titles(topic, titles)
        return titles

    async def article_html(self, title: str) -> str:
        """The article as Wikimedia's Parsoid HTML: sections, headings, and tables intact."""
        pinned = self._store.get_article_html(title)
        if pinned is not None:
            return pinned
        html = (await self._get(ARTICLE_HTML_PATH.format(title=quote(title.replace(" ", "_"), safe="")), {})).text
        self._store.put_article_html(title, html)
        return html

    def article_url(self, title: str) -> str:
        return f"{self._settings.base_url}{ARTICLE_PATH_PREFIX}{quote(title.replace(' ', '_'))}"

    def article_title_in(self, url: str) -> str | None:
        """The article title a /wiki/ address on this client's host names, or None for any other address."""
        parsed = urlparse(url)
        if parsed.hostname != urlparse(self._settings.base_url).hostname or not parsed.path.startswith(ARTICLE_PATH_PREFIX):
            return None
        return unquote(parsed.path.removeprefix(ARTICLE_PATH_PREFIX)).replace("_", " ") or None

    async def _get(self, path: str, params: dict[str, Any]) -> httpx.Response:
        try:
            return await self._follow_within_wikipedia(f"{self._settings.base_url}{path}", params)
        except httpx.HTTPError as error:
            raise WikipediaUnavailable(f"no answer from Wikipedia ({type(error).__name__})") from error

    async def _follow_within_wikipedia(self, url: str, params: dict[str, Any]) -> httpx.Response:
        """A redirected title (an old name, a different capitalisation) answers with a redirect to the article's own address."""
        headers = {"User-Agent": self._settings.user_agent}
        async with httpx.AsyncClient(timeout=self._settings.timeout_seconds, follow_redirects=False, headers=headers, transport=self._transport) as client:
            for _ in range(MAX_REDIRECTS + 1):
                response = await client.get(url, params=params)
                if not response.is_redirect:
                    return checked(response)
                url, params = urljoin(url, response.headers.get("location", "")), {}
                if urlparse(url).hostname != urlparse(self._settings.base_url).hostname:
                    raise WikipediaUnavailable(f"Wikipedia redirected off its own host, to {urlparse(url).hostname}")
        raise WikipediaUnavailable("too many redirects")


def checked(response: httpx.Response) -> httpx.Response:
    if response.status_code != OK:
        raise WikipediaUnavailable(f"Wikipedia answered {response.status_code} for {response.request.url.path}")
    return response
