"""Fetches Met.no's Locationforecast 2.0 for home or any other place, the way its terms of service ask (https://api.met.no/doc/TermsOfService).

The terms, and how this client meets them: identify the application in the User-Agent; send coordinates with at most four decimals; keep a
response until its Expires time instead of asking again; after that, ask with If-Modified-Since so an unchanged forecast comes back as an empty 304.
The "complete" product is used rather than "compact" because it carries each six-hour block's minimum and maximum temperature everywhere and the
probability of precipitation where Met.no computes it (the Nordic area; elsewhere the field is absent). The model never sees the raw document.
"""

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Protocol

import httpx

from weather_mcp.settings import WeatherSettings

METNO_FORECAST_URL = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
COORDINATE_DECIMALS = 4
REUSE_WITHOUT_EXPIRES = timedelta(minutes=10)
OK_STATUSES = (200, 203)  # 203 is Met.no's warning that the product version is deprecated; the body is still valid
NOT_MODIFIED = 304
PLACES_HELD = 32


class WeatherUnavailable(RuntimeError):
    """The forecast could not be fetched and no earlier copy is held."""


class ForecastStore(Protocol):
    """Pins one forecast per location for the life of the store. The benchmark passes its per-run cache so every candidate reads the same forecast;
    the product passes a disabled cache, and the in-memory copy below is all it keeps."""

    def get_forecast(self, location_key: str) -> dict[str, Any] | None: ...

    def put_forecast(self, location_key: str, forecast: dict[str, Any]) -> None: ...


@dataclass
class HeldForecast:
    body: dict[str, Any]
    expires: datetime
    last_modified: str | None


def utc_now() -> datetime:
    return datetime.now(UTC)


class MetnoClient:
    """One forecast held per place, for home and for every other place asked about, at most PLACES_HELD of them, the oldest dropped first."""

    def __init__(self, settings: WeatherSettings, store: ForecastStore, clock: Callable[[], datetime] = utc_now, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._settings = settings
        self._store = store
        self._clock = clock
        self._transport = transport
        self._held: OrderedDict[str, HeldForecast] = OrderedDict()

    async def forecast(self, latitude: float, longitude: float) -> dict[str, Any]:
        """The Locationforecast document for these coordinates: pinned, held until it expires, or fetched."""
        key = location_key(latitude, longitude)
        pinned = self._store.get_forecast(key)
        if pinned is not None:
            return pinned
        held = self._held.get(key)
        if held is not None and self._clock() < held.expires:
            return held.body
        body = await self._refresh(key)
        self._store.put_forecast(key, body)
        return body

    async def _refresh(self, key: str) -> dict[str, Any]:
        """A forecast issued an hour or two ago still describes the coming days well, so a failed refresh falls back to the copy already held."""
        try:
            return await self._fetch(key)
        except WeatherUnavailable:
            if key not in self._held:
                raise
            return self._held[key].body

    async def _fetch(self, key: str) -> dict[str, Any]:
        held = self._held.get(key)
        response = await self._request(key, held)
        if response.status_code == NOT_MODIFIED and held is not None:
            held.expires = expiry_of(response, self._clock())
            return held.body
        if response.status_code not in OK_STATUSES:
            raise WeatherUnavailable(f"Met.no answered {response.status_code}")
        self._hold(key, HeldForecast(body=response.json(), expires=expiry_of(response, self._clock()), last_modified=response.headers.get("last-modified")))
        return self._held[key].body

    def _hold(self, key: str, forecast: HeldForecast) -> None:
        self._held[key] = forecast
        self._held.move_to_end(key)
        while len(self._held) > PLACES_HELD:
            self._held.popitem(last=False)

    async def _request(self, key: str, held: HeldForecast | None) -> httpx.Response:
        latitude, longitude = key.split(",")
        headers = {"User-Agent": self._settings.user_agent}
        if held is not None and held.last_modified:
            headers["If-Modified-Since"] = held.last_modified
        try:
            async with httpx.AsyncClient(timeout=self._settings.timeout_seconds, transport=self._transport) as client:
                return await client.get(METNO_FORECAST_URL, params={"lat": latitude, "lon": longitude}, headers=headers)
        except httpx.HTTPError as error:
            raise WeatherUnavailable(f"no answer from Met.no ({type(error).__name__})") from error


def location_key(latitude: float, longitude: float) -> str:
    return f"{latitude:.{COORDINATE_DECIMALS}f},{longitude:.{COORDINATE_DECIMALS}f}"


def expiry_of(response: httpx.Response, now: datetime) -> datetime:
    try:
        return parsedate_to_datetime(response.headers["expires"])
    except (KeyError, TypeError, ValueError):
        return now + REUSE_WITHOUT_EXPIRES
