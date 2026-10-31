"""Reads Fandango's theater listings near Times Square for the nightly refresh, as far ahead as theaters sell tickets, and keeps each Manhattan movie
once, with every theater showing it, its Rotten Tomatoes scores, and what its own page says about it.

The listing is the JSON Fandango's own zip-code page reads (fandango.com/napi/theaterswithshowtimes), undocumented and keyless. It answers only a
session that has opened that page first, so the refresh reads the page once for its cookies. Each day is two pages of 50 theaters sorted by distance;
only the theaters with a Manhattan zip code (100xx to 102xx) are kept, 23 of them on 2026-10-25. Showtimes are read but not kept.

After the listing come two reads per movie: its scores every night, and its page only the first night it is listed, since a synopsis and a cast do
not change. A movie whose scores or page cannot be read is kept without them, and its page is tried again the next night.
"""

import asyncio
import logging
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urljoin

import httpx

from movies_mcp.movie_page import MoviePageUnreadable, movie_page_from_html, scores_from_ratings
from movies_mcp.movies import Movie, MoviePage, MoviesSnapshot, RottenTomatoesScores
from movies_mcp.settings import MoviesSettings
from utils.browser_utils import chosen_user_agent
from utils.snapshot_utils import ListingsUnavailable, SnapshotMissing, listing_today, read_snapshot, write_snapshot
from web_search_mcp.url_guard import Resolver, UnsafeUrl, ensure_public_url, refuse_unless_public_peer, system_resolver

OK = 200
MAX_REDIRECTS = 5
MANHATTAN_ZIP_CODE = re.compile(r"10[0-2]\d\d")
YEAR_AFTER_TITLE = re.compile(r"\s*\((?:19|20)\d\d\)$")  # "Clayface (2026)"
_LOGGER = logging.getLogger(__name__)


class FandangoUnavailable(ListingsUnavailable):
    """Fandango did not answer, refused, or answered in a shape the refresh cannot read."""


async def refresh_movies_snapshot(settings: MoviesSettings, transport: httpx.AsyncBaseTransport | None = None, resolver: Resolver = system_resolver) -> MoviesSnapshot:
    """Reads the listings and replaces the snapshot. A failed listing read raises before anything is written, so the last good snapshot stays."""
    first_day = listing_today(settings)
    days = [first_day + timedelta(days=offset) for offset in range(settings.days)]
    pages_read = pages_already_read(settings)
    async with httpx.AsyncClient(timeout=settings.timeout_seconds, follow_redirects=False, headers={"User-Agent": chosen_user_agent(settings.user_agent)}, transport=transport) as client:
        session = FandangoSession(client, settings, resolver)
        listings = ManhattanListings(await session.read_days(days))
        for movie in listings.movies.values():
            await session.add_details(movie, pages_read)
    snapshot = listings.snapshot(refreshed_at=datetime.now(UTC))
    write_snapshot(settings.snapshot_path, snapshot)
    return snapshot


def pages_already_read(settings: MoviesSettings) -> dict[int, MoviePage]:
    try:
        previous = read_snapshot(settings.snapshot_path, MoviesSnapshot)
    except SnapshotMissing:
        return {}
    return {movie.fandango_id: movie.page for movie in previous.movies if movie.page}


class FandangoSession:
    """One night's requests: the zip-code page for its cookies, then each day's theaters a page at a time, then each movie's details, one request
    after another."""

    def __init__(self, client: httpx.AsyncClient, settings: MoviesSettings, resolver: Resolver) -> None:
        self.client, self.settings, self.resolver = client, settings, resolver
        self.listing_page = settings.listing_page_url.format(zip_code=settings.zip_code)

    async def read_days(self, days: list[date]) -> dict[date, list[dict[str, Any]]]:
        await self.open()
        return {day: await self.read_day(day) for day in days}

    async def open(self) -> None:
        response = await self.request(self.listing_page, {}, "text/html")
        if response.status_code != OK:
            raise FandangoUnavailable(f"Fandango's listing page answered {response.status_code}")

    async def read_day(self, day: date) -> list[dict[str, Any]]:
        theaters: list[dict[str, Any]] = []
        page, total_pages = 1, 1
        while page <= total_pages:
            page_theaters, total_pages = await self.read_page(day, page)
            theaters.extend(page_theaters)
            page += 1
        return theaters

    async def read_page(self, day: date, page: int) -> tuple[list[dict[str, Any]], int]:
        params = {
            "zipCode": self.settings.zip_code,
            "date": day.isoformat(),
            "page": page,
            "limit": self.settings.theaters_per_request,
            "isdesktop": "true",
            "filter": "open-theaters",
            "filterEnabled": "true",
        }
        response = await self.paced_request(self.settings.theaters_url, params, "application/json")
        if response.status_code != OK:
            raise FandangoUnavailable(f"Fandango answered {response.status_code} for {day}, page {page}: {response.text[:120]}")
        try:
            body = response.json()
            return list(body["theaters"]), int(body["pagination"]["totalPages"])
        except (ValueError, KeyError, TypeError) as error:
            raise FandangoUnavailable(f"Fandango's listing for {day} was not in the expected shape ({type(error).__name__}: {error})") from error

    async def add_details(self, movie: Movie, pages_read: dict[int, MoviePage]) -> None:
        await self.add_scores(movie)
        movie.page = pages_read.get(movie.fandango_id)
        if not movie.page and movie.page_path:
            await self.add_page(movie)

    async def add_scores(self, movie: Movie) -> None:
        try:
            movie.scores = await self.read_scores(movie.fandango_id)
        except FandangoUnavailable as error:
            _LOGGER.warning("kept %s without its scores: %s", movie.title, error)

    async def add_page(self, movie: Movie) -> None:
        try:
            movie.page = await self.read_movie_page(movie.page_path)
        except (FandangoUnavailable, MoviePageUnreadable) as error:
            _LOGGER.warning("kept %s without its page: %s", movie.title, error)

    async def read_scores(self, movie_id: int) -> RottenTomatoesScores | None:
        response = await self.paced_request(self.settings.ratings_url.format(movie_id=movie_id), {}, "application/json")
        if response.status_code != OK:
            raise FandangoUnavailable(f"Fandango's scores answered {response.status_code}")
        try:
            return scores_from_ratings(response.json())
        except (ValueError, AttributeError) as error:
            raise FandangoUnavailable(f"Fandango's scores were not in the expected shape ({type(error).__name__})") from error

    async def read_movie_page(self, page_path: str) -> MoviePage:
        response = await self.paced_request(self.settings.movie_page_url.format(page_path=page_path), {}, "text/html")
        if response.status_code != OK:
            raise FandangoUnavailable(f"the movie's page answered {response.status_code}")
        return movie_page_from_html(response.text)

    async def paced_request(self, url: str, params: dict[str, Any], accept: str) -> httpx.Response:
        await asyncio.sleep(self.settings.seconds_between_requests)
        return await self.request(url, params, accept)

    async def request(self, url: str, params: dict[str, Any], accept: str) -> httpx.Response:
        """Follows Fandango's redirects by hand, as the page reader does, so a redirect cannot point the refresh at an address on the home network."""
        url = str(httpx.URL(url, params=params))
        for _ in range(MAX_REDIRECTS + 1):
            response = await self.request_once(url, accept)
            if not response.is_redirect:
                return response
            url = urljoin(url, response.headers.get("location", ""))
        raise FandangoUnavailable("Fandango redirected too many times")

    async def request_once(self, url: str, accept: str) -> httpx.Response:
        """The address is checked before connecting and the connection's peer after; cookies stay matched to Fandango's name, so the connection is
        not pinned to the checked address as the page reader's is."""
        try:
            await ensure_public_url(url, self.resolver)
            response = await self.client.get(url, headers={"Accept": accept, "Referer": self.listing_page})
            refuse_unless_public_peer(response)
            return response
        except UnsafeUrl as error:
            raise FandangoUnavailable(f"Fandango pointed the refresh at an address it must not read ({error})") from error
        except httpx.HTTPError as error:
            raise FandangoUnavailable(f"no answer from Fandango ({type(error).__name__})") from error


class ManhattanListings:
    """The days' listings folded into one entry per movie: each Manhattan theater showing it, with the first day it shows there."""

    def __init__(self, listings: dict[date, list[dict[str, Any]]]) -> None:
        self.days = sorted(listings)
        self.movies: dict[str, Movie] = {}
        self.theaters: set[str] = set()
        for day in self.days:
            for theater in filter(is_open_in_manhattan, listings[day]):
                self.add_theater(day, theater)

    def add_theater(self, day: date, theater: dict[str, Any]) -> None:
        name = " ".join(theater["name"].split())
        self.theaters.add(name)
        for product in theater.get("movies") or []:  # an open theater with nothing posted for the day has no movies key
            self.add_showing(day, name, product)

    def add_showing(self, day: date, theater: str, product: dict[str, Any]) -> None:
        title = listed_title(product["title"])
        movie = self.movies.setdefault(title, movie_from_product(title, product))
        movie.genres = sorted(set(movie.genres) | set(product.get("genres") or []))
        movie.theaters.setdefault(theater, day)  # days are read in order, so the first one kept is the earliest

    def snapshot(self, refreshed_at: datetime) -> MoviesSnapshot:
        return MoviesSnapshot(refreshed_at=refreshed_at, first_day=self.days[0], last_day=self.days[-1], theaters=sorted(self.theaters), movies=list(self.movies.values()))


def is_open_in_manhattan(theater: dict[str, Any]) -> bool:
    return bool(MANHATTAN_ZIP_CODE.fullmatch(theater.get("zip") or "")) and not theater.get("isTemporarilyClosed")


def movie_from_product(title: str, product: dict[str, Any]) -> Movie:
    release = product.get("releaseDate")
    return Movie(
        fandango_id=int(product["id"]),
        page_path=product.get("mopURI") or "",
        title=title,
        genres=[],
        rating=(product.get("rating") or "").strip(),
        release_date=date.fromisoformat(release[:10]) if release else None,
        runtime_minutes=product.get("runtime") or None,
        theaters={},
    )


def listed_title(text: str) -> str:
    return YEAR_AFTER_TITLE.sub("", " ".join(text.split()))
