"""The monthly refresh of Michelin Guide restaurants: every guide city's listing, a page of 48 cards at a time, then the inspector's description of each
restaurant in New York and the Bay Area.

A description is read once and kept while the restaurant keeps its award, so after the first month only new or re-awarded restaurants cost a page.
A city whose listing cannot be read keeps last month's restaurants, and a restaurant page that cannot be read leaves its description to be read when
it is asked for. A bot check stops the whole refresh, since every later page would get one too; the last snapshot stays.

Requests go one at a time, two seconds apart, with the browser user agent Michelin's firewall serves (utils/browser_utils.py), and every redirect is
checked like the page reader's.
"""

import asyncio
import logging
from collections.abc import Iterable
from datetime import UTC, date, datetime

import httpx

from restaurants_mcp.cities import GUIDE_CITIES, GuideCity
from restaurants_mcp.michelin_pages import ListingPage, RestaurantPage, UnexpectedPage, read_listing_page, read_restaurant_page
from restaurants_mcp.restaurants import Restaurant, RestaurantsSnapshot
from restaurants_mcp.settings import RestaurantsSettings
from utils.browser_utils import chosen_user_agent
from utils.snapshot_utils import ListingsUnavailable, SnapshotMissing, read_snapshot, write_snapshot
from web_search_mcp.page_failures import is_bot_check
from web_search_mcp.url_guard import Resolver, UnsafeUrl, get_with_checked_redirects, system_resolver

OK = 200
_LOGGER = logging.getLogger(__name__)


class MichelinUnavailable(ListingsUnavailable):
    """Michelin answered with a bot check, pointed the refresh somewhere it must not go, or let no listing be read."""


class MichelinPageUnreadable(RuntimeError):
    """One page could not be read; the refresh keeps what it had for that page and goes on."""


def refresh_is_due(settings: RestaurantsSettings, today: date) -> bool:
    try:
        snapshot = read_snapshot(settings.snapshot_path, RestaurantsSnapshot)
    except SnapshotMissing:
        return True
    return (today - snapshot.refreshed_at.astimezone().date()).days >= settings.refresh_after_days


async def refresh_restaurants_snapshot(settings: RestaurantsSettings, transport: httpx.AsyncBaseTransport | None = None, resolver: Resolver = system_resolver) -> RestaurantsSnapshot:
    """Reads the guide and replaces the snapshot. A refresh that stops raises before anything is written, so the last good snapshot stays."""
    previous = last_restaurants(settings)
    headers = {"User-Agent": chosen_user_agent(settings.user_agent), "Accept-Language": "en-US,en;q=0.9"}
    async with httpx.AsyncClient(timeout=settings.timeout_seconds, follow_redirects=False, headers=headers, transport=transport) as client:
        guide = MichelinGuide(client, settings, resolver)
        listed = await guide.read_cities(GUIDE_CITIES, previous)
        restaurants = [await guide.described(restaurant, previous) for restaurant in listed]
    snapshot = RestaurantsSnapshot(refreshed_at=datetime.now(UTC), restaurants=restaurants)
    write_snapshot(settings.snapshot_path, snapshot)
    return snapshot


def last_restaurants(settings: RestaurantsSettings) -> dict[str, Restaurant]:
    """Last month's restaurants by their page's address, for the cities that cannot be read and the descriptions already read."""
    try:
        return {restaurant.url: restaurant for restaurant in read_snapshot(settings.snapshot_path, RestaurantsSnapshot).restaurants}
    except SnapshotMissing:
        return {}


class MichelinGuide:
    def __init__(self, client: httpx.AsyncClient, settings: RestaurantsSettings, resolver: Resolver) -> None:
        self.client, self.settings, self.resolver = client, settings, resolver

    async def read_cities(self, cities: Iterable[GuideCity], previous: dict[str, Restaurant]) -> list[Restaurant]:
        """Each restaurant once, under the first city that lists it."""
        restaurants: dict[str, Restaurant] = {}
        cities_read = 0
        for city in cities:
            try:
                city_restaurants = await self.read_city(city)
                cities_read += 1
            except MichelinPageUnreadable as error:
                _LOGGER.warning("%s: kept last month's restaurants: %s", city.name, error)
                city_restaurants = [restaurant for restaurant in previous.values() if restaurant.guide_city == city.name]
            for restaurant in city_restaurants:
                restaurants.setdefault(restaurant.url, restaurant)
        if not cities_read:
            raise MichelinUnavailable("no guide city's listing could be read")
        return list(restaurants.values())

    async def read_city(self, city: GuideCity) -> list[Restaurant]:
        """Every page of the city's listing, each restaurant once: a listing can repeat a card across its pages."""
        listing_url = f"{self.settings.guide_url}/{city.path}/restaurants"
        first_page = self.listing_page(await self.page_html(listing_url), city, listing_url)
        restaurants = {restaurant.url: restaurant for restaurant in first_page.restaurants}
        for page_number in range(2, first_page.last_page + 1):
            page_url = f"{listing_url}/page/{page_number}"
            restaurants.update((restaurant.url, restaurant) for restaurant in self.listing_page(await self.page_html(page_url), city, page_url).restaurants)
        _LOGGER.info("%s: %d restaurants on %d pages", city.name, len(restaurants), first_page.last_page)
        return list(restaurants.values())

    def listing_page(self, html: str, city: GuideCity, page_url: str) -> ListingPage:
        try:
            return read_listing_page(html, city, page_url)
        except UnexpectedPage as error:
            raise MichelinPageUnreadable(f"{page_url}: {error}") from error

    async def described(self, restaurant: Restaurant, previous: dict[str, Restaurant]) -> Restaurant:
        """The restaurant with its description: last month's while its award is unchanged, else read now, but only in the described areas."""
        if not restaurant.is_in_described_area:
            return restaurant
        known = previous.get(restaurant.url)
        if known and known.description and known.award == restaurant.award:
            return restaurant.model_copy(update={"description": known.description, "address": known.address})
        try:
            page = await self.restaurant_page(restaurant.url)
        except MichelinPageUnreadable as error:
            _LOGGER.warning("%s: no description this month: %s", restaurant.name, error)
            return restaurant
        return restaurant.model_copy(update={"description": page.description, "address": page.address})

    async def restaurant_page(self, url: str) -> RestaurantPage:
        html = await self.page_html(url)
        try:
            return read_restaurant_page(html)
        except UnexpectedPage as error:
            raise MichelinPageUnreadable(f"{url}: {error}") from error

    async def page_html(self, url: str) -> str:
        await asyncio.sleep(self.settings.seconds_between_requests)
        try:
            response = await get_with_checked_redirects(self.client, url, self.resolver, {})
        except UnsafeUrl as error:
            raise MichelinUnavailable(f"Michelin pointed the refresh at an address it must not read ({error})") from error
        except httpx.HTTPError as error:
            raise MichelinPageUnreadable(f"no answer for {url} ({type(error).__name__})") from error
        if is_bot_check(response):
            raise MichelinUnavailable("Michelin answered with a bot check; the browser user agent may be out of date")
        if response.status_code != OK:
            raise MichelinPageUnreadable(f"{url} answered {response.status_code}")
        return response.text
