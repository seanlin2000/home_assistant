"""The monthly Michelin refresh: cards read from a listing page with the carousel of other states skipped, descriptions read from restaurant pages
in the described areas and kept while the award is unchanged, a city that cannot be read keeping last month's restaurants, and a bot check or a
redirect to the home network stopping the refresh with the last snapshot kept.

The fixtures are guide.michelin.com pages recorded on 2026-11-01: page 1 of the New York listing, trimmed to four of its 48 cards, one carousel card,
and the pagination; and Le Bernardin's page, trimmed to its description and structured data."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from restaurants_mcp.cities import GUIDE_CITIES
from restaurants_mcp.michelin import MichelinUnavailable, refresh_is_due, refresh_restaurants_snapshot
from restaurants_mcp.michelin_pages import UnexpectedPage, price_level, read_listing_page, read_restaurant_page
from restaurants_mcp.restaurants import Award, RestaurantsSnapshot
from restaurants_mcp.settings import RestaurantsSettings
from utils.snapshot_utils import read_snapshot, write_snapshot

LISTING_HTML = Path("tests/fixtures/michelin_listing_new_york_page1.html").read_text()
RESTAURANT_HTML = Path("tests/fixtures/michelin_restaurant_le_bernardin.html").read_text()
NEW_YORK = GUIDE_CITIES[0]
LISTING_URL = "https://guide.michelin.com/us/en/new-york-state/new-york/restaurants"
CHICAGO_HTML = (
    LISTING_HTML.replace("/new-york-state/new-york/restaurant/", "/illinois/chicago/restaurant/")
    .replace("/new-york-state/brooklyn/restaurant/", "/illinois/chicago/restaurant/")
    .replace('data-dtm-region="New York State"', 'data-dtm-region="Illinois"')
)
LISTINGS = {"/new-york-state/new-york/restaurants": LISTING_HTML, "/illinois/chicago/restaurants": CHICAGO_HTML}
FIXTURE_NAMES = ["Icca", "Chambers", "Dim Sum Go Go", "The River Café"]


async def resolve_public(host: str) -> list[str]:
    return ["93.184.216.34"]


class FakeMichelin:
    """Serves the recorded New York listing for every page of New York's, the same cards moved to Illinois for Chicago's, and Le Bernardin's page
    for every restaurant; every other city answers 404. Remembers every request."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.failing_city = ""

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if self.failing_city and self.failing_city in path:
            return httpx.Response(503)
        if "/restaurant/" in path:
            return httpx.Response(200, text=RESTAURANT_HTML)
        listing = next((html for city, html in LISTINGS.items() if city in path), None)
        return httpx.Response(200, text=listing) if listing else httpx.Response(404)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def paths_containing(self, part: str) -> list[str]:
        return [request.url.path for request in self.requests if part in request.url.path]


def fixture_settings(tmp_path: Path) -> RestaurantsSettings:
    return RestaurantsSettings(snapshot_path=tmp_path / "restaurants.json", seconds_between_requests=0)


def test_a_listing_page_reads_its_own_cards_and_skips_the_carousel() -> None:
    page = read_listing_page(LISTING_HTML, NEW_YORK, LISTING_URL)

    assert [restaurant.name for restaurant in page.restaurants] == FIXTURE_NAMES  # the carousel's Johns Creek, Georgia card is not among them
    assert page.last_page == 8
    icca = page.restaurants[0]
    assert (icca.award, icca.price_level, icca.price_symbols, icca.cuisine) == (Award.ONE_STAR, 4, "$$$$", "Japanese")
    assert (icca.town, icca.district, icca.region, icca.guide_city) == ("New York", "Manhattan", "New York State", "New York")
    assert icca.url == "https://guide.michelin.com/us/en/new-york-state/new-york/restaurant/icca"
    assert (round(icca.latitude, 2), round(icca.longitude, 2)) == (40.71, -74.01)
    assert [restaurant.award for restaurant in page.restaurants[1:]] == [Award.SELECTED, Award.BIB_GOURMAND, Award.SELECTED]
    assert page.restaurants[3].district == "Brooklyn" and page.restaurants[3].is_in_described_area


def test_an_award_the_reader_does_not_know_fails_the_page_rather_than_guessing() -> None:
    with pytest.raises(UnexpectedPage, match="green star"):
        read_listing_page(LISTING_HTML.replace('data-dtm-distinction="1 star"', 'data-dtm-distinction="green star"'), NEW_YORK, LISTING_URL)


def test_a_card_without_a_price_category_counts_the_printed_symbols() -> None:
    assert (price_level("CAT_P02", "$$"), price_level("none", "€€€"), price_level("none", "")) == (2, 3, None)


def test_a_restaurant_page_gives_the_whole_description_and_the_street_address() -> None:
    page = read_restaurant_page(RESTAURANT_HTML)

    assert page.description.startswith("Well-heeled patrons continue to hold court") and page.description.endswith("technically assured finish.")
    assert page.address == "155 W. 51st St., New York"


async def test_the_refresh_reads_every_page_and_describes_the_new_york_restaurants(tmp_path: Path) -> None:
    server = FakeMichelin()
    snapshot = await refresh_restaurants_snapshot(fixture_settings(tmp_path), server.transport, resolve_public)

    assert len(server.paths_containing("/new-york-state/new-york/restaurants")) == 8
    new_york = [restaurant for restaurant in snapshot.restaurants if restaurant.guide_city == "New York"]
    assert [restaurant.name for restaurant in new_york] == FIXTURE_NAMES  # each restaurant once, though all eight pages repeat the fixture's cards
    assert all(restaurant.description.startswith("Well-heeled") for restaurant in new_york)
    assert not any(restaurant.description for restaurant in snapshot.restaurants if restaurant.guide_city == "Chicago")
    assert read_snapshot(tmp_path / "restaurants.json", RestaurantsSnapshot) == snapshot


async def test_a_description_is_kept_while_the_award_is_unchanged_and_read_again_when_it_changes(tmp_path: Path) -> None:
    settings = fixture_settings(tmp_path)
    await refresh_restaurants_snapshot(settings, FakeMichelin().transport, resolve_public)
    server = FakeMichelin()
    await refresh_restaurants_snapshot(settings, server.transport, resolve_public)
    assert server.paths_containing("/restaurant/") == []

    rewarded = FakeMichelin()
    await refresh_restaurants_snapshot(settings, httpx.MockTransport(lambda request: icca_with_two_stars(rewarded.handle(request))), resolve_public)
    assert rewarded.paths_containing("/restaurant/") == ["/us/en/new-york-state/new-york/restaurant/icca"]


def icca_with_two_stars(response: httpx.Response) -> httpx.Response:
    text = response.text.replace('data-dtm-distinction="1 star"', 'data-dtm-distinction="2 star"')
    return httpx.Response(response.status_code, text=text)


async def test_a_city_that_cannot_be_read_keeps_last_months_restaurants(tmp_path: Path) -> None:
    settings = fixture_settings(tmp_path)
    await refresh_restaurants_snapshot(settings, FakeMichelin().transport, resolve_public)
    server = FakeMichelin()
    server.failing_city = "/new-york-state/new-york/"
    snapshot = await refresh_restaurants_snapshot(settings, server.transport, resolve_public)

    assert [restaurant.name for restaurant in snapshot.restaurants if restaurant.guide_city == "New York"] == FIXTURE_NAMES


async def test_a_refresh_that_reads_no_city_writes_nothing(tmp_path: Path) -> None:
    with pytest.raises(MichelinUnavailable, match="no guide city"):
        await refresh_restaurants_snapshot(fixture_settings(tmp_path), httpx.MockTransport(lambda request: httpx.Response(404)), resolve_public)
    assert not (tmp_path / "restaurants.json").exists()


async def test_a_bot_check_stops_the_refresh_and_keeps_the_last_snapshot(tmp_path: Path) -> None:
    settings = fixture_settings(tmp_path)
    await refresh_restaurants_snapshot(settings, FakeMichelin().transport, resolve_public)
    kept = settings.snapshot_path.read_bytes()
    challenged = httpx.MockTransport(lambda request: httpx.Response(202, headers={"x-amzn-waf-action": "challenge"}))
    with pytest.raises(MichelinUnavailable, match="bot check"):
        await refresh_restaurants_snapshot(settings, challenged, resolve_public)
    assert settings.snapshot_path.read_bytes() == kept


async def test_a_redirect_to_the_home_network_stops_the_refresh(tmp_path: Path) -> None:
    redirecting = httpx.MockTransport(lambda request: httpx.Response(302, headers={"location": "http://192.168.1.1/admin"}))
    with pytest.raises(MichelinUnavailable, match="must not read"):
        await refresh_restaurants_snapshot(fixture_settings(tmp_path), redirecting, resolve_public)


def test_the_guide_is_read_again_only_once_the_snapshot_is_four_weeks_old(tmp_path: Path) -> None:
    settings = fixture_settings(tmp_path)
    assert refresh_is_due(settings, date(2026, 11, 1))
    write_snapshot(settings.snapshot_path, RestaurantsSnapshot(refreshed_at=datetime(2026, 11, 1, 12, tzinfo=UTC), restaurants=[]))

    assert not refresh_is_due(settings, date(2026, 11, 1) + timedelta(days=27))
    assert refresh_is_due(settings, date(2026, 11, 1) + timedelta(days=28))


async def test_a_restaurant_two_cities_list_is_kept_once_under_the_first(tmp_path: Path) -> None:
    both_list_new_york = httpx.MockTransport(lambda request: httpx.Response(200, text=LISTING_HTML) if "/restaurants" in request.url.path else httpx.Response(200, text=RESTAURANT_HTML))
    snapshot = await refresh_restaurants_snapshot(fixture_settings(tmp_path), both_list_new_york, resolve_public)

    assert [(restaurant.name, restaurant.guide_city) for restaurant in snapshot.restaurants] == [(name, "New York") for name in FIXTURE_NAMES]
