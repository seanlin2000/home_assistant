"""Fetches Met.no's Locationforecast 2.0 for the home coordinates, the way its terms of service ask (https://api.met.no/doc/TermsOfService).

The terms, and how this client meets them: identify the application in the User-Agent; send coordinates with at most four decimals; keep a
response until its Expires time instead of asking again; after that, ask with If-Modified-Since so an unchanged forecast comes back as an empty 304.
The "complete" product is used rather than "compact" because it carries each six-hour block's minimum and maximum temperature everywhere and the
probability of precipitation where Met.no computes it (the Nordic area; elsewhere the field is absent). The model never sees the raw document.
"""

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
    def __init__(self, settings: WeatherSettings, store: ForecastStore, clock: Callable[[], datetime] = utc_now, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._settings = settings
        self._store = store
        self._clock = clock
        self._transport = transport
        self._held: HeldForecast | None = None

    @property
    def location_key(self) -> str:
        return f"{self._settings.latitude:.{COORDINATE_DECIMALS}f},{self._settings.longitude:.{COORDINATE_DECIMALS}f}"

    async def forecast(self) -> dict[str, Any]:
        """The Locationforecast document for home: pinned, held until it expires, or fetched."""
        pinned = self._store.get_forecast(self.location_key)
        if pinned is not None:
            return pinned
        if self._held is not None and self._clock() < self._held.expires:
            return self._held.body
        body = await self._refresh()
        self._store.put_forecast(self.location_key, body)
        return body

    async def _refresh(self) -> dict[str, Any]:
        """A forecast issued an hour or two ago still describes the coming days well, so a failed refresh falls back to the copy already held."""
        try:
            return await self._fetch()
        except WeatherUnavailable:
            if self._held is None:
                raise
            return self._held.body

    async def _fetch(self) -> dict[str, Any]:
        response = await self._request()
        if response.status_code == NOT_MODIFIED and self._held is not None:
            self._held.expires = expiry_of(response, self._clock())
            return self._held.body
        if response.status_code not in OK_STATUSES:
            raise WeatherUnavailable(f"Met.no answered {response.status_code}")
        self._held = HeldForecast(body=response.json(), expires=expiry_of(response, self._clock()), last_modified=response.headers.get("last-modified"))
        return self._held.body

    async def _request(self) -> httpx.Response:
        latitude, longitude = self.location_key.split(",")
        headers = {"User-Agent": self._settings.user_agent}
        if self._held is not None and self._held.last_modified:
            headers["If-Modified-Since"] = self._held.last_modified
        try:
            async with httpx.AsyncClient(timeout=self._settings.timeout_seconds, transport=self._transport) as client:
                return await client.get(METNO_FORECAST_URL, params={"lat": latitude, "lon": longitude}, headers=headers)
        except httpx.HTTPError as error:
            raise WeatherUnavailable(f"no answer from Met.no ({type(error).__name__})") from error


def expiry_of(response: httpx.Response, now: datetime) -> datetime:
    try:
        return parsedate_to_datetime(response.headers["expires"])
    except (KeyError, TypeError, ValueError):
        return now + REUSE_WITHOUT_EXPIRES
