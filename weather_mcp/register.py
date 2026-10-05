"""Expose the home forecast as an MCP tool on an existing server, alongside web search and the calculators, so the agent sees one tool list."""

import logging
from collections.abc import Callable
from datetime import datetime

from mcp.server.mcpserver import MCPServer

from weather_mcp.forecast import ForecastReader, ForecastRequestError
from weather_mcp.metno_client import ForecastStore, MetnoClient, WeatherUnavailable, utc_now
from weather_mcp.settings import WeatherSettings

WEATHER_TOOL_NAME = "weather_forecast"
SERVICE_DOWN_MESSAGE = "Weather error: the forecast service did not answer. Tell the user you could not get the forecast right now."
_LOGGER = logging.getLogger(__name__)


def register_weather_tools(server: MCPServer, settings: WeatherSettings, store: ForecastStore, clock: Callable[[], datetime] = utc_now) -> None:
    if not settings.has_location:
        _LOGGER.warning("%s is not offered: WEATHER_LATITUDE and WEATHER_LONGITUDE are unset (scripts/ha_setup.py --only weather writes them to .env)", WEATHER_TOOL_NAME)
        return
    client = MetnoClient(settings, store, clock)

    @server.tool(name=WEATHER_TOOL_NAME)
    async def weather_forecast(day: str = "today", part_of_day: str = "all") -> str:
        """Weather forecast for the user's home only; for any other place, search the web. day: "today", "tomorrow", a weekday such as "saturday", "weekend", or "week" for the next seven days. part_of_day: "morning", "afternoon", "evening", "night" (the night after that day's evening), or "all". Times are local."""
        try:
            document = await client.forecast()
        except WeatherUnavailable as error:
            _LOGGER.warning("%s failed: %s", WEATHER_TOOL_NAME, error)
            return SERVICE_DOWN_MESSAGE
        return described(ForecastReader(document, clock(), settings.zone(), settings.units), day, part_of_day)


def described(reader: ForecastReader, day: str, part_of_day: str) -> str:
    try:
        return reader.describe(day, part_of_day)
    except ForecastRequestError as error:
        return f"Weather error: {error}."
