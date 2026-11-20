"""Turns a spoken place name into coordinates and a time zone with Open-Meteo's geocoding service (design doc v2/03 section 3.2).

"Paris" is the first match, which Open-Meteo orders by population. "Paris, Texas" is the first match whose region, country, or country code starts
with the part after the comma. Places do not move, so every answer is kept: in memory for the life of the server, and in the benchmark's run cache.
"""

from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from weather_mcp.metno_client import COORDINATE_DECIMALS

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
MATCHES_TO_CONSIDER = 10
MAX_PLACE_CHARS = 80


class PlaceNotFound(LookupError):
    """No match for the spoken name."""


class GeocodingUnavailable(RuntimeError):
    """The geocoding service did not answer and the name is not cached."""


class Place(BaseModel):
    name: str
    region: str | None = None
    country: str | None = None
    country_code: str | None = None
    latitude: float
    longitude: float
    timezone: str

    @property
    def label(self) -> str:
        """How the forecast's heading names the place, e.g. "Lisbon, Lisbon, Portugal", so the answer can say which Lisbon it means."""
        return ", ".join(part for part in (self.name, self.region, self.country) if part)


class PlaceStore(Protocol):
    def get_place(self, spoken_name: str) -> dict[str, Any] | None: ...

    def put_place(self, spoken_name: str, place: dict[str, Any]) -> None: ...


class Geocoder:
    def __init__(self, store: PlaceStore, timeout_seconds: float, user_agent: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._store = store
        self._timeout = timeout_seconds
        self._user_agent = user_agent
        self._transport = transport
        self._known: dict[str, Place] = {}

    async def locate(self, spoken_name: str) -> Place:
        key = " ".join(spoken_name.lower().split())
        if key in self._known:
            return self._known[key]
        stored = self._store.get_place(key)
        place = Place.model_validate(stored) if stored else await self._look_up(spoken_name)
        self._store.put_place(key, place.model_dump())
        self._known[key] = place
        return place

    async def _look_up(self, spoken_name: str) -> Place:
        name, _, qualifier = spoken_name.partition(",")
        match = choose_match(await self._matches(name.strip()), qualifier.strip())
        if match is None:
            raise PlaceNotFound(spoken_name)
        return place_from_match(match)

    async def _matches(self, name: str) -> list[dict[str, Any]]:
        params = {"name": name, "count": MATCHES_TO_CONSIDER, "language": "en", "format": "json"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport, headers={"User-Agent": self._user_agent}) as client:
                response = await client.get(GEOCODING_URL, params=params)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise GeocodingUnavailable(f"no answer from Open-Meteo geocoding ({type(error).__name__})") from error
        return response.json().get("results") or []


def choose_match(matches: list[dict[str, Any]], qualifier: str) -> dict[str, Any] | None:
    if not qualifier:
        return matches[0] if matches else None
    wanted = qualifier.lower()
    return next((match for match in matches if any(str(match.get(field) or "").lower().startswith(wanted) for field in ("admin1", "country", "country_code"))), None)


def place_from_match(match: dict[str, Any]) -> Place:
    return Place(
        name=match["name"],
        region=match.get("admin1"),
        country=match.get("country"),
        country_code=match.get("country_code"),
        latitude=round(match["latitude"], COORDINATE_DECIMALS),
        longitude=round(match["longitude"], COORDINATE_DECIMALS),
        timezone=match.get("timezone") or "UTC",
    )
