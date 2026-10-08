"""Fixture search for the benchmark's injection questions: known pages on every run (design doc v2/03 section 3.3).

Only the benchmark's own copy of the tool server has it, started with WEB_SEARCH_FIXTURES_DIR. While a page set is selected through
POST /benchmark/fixture, every search returns that set's pages and a fetch of one of their addresses reads the file. Any other address is
fetched as usual, so a model that obeys a page's "fetch this address" shows in the log.
"""

import re
from collections.abc import Awaitable, Callable
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from web_search_mcp.searxng_client import SearchResult, SearxngClient

FIXTURE_ROUTE = "/benchmark/fixture"
FIXTURE_ENGINE = "fixture"
SET_NAME = re.compile(r"^[a-z0-9_-]+$")  # a file name in the fixtures folder, never a path


class FixturePage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    title: str
    snippet: str
    text: str


class FixtureSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pages: list[FixturePage]


class FixturePages:
    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._selected: FixtureSet | None = None

    def select(self, name: str | None) -> None:
        """Select the set in <name>.yaml, or none; raises FileNotFoundError for a set that does not exist."""
        if name is not None and not SET_NAME.match(name):
            raise FileNotFoundError(name)
        self._selected = None if name is None else load_fixture_set(self._directory / f"{name}.yaml")

    def results(self) -> list[SearchResult] | None:
        if self._selected is None:
            return None
        count = len(self._selected.pages)
        return [SearchResult(title=page.title, url=page.url, snippet=page.snippet, engines=[FIXTURE_ENGINE], score=float(count - rank)) for rank, page in enumerate(self._selected.pages)]

    def text_for(self, url: str) -> str | None:
        if self._selected is None:
            return None
        return next((page.text for page in self._selected.pages if page.url == url), None)


def load_fixture_set(path: Path) -> FixtureSet:
    return FixtureSet.model_validate(yaml.safe_load(path.read_text()))


class FixtureSearch:
    """Stands in front of the SearXNG client: the selected set's pages for any query, or the live search when no set is selected."""

    def __init__(self, live_search: SearxngClient, pages: FixturePages) -> None:
        self._live_search = live_search
        self._pages = pages

    async def search(self, query: str, time_range: str | None = None) -> list[SearchResult]:
        fixture_results = self._pages.results()
        return fixture_results if fixture_results is not None else await self._live_search.search(query, time_range)


def fixture_route(pages: FixturePages) -> Callable[[Request], Awaitable[Response]]:
    async def select_fixture(request: Request) -> Response:
        name = (await request.json()).get("set")
        try:
            pages.select(name)
        except FileNotFoundError:
            return JSONResponse({"error": f"no page set named {name!r}"}, status_code=404)
        return JSONResponse({"selected": name})

    return select_fixture
