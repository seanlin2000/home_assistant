"""The restaurant tools' answers from the monthly snapshot: the restaurants a location names, or the nearest to any other place, and one restaurant in
full. Descriptions the snapshot lacks are read while answering (restaurants_mcp/descriptions.py).

Every failure is one sentence telling the model what to do next, never an exception, as the other listings tools do.
"""

import logging
from collections.abc import Awaitable, Callable

from restaurants_mcp.descriptions import DescriptionReader
from restaurants_mcp.locations import area_named, is_near_request, place_named_near
from restaurants_mcp.render import nearby_text, no_match_text, restaurant_details_text, restaurants_text, several_matches_text, short_list_note
from restaurants_mcp.restaurant_names import restaurants_named
from restaurants_mcp.restaurants import RestaurantsSnapshot
from restaurants_mcp.selection import RestaurantFilters, best_awarded_first, nearest_first
from restaurants_mcp.settings import RestaurantsSettings
from utils.geocoding_utils import Geocoder, GeocodingUnavailable, PlaceNotFound
from utils.snapshot_utils import SnapshotMissing, age_note, listing_today, read_snapshot
from utils.text_utils import clip_to_whole_lines

NO_SNAPSHOT_MESSAGE = "Restaurants error: the Michelin Guide has not been read yet. Tell the user the restaurant recommendations are not available right now."
PLACE_NOT_FOUND_MESSAGE = 'No place called "{place}" on the map. Ask the user for a city, a district, or a neighbourhood with its city, such as "West Village, Manhattan".'
MAP_DOWN_MESSAGE = "The map search did not answer, so places other than the guide's own cities and districts cannot be found right now. Ask the user for a city or a district."
_LOGGER = logging.getLogger(__name__)


class RestaurantAnswers:
    def __init__(self, settings: RestaurantsSettings, geocoder: Geocoder, descriptions: DescriptionReader) -> None:
        self.settings, self.geocoder, self.descriptions = settings, geocoder, descriptions

    async def recommendations(self, location: str, filters: RestaurantFilters, limit: int) -> str:
        return await self.answered(lambda snapshot: self.recommend(snapshot, location, filters, limit))

    async def details(self, asked: str, location: str) -> str:
        return await self.answered(lambda snapshot: self.describe(snapshot, asked, location))

    async def answered(self, answer: Callable[[RestaurantsSnapshot], Awaitable[str]]) -> str:
        """The answer within the word budget, then a note when the monthly refresh has not run for weeks, which no word budget cuts."""
        try:
            snapshot = read_snapshot(self.settings.snapshot_path, RestaurantsSnapshot)
        except SnapshotMissing as error:
            _LOGGER.warning("the restaurant tools have no snapshot: %s", error)
            return NO_SNAPSHOT_MESSAGE
        text = clip_to_whole_lines(await answer(snapshot), self.settings.max_words)
        stale_note = age_note(snapshot.refreshed_at, listing_today(self.settings), self.settings.stale_after_days)
        return with_note(text, stale_note)

    async def recommend(self, snapshot: RestaurantsSnapshot, location: str, filters: RestaurantFilters, limit: int) -> str:
        area = None if is_near_request(location) else area_named(snapshot.restaurants, location)
        if area is None:
            return await self.recommend_near(snapshot, place_named_near(location), filters, limit)
        found = best_awarded_first([restaurant for restaurant in area.restaurants if filters.admits(restaurant)])
        listed = await self.descriptions.with_descriptions(found[:limit], snapshot.refreshed_at)
        return with_note(restaurants_text(listed, len(found), area.label, filters), short_list_note(len(found), limit))

    async def recommend_near(self, snapshot: RestaurantsSnapshot, place_name: str, filters: RestaurantFilters, limit: int) -> str:
        try:
            place = await self.geocoder.locate(place_name)
        except PlaceNotFound:
            return PLACE_NOT_FOUND_MESSAGE.format(place=place_name)
        except GeocodingUnavailable as error:
            _LOGGER.warning("restaurants near %s: %s", place_name, error)
            return MAP_DOWN_MESSAGE
        nearby = nearest_first([restaurant for restaurant in snapshot.restaurants if filters.admits(restaurant)], place)
        described = await self.descriptions.with_descriptions([near.restaurant for near in nearby[:limit]], snapshot.refreshed_at)
        listed = [near.model_copy(update={"restaurant": restaurant}) for near, restaurant in zip(nearby, described)]
        return with_note(nearby_text(listed, len(nearby), place.label, filters), short_list_note(len(nearby), limit))

    async def describe(self, snapshot: RestaurantsSnapshot, asked: str, location: str) -> str:
        area = area_named(snapshot.restaurants, location) if location else None
        named = restaurants_named(area.restaurants if area else snapshot.restaurants, asked)
        if not named.restaurants:
            return no_match_text(asked)
        if len(named.restaurants) > 1:
            return several_matches_text(named.restaurants, asked)
        [restaurant] = await self.descriptions.with_descriptions(named.restaurants, snapshot.refreshed_at)
        return restaurant_details_text(restaurant)


def with_note(text: str, note: str) -> str:
    return f"{text}\n{note}" if note else text
