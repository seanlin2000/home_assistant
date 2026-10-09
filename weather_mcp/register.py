"""Expose the forecast as an MCP tool on an existing server, alongside web search and the calculators, so the agent sees one tool list.

Without a place the forecast is for home, whose coordinates come from the environment and never appear in the conversation. With a place, the name
is looked up with Open-Meteo's geocoding first, and the forecast is grouped in that place's own time zone (design doc v2/03 section 3.2).
"""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Protocol
from zoneinfo import ZoneInfo

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from weather_mcp.forecast import ForecastReader, ForecastRequestError
from weather_mcp.geocoding import MAX_PLACE_CHARS, Geocoder, GeocodingUnavailable, PlaceNotFound, PlaceStore
from weather_mcp.metno_client import ForecastStore, MetnoClient, WeatherUnavailable, utc_now
from weather_mcp.settings import WeatherSettings

WEATHER_TOOL_NAME = "weather_forecast"
SERVICE_DOWN_MESSAGE = "Weather error: the forecast service did not answer. Tell the user you could not get the forecast right now."
PLACE_NOT_FOUND_MESSAGE = "Weather error: no place called {place} was found. Ask the user to say the place again, with its country."
GEOCODING_DOWN_MESSAGE = "Weather error: the forecast for {place} is unavailable right now, because the place lookup did not answer. Tell the user."
_LOGGER = logging.getLogger(__name__)


class WeatherStore(ForecastStore, PlaceStore, Protocol):
    """The tool server's cache: forecasts pinned per location and places pinned per spoken name."""


def register_weather_tools(server: MCPServer, settings: WeatherSettings, store: WeatherStore, clock: Callable[[], datetime] = utc_now) -> None:
    if not settings.has_location:
        _LOGGER.warning("%s is not offered: WEATHER_LATITUDE and WEATHER_LONGITUDE are unset (scripts/ha_setup.py --only weather writes them to .env)", WEATHER_TOOL_NAME)
        return
    client = MetnoClient(settings, store, clock)
    geocoder = Geocoder(store, settings.timeout_seconds, settings.user_agent)

    @server.tool(name=WEATHER_TOOL_NAME)
    async def weather_forecast(day: str = "today", part_of_day: str = "all", place: Annotated[str, Field(max_length=MAX_PLACE_CHARS)] = "") -> str:
        """Weather forecast for the user's home, or for any other place. day: "today", "tonight", "tomorrow", a weekday such as "saturday", "weekend", or "week" for the next seven days. part_of_day: "morning", "afternoon", "evening", "night" (the night after that day's evening), or "all". place: leave empty for home; otherwise the place as the user said it, with the region or country after a comma when it helps, e.g. "Lisbon" or "Portland, Maine". Times are the place's local time."""
        if not place.strip():
            return await home_forecast(client, settings, clock(), day, part_of_day)
        return await place_forecast(client, geocoder, settings, clock(), place.strip(), day, part_of_day)


async def home_forecast(client: MetnoClient, settings: WeatherSettings, now: datetime, day: str, part_of_day: str) -> str:
    try:
        document = await client.forecast(settings.latitude, settings.longitude)
    except WeatherUnavailable as error:
        _LOGGER.warning("%s failed: %s", WEATHER_TOOL_NAME, error)
        return SERVICE_DOWN_MESSAGE
    return described(ForecastReader(document, now, settings.zone(), settings.units), day, part_of_day)


async def place_forecast(client: MetnoClient, geocoder: Geocoder, settings: WeatherSettings, now: datetime, place: str, day: str, part_of_day: str) -> str:
    try:
        located = await geocoder.locate(place)
        document = await client.forecast(located.latitude, located.longitude)
    except PlaceNotFound:
        return PLACE_NOT_FOUND_MESSAGE.format(place=place)
    except GeocodingUnavailable as error:
        _LOGGER.warning("%s could not look up %r: %s", WEATHER_TOOL_NAME, place, error)
        return GEOCODING_DOWN_MESSAGE.format(place=place)
    except WeatherUnavailable as error:
        _LOGGER.warning("%s failed: %s", WEATHER_TOOL_NAME, error)
        return SERVICE_DOWN_MESSAGE
    return described(ForecastReader(document, now, ZoneInfo(located.timezone), settings.units, place_label=located.label), day, part_of_day)


def described(reader: ForecastReader, day: str, part_of_day: str) -> str:
    try:
        return reader.describe(day, part_of_day)
    except ForecastRequestError as error:
        return f"Weather error: {error}."
