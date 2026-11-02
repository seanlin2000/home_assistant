"""Turns a spoken place, down to a neighbourhood or a landmark, into coordinates with OpenStreetMap's Nominatim, for the restaurant tool's "near a
place" answers.

The weather tool's Open-Meteo geocoder knows towns but not neighbourhoods: on 2026-11-01 it put "Mountain View" in Arkansas and "West Village" in
Ireland, and found no "Williamsburg, New York" or "Union Square, New York", all of which Nominatim placed correctly. Nominatim's usage policy
(operations.osmfoundation.org/policies/nominatim) asks for an identifying User-Agent, at most one request a second, and kept answers; places do not
move, so every answer is kept for the life of the server.
"""

import asyncio
import time
from typing import Any

import httpx
from pydantic import BaseModel

from utils.user_agent_utils import descriptive_user_agent

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = descriptive_user_agent("geocoding")
SECONDS_BETWEEN_REQUESTS = 1.0
MATCHES_TO_CONSIDER = 5
AREA_CATEGORIES = ("place", "boundary")  # a neighbourhood or a town, preferred over a shop or a charging station that carries the name
SETTLEMENT_KEYS = ("city", "town", "village")  # the first of these a place's address has names the settlement it is in


class PlaceNotFound(LookupError):
    """Nominatim knows no place by that name."""


class GeocodingUnavailable(RuntimeError):
    """Nominatim did not answer."""


class Coordinates(BaseModel):
    label: str
    latitude: float
    longitude: float


class Geocoder:
    def __init__(self, timeout_seconds: float, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._timeout = timeout_seconds
        self._transport = transport
        self._known: dict[str, Coordinates] = {}
        self._lock = asyncio.Lock()
        self._last_request = 0.0

    async def locate(self, spoken_place: str) -> Coordinates:
        key = " ".join(spoken_place.lower().split())
        if key not in self._known:
            self._known[key] = coordinates_of(chosen_match(await self._matches(spoken_place), spoken_place))
        return self._known[key]

    async def _matches(self, spoken_place: str) -> list[dict[str, Any]]:
        async with self._lock:
            await asyncio.sleep(max(0.0, self._last_request + SECONDS_BETWEEN_REQUESTS - time.monotonic()))
            self._last_request = time.monotonic()
            params = {"q": spoken_place, "format": "jsonv2", "limit": MATCHES_TO_CONSIDER, "addressdetails": 1, "accept-language": "en"}
            try:
                async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport, headers={"User-Agent": USER_AGENT}) as client:
                    response = await client.get(NOMINATIM_SEARCH_URL, params=params)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as error:
                raise GeocodingUnavailable(f"no answer from Nominatim ({type(error).__name__})") from error


def chosen_match(matches: list[dict[str, Any]], spoken_place: str) -> dict[str, Any]:
    if not matches:
        raise PlaceNotFound(spoken_place)
    return next((match for match in matches if match.get("category") in AREA_CATEGORIES), matches[0])


def coordinates_of(match: dict[str, Any]) -> Coordinates:
    return Coordinates(label=spoken_label(match), latitude=float(match["lat"]), longitude=float(match["lon"]))


def spoken_label(match: dict[str, Any]) -> str:
    """The place, its city or town, and its state, each once: "Union Square, New York", "Cupertino, California", rather than the whole postal address
    with its community board, county, and zip code."""
    address = match.get("address") or {}
    settlement = next((address[key] for key in SETTLEMENT_KEYS if address.get(key)), "")
    name = match.get("name") or str(match.get("display_name", "")).split(",")[0]
    return ", ".join(dict.fromkeys(part for part in (name, settlement, address.get("state", "")) if part))
