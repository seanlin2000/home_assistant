"""Inspector's descriptions for restaurants outside New York and the Bay Area, read from their Michelin pages while answering and kept until the next
monthly refresh.

The refresh reads descriptions ahead only where the user eats most often; elsewhere a description costs one page the first time it is asked for. The
pages are read a few at a time, so a list of ten takes a few seconds, and kept in a file stamped with the snapshot they belong to, so the next
refresh starts them afresh. A page that cannot be read leaves its restaurant without a description in that answer and is tried again next time.
"""

import asyncio
import logging
from datetime import datetime

import httpx

from restaurants_mcp.michelin import MichelinGuide, MichelinPageUnreadable, MichelinUnavailable
from restaurants_mcp.michelin_pages import RestaurantPage
from restaurants_mcp.restaurants import Restaurant
from restaurants_mcp.settings import RestaurantsSettings
from utils.browser_utils import chosen_user_agent
from utils.snapshot_utils import DatedSnapshot, SnapshotMissing, read_snapshot, write_snapshot
from web_search_mcp.url_guard import Resolver, system_resolver

_LOGGER = logging.getLogger(__name__)


class DescriptionCache(DatedSnapshot):
    """refreshed_at is the restaurants snapshot's, so pages read for last month's snapshot are not served with this month's."""

    pages: dict[str, RestaurantPage]


class DescriptionReader:
    def __init__(self, settings: RestaurantsSettings, transport: httpx.AsyncBaseTransport | None = None, resolver: Resolver = system_resolver) -> None:
        self.settings, self.transport, self.resolver = settings, transport, resolver

    async def with_descriptions(self, restaurants: list[Restaurant], snapshot_refreshed_at: datetime) -> list[Restaurant]:
        cache = self.cache_for(snapshot_refreshed_at)
        missing = [restaurant.url for restaurant in restaurants if not restaurant.description and restaurant.url not in cache.pages]
        if missing:
            cache.pages.update(await self.read_pages(missing))
            write_snapshot(self.settings.descriptions_path, cache)
        return [described_by(restaurant, cache.pages.get(restaurant.url)) for restaurant in restaurants]

    def cache_for(self, snapshot_refreshed_at: datetime) -> DescriptionCache:
        try:
            cache = read_snapshot(self.settings.descriptions_path, DescriptionCache)
        except SnapshotMissing:
            return DescriptionCache(refreshed_at=snapshot_refreshed_at, pages={})
        return cache if cache.refreshed_at == snapshot_refreshed_at else DescriptionCache(refreshed_at=snapshot_refreshed_at, pages={})

    async def read_pages(self, urls: list[str]) -> dict[str, RestaurantPage]:
        headers = {"User-Agent": chosen_user_agent(self.settings.user_agent), "Accept-Language": "en-US,en;q=0.9"}
        at_once = asyncio.Semaphore(self.settings.pages_read_at_once)
        unpaced = self.settings.model_copy(update={"seconds_between_requests": 0.0})  # the semaphore spaces these reads, not a pause before each
        async with httpx.AsyncClient(timeout=self.settings.timeout_seconds, follow_redirects=False, headers=headers, transport=self.transport) as client:
            guide = MichelinGuide(client, unpaced, self.resolver)
            pages = await asyncio.gather(*(self.read_page(guide, url, at_once) for url in urls))
        return {url: page for url, page in zip(urls, pages) if page is not None}

    async def read_page(self, guide: MichelinGuide, url: str, at_once: asyncio.Semaphore) -> RestaurantPage | None:
        async with at_once:
            try:
                return await guide.restaurant_page(url)
            except (MichelinPageUnreadable, MichelinUnavailable) as error:
                _LOGGER.warning("no description for %s: %s", url, error)
                return None


def described_by(restaurant: Restaurant, page: RestaurantPage | None) -> Restaurant:
    if restaurant.description or page is None:
        return restaurant
    return restaurant.model_copy(update={"description": page.description, "address": page.address})
