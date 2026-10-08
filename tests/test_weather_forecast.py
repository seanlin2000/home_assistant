"""The weather_forecast tool: Met.no's UTC blocks read as local days and parts of days, the week and weekend summaries, the terms-of-service caching,
and a server that leaves the tool out when home has no coordinates. The fixture is Met.no's "complete" forecast for central Oslo, recorded at
06:29 UTC on 2026-09-30 and trimmed to the fields the tool reads."""

import json
import logging
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
from mcp.server.mcpserver import MCPServer

from assistant_core.models import ToolCall
from assistant_core.tools import McpToolBox
from weather_mcp.forecast import ForecastReader, ForecastRequestError, condition_words
from weather_mcp.geocoding import Geocoder, PlaceNotFound, choose_match, place_from_match
from weather_mcp.metno_client import PLACES_HELD, MetnoClient, WeatherUnavailable
from weather_mcp.register import SERVICE_DOWN_MESSAGE, WEATHER_TOOL_NAME, register_weather_tools
from weather_mcp.settings import WeatherSettings, weather_settings_from_environment
from web_search_mcp.query_cache import QueryCache
from web_search_mcp.server import build_server
from web_search_mcp.settings import SearchSettings

FIXTURE = json.loads(Path("tests/fixtures/metno_oslo_complete.json").read_text())
OSLO = ZoneInfo("Europe/Oslo")
NEW_YORK = ZoneInfo("America/New_York")
WEDNESDAY_LUNCHTIME_IN_OSLO = datetime(2026, 9, 30, 10, 30, tzinfo=UTC)
OSLO_SETTINGS = WeatherSettings(latitude=59.913868, longitude=10.752245, timezone="Europe/Oslo", units="metric")


def reader(now: datetime = WEDNESDAY_LUNCHTIME_IN_OSLO, zone: ZoneInfo = OSLO, units: str = "metric") -> ForecastReader:
    return ForecastReader(FIXTURE, now, zone, units)


def test_part_of_day_is_read_in_local_time() -> None:
    oslo_afternoon = reader().describe("tomorrow", "afternoon")
    assert oslo_afternoon == (
        "Home weather forecast for tomorrow, Thursday October 1, local time:\n" "afternoon (noon to 6 pm): 15 to 18°C, partly cloudy, dry, 0% chance of precipitation, wind up to 14 km/h"
    )
    new_york_afternoon = reader(zone=NEW_YORK).describe("tomorrow", "afternoon")
    assert "afternoon (noon to 6 pm): 15 to 18°C, cloudy, dry, 3% chance of precipitation" in new_york_afternoon


def test_today_starts_with_now_and_drops_the_parts_that_have_passed() -> None:
    lines = reader().describe("today", "all").splitlines()
    assert lines[0] == "Home weather forecast for today, Wednesday September 30, local time:"
    assert lines[1].startswith("now: 13°C, cloudy")
    assert [line.split(" (")[0] for line in lines[2:]] == ["afternoon", "evening", "night"]
    assert reader().describe("today", "morning") == "The morning of Wednesday September 30 has already passed; there is no forecast for it."


def test_tonight_asked_after_midnight_means_the_night_in_progress() -> None:
    two_am_in_oslo = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
    assert "overnight (midnight to 6 am)" in reader(now=two_am_in_oslo).describe("today", "night")


def test_week_has_one_line_per_day_starting_with_the_rest_of_today() -> None:
    lines = reader(units="imperial").describe("week", "all").splitlines()
    assert len(lines) == 8
    assert lines[1] == "Wednesday September 30 (rest of today): 56 to 60°F, cloudy, dry, 0% chance of precipitation"
    assert lines[3] == "Friday October 2: 56 to 60°F, cloudy with heavy rain at times, 0.44 in of precipitation, 66% chance of precipitation"


def test_weekend_is_saturday_and_sunday_or_only_the_rest_of_sunday() -> None:
    weekend = reader().describe("weekend", "all").splitlines()
    assert [line.split(":")[0] for line in weekend[1:]] == ["Saturday October 3", "Sunday October 4"]
    sunday_morning = datetime(2026, 10, 4, 7, 0, tzinfo=UTC)
    assert reader(now=sunday_morning).describe("weekend", "all").splitlines()[1].startswith("Sunday October 4 (rest of today)")


def test_days_past_the_forecast_say_so_instead_of_guessing() -> None:
    sunday_morning = datetime(2026, 10, 4, 7, 0, tzinfo=UTC)
    assert reader(now=sunday_morning).describe("saturday", "all") == "No forecast for Saturday October 10 yet: it is beyond the forecast, which reaches only to Friday October 9."


def test_arguments_the_model_must_correct_are_named_plainly() -> None:
    with pytest.raises(ForecastRequestError, match="today, tomorrow, a weekday name"):
        reader().describe("next month", "all")
    with pytest.raises(ForecastRequestError, match="morning, afternoon, evening, night, or all"):
        reader().describe("today", "lunch")
    assert reader().describe(" Tomorrow ", "Whole Day").startswith("Home weather forecast for tomorrow")


def test_symbol_codes_become_plain_words() -> None:
    assert condition_words("partlycloudy_day") == "partly cloudy"
    assert condition_words("lightrainshowers_night") == "light rain showers"
    assert condition_words("heavysnowandthunder") == "heavy snow with thunder"
    assert condition_words("lightssleetshowersandthunder_polartwilight") == "light sleet showers with thunder"


class FakeMetno:
    """Answers like api.met.no and records every request it sees."""

    def __init__(self, now: datetime) -> None:
        self.now = now
        self.requests: list[httpx.Request] = []
        self.status = 200

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status >= 500:
            return httpx.Response(self.status)
        headers = {"Expires": format_datetime(self.now + timedelta(minutes=30), usegmt=True), "Last-Modified": "Wed, 30 Sep 2026 06:24:27 GMT"}
        if request.headers.get("If-Modified-Since") == headers["Last-Modified"]:
            return httpx.Response(304, headers=headers)
        return httpx.Response(200, json=FIXTURE, headers=headers)

    def clock(self) -> datetime:
        return self.now


OSLO = (OSLO_SETTINGS.latitude, OSLO_SETTINGS.longitude)


def metno_client(fake: FakeMetno, store: QueryCache | None = None) -> MetnoClient:
    return MetnoClient(OSLO_SETTINGS, store or QueryCache(None), fake.clock, transport=httpx.MockTransport(fake.handle))


async def test_request_rounds_coordinates_and_identifies_the_app_without_personal_details() -> None:
    fake = FakeMetno(WEDNESDAY_LUNCHTIME_IN_OSLO)
    await metno_client(fake).forecast(*OSLO)
    request = fake.requests[0]
    assert request.url.path == "/weatherapi/locationforecast/2.0/complete"
    assert dict(request.url.params) == {"lat": "59.9139", "lon": "10.7522"}
    assert request.headers["User-Agent"] == "studio-assistant-weather/1.0 github.com/seanlin2000/home_assistant" and "@" not in request.headers["User-Agent"]


async def test_forecast_is_reused_until_it_expires_then_revalidated_with_if_modified_since() -> None:
    fake = FakeMetno(WEDNESDAY_LUNCHTIME_IN_OSLO)
    client = metno_client(fake)
    first = await client.forecast(*OSLO)
    fake.now += timedelta(minutes=20)
    assert await client.forecast(*OSLO) is first and len(fake.requests) == 1
    fake.now += timedelta(minutes=20)
    assert await client.forecast(*OSLO) is first
    assert len(fake.requests) == 2 and fake.requests[1].headers["If-Modified-Since"] == "Wed, 30 Sep 2026 06:24:27 GMT"
    fake.now += timedelta(minutes=10)
    await client.forecast(*OSLO)
    assert len(fake.requests) == 2, "the 304 carried a new Expires, so the copy is fresh again"


async def test_a_failed_refresh_keeps_the_copy_already_held_and_fails_only_without_one() -> None:
    fake = FakeMetno(WEDNESDAY_LUNCHTIME_IN_OSLO)
    client = metno_client(fake)
    held = await client.forecast(*OSLO)
    fake.now += timedelta(hours=1)
    fake.status = 503
    assert await client.forecast(*OSLO) is held
    with pytest.raises(WeatherUnavailable, match="503"):
        await metno_client(fake).forecast(*OSLO)


async def test_a_pinned_store_serves_every_later_call_without_the_network(tmp_path: Path) -> None:
    fake = FakeMetno(WEDNESDAY_LUNCHTIME_IN_OSLO)
    store = QueryCache(str(tmp_path))
    await metno_client(fake, store).forecast(*OSLO)
    fake.now += timedelta(days=1)
    assert await metno_client(fake, store).forecast(*OSLO) == FIXTURE and len(fake.requests) == 1


async def call_weather_tool(settings: WeatherSettings, store: QueryCache, arguments: dict[str, Any]) -> str:
    server = MCPServer("weather-test")
    register_weather_tools(server, settings, store, clock=lambda: WEDNESDAY_LUNCHTIME_IN_OSLO)
    async with McpToolBox(server) as toolbox:
        return await toolbox.call(ToolCall(id="1", name=WEATHER_TOOL_NAME, arguments=arguments))


async def test_tool_answers_from_the_forecast_and_relays_bad_arguments(tmp_path: Path) -> None:
    store = QueryCache(str(tmp_path))
    store.put_forecast("59.9139,10.7522", FIXTURE)
    answer = await call_weather_tool(OSLO_SETTINGS, store, {"day": "tomorrow", "part_of_day": "afternoon"})
    assert answer.startswith("Home weather forecast for tomorrow, Thursday October 1")
    assert (await call_weather_tool(OSLO_SETTINGS, store, {"day": "yesterday"})).startswith('Weather error: day "yesterday" is not one of')


async def test_tool_says_so_in_one_sentence_when_met_no_is_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    async def unreachable(self: MetnoClient, latitude: float, longitude: float) -> dict[str, Any]:
        raise WeatherUnavailable("no answer from Met.no (ConnectTimeout)")

    monkeypatch.setattr(MetnoClient, "forecast", unreachable)
    assert await call_weather_tool(OSLO_SETTINGS, QueryCache(None), {}) == SERVICE_DOWN_MESSAGE


async def test_server_offers_the_tool_only_when_home_has_coordinates(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        without_home = build_server(SearchSettings(), weather=WeatherSettings())
    async with McpToolBox(without_home) as toolbox:
        assert WEATHER_TOOL_NAME not in [spec.name for spec in await toolbox.list_tools()]
    assert "WEATHER_LATITUDE and WEATHER_LONGITUDE are unset" in caplog.text
    async with McpToolBox(build_server(SearchSettings(), weather=OSLO_SETTINGS)) as toolbox:
        spec = next(spec for spec in await toolbox.list_tools() if spec.name == WEATHER_TOOL_NAME)
    assert set(spec.input_schema["properties"]) == {"day", "part_of_day", "place"}


def test_settings_come_from_weather_variables_and_empty_values_count_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEATHER_LATITUDE", "40.7484")
    monkeypatch.setenv("WEATHER_LONGITUDE", "")
    monkeypatch.setenv("WEATHER_UNITS", "imperial")
    settings = weather_settings_from_environment()
    assert settings.latitude == 40.7484 and settings.longitude is None and not settings.has_location and settings.units == "imperial"
    monkeypatch.setenv("WEATHER_TIMEZONE", "America/New_York")
    assert weather_settings_from_environment().zone() == NEW_YORK


LISBON_MATCHES = [
    {"name": "Lisbon", "admin1": "Lisbon", "country": "Portugal", "country_code": "PT", "latitude": 38.71667, "longitude": -9.13333, "timezone": "Europe/Lisbon"},
    {"name": "Lisbon", "admin1": "Maine", "country": "United States", "country_code": "US", "latitude": 44.03146, "longitude": -70.10423, "timezone": "America/New_York"},
]


def test_the_part_after_the_comma_picks_the_region_country_or_code() -> None:
    assert choose_match(LISBON_MATCHES, "")["country_code"] == "PT"
    assert choose_match(LISBON_MATCHES, "Maine")["admin1"] == "Maine"
    assert choose_match(LISBON_MATCHES, "us")["admin1"] == "Maine"
    assert choose_match(LISBON_MATCHES, "Texas") is None
    assert place_from_match(LISBON_MATCHES[0]).label == "Lisbon, Lisbon, Portugal"


async def test_a_place_is_looked_up_once_then_remembered(tmp_path: Path) -> None:
    requests = []

    def geocoding(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": LISBON_MATCHES})

    store = QueryCache(str(tmp_path))
    geocoder = Geocoder(store, 5.0, "test", transport=httpx.MockTransport(geocoding))
    first = await geocoder.locate("Lisbon, Maine")
    assert (first.latitude, first.longitude) == (44.0315, -70.1042)
    assert dict(requests[0].url.params) == {"name": "Lisbon", "count": "10", "language": "en", "format": "json"}
    assert await Geocoder(store, 5.0, "test", transport=httpx.MockTransport(geocoding)).locate("lisbon,  maine") == first
    assert len(requests) == 1


async def test_an_unknown_place_is_a_sentence_the_model_can_repeat(tmp_path: Path) -> None:
    geocoder = Geocoder(QueryCache(None), 5.0, "test", transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})))
    with pytest.raises(PlaceNotFound):
        await geocoder.locate("Lisbonn")


async def test_the_forecast_for_a_named_place_names_it_in_the_heading(tmp_path: Path) -> None:
    store = QueryCache(str(tmp_path))
    store.put_place("oslo, norway", {"name": "Oslo", "region": "Oslo", "country": "Norway", "country_code": "NO", "latitude": 59.9139, "longitude": 10.7522, "timezone": "Europe/Oslo"})
    store.put_forecast("59.9139,10.7522", FIXTURE)
    home_elsewhere = OSLO_SETTINGS.model_copy(update={"latitude": 40.7484, "longitude": -73.9857, "timezone": "America/New_York"})
    answer = await call_weather_tool(home_elsewhere, store, {"day": "tomorrow", "part_of_day": "afternoon", "place": "Oslo, Norway"})
    assert answer.startswith("Forecast for Oslo, Oslo, Norway, tomorrow, Thursday October 1, local time:")


async def test_the_client_holds_at_most_thirty_two_places(tmp_path: Path) -> None:
    fake = FakeMetno(WEDNESDAY_LUNCHTIME_IN_OSLO)
    client = metno_client(fake)
    for index in range(PLACES_HELD + 1):
        await client.forecast(10.0 + index, 20.0)
    await client.forecast(10.0, 20.0)
    assert len(fake.requests) == PLACES_HELD + 2, "the first place was dropped when the thirty-third arrived"
