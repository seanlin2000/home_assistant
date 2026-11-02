"""Finding the restaurants a spoken location names, by Michelin's own names for where each restaurant is: its town, its district, its guide city, and
its region.

A city's name means the city itself, the rule the user set for San Francisco on 2026-10-31: "Miami" is the 40 restaurants in Miami, not the 60 of
Michelin's Miami listing, which also holds Miami Beach and Coral Gables. So towns are tried before guide cities. Districts are New York's boroughs,
the Bay Area's districts, and the wards and neighbourhoods Michelin names elsewhere, and a district is found by its own words too: "Shibuya" is
Shibuya-ku, "Westminster" is "Central London - City of Westminster". The few names Michelin uses for none of them are aliases here.
"""

import re
import unicodedata
from collections.abc import Callable

from pydantic import BaseModel

from restaurants_mcp.cities import BAY_AREA_DISTRICTS
from restaurants_mcp.restaurants import Restaurant

NEAR_PREFIX = re.compile(r"^(near|around|close to)\s+", re.IGNORECASE)
AreaTest = Callable[[Restaurant], bool]


class Area(BaseModel):
    label: str
    restaurants: list[Restaurant]


def plain_words(name: str) -> list[str]:
    """Lowercase words without accents or punctuation: "São Paulo" and "Sao Paulo" are the same place."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]", " ", plain).split()


def same_name(asked: str, name: str) -> bool:
    return bool(name) and plain_words(asked) == plain_words(name)


ALIASES: dict[str, tuple[str, AreaTest]] = {
    "nyc": ("New York City", lambda restaurant: restaurant.guide_city == "New York"),
    "new york": ("New York City", lambda restaurant: restaurant.guide_city == "New York"),
    "new york city": ("New York City", lambda restaurant: restaurant.guide_city == "New York"),
    "bay area": ("the Bay Area", lambda restaurant: restaurant.region == "California" and restaurant.district in BAY_AREA_DISTRICTS),
    "sf bay area": ("the Bay Area", lambda restaurant: restaurant.region == "California" and restaurant.district in BAY_AREA_DISTRICTS),
    "san francisco bay area": ("the Bay Area", lambda restaurant: restaurant.region == "California" and restaurant.district in BAY_AREA_DISTRICTS),
    "sf": ("San Francisco", lambda restaurant: restaurant.town == "San Francisco"),
    "la": ("Los Angeles", lambda restaurant: restaurant.town == "Los Angeles"),
    "saigon": ("Ho Chi Minh City", lambda restaurant: restaurant.guide_city == "Ho Chi Minh City"),
}


def is_near_request(location: str) -> bool:
    return bool(NEAR_PREFIX.match(location.strip()))


def place_named_near(location: str) -> str:
    return NEAR_PREFIX.sub("", location.strip())


def area_named(restaurants: list[Restaurant], location: str) -> Area | None:
    """The restaurants of the first kind of name that matches any: an alias, a town, a district, a guide city, a region, then a district holding every
    word asked. None when no restaurant is there by any of Michelin's names."""
    asked_words = plain_words(location)
    if not asked_words:
        return None
    alias = ALIASES.get(" ".join(asked_words))
    tests: list[tuple[str, AreaTest]] = [alias] if alias else []
    tests.extend(
        [
            (location, lambda restaurant: same_name(location, restaurant.town)),
            (location, lambda restaurant: same_name(location, restaurant.district)),
            (location, lambda restaurant: same_name(location, restaurant.guide_city)),
            (location, lambda restaurant: same_name(location, restaurant.region)),
            (location, lambda restaurant: bool(restaurant.district) and set(asked_words) <= set(plain_words(restaurant.district))),
        ]
    )
    for label, test in tests:
        found = [restaurant for restaurant in restaurants if test(restaurant)]
        if found:
            return Area(label=area_label(label, found), restaurants=found)
    return None


def area_label(asked: str, found: list[Restaurant]) -> str:
    """Michelin's spelling of the name asked when every restaurant found shares it: "shibuya" is said as Shibuya-ku, "sao paulo" as São Paulo."""
    for spellings in ({restaurant.town for restaurant in found}, {restaurant.district for restaurant in found}, {restaurant.guide_city for restaurant in found}):
        spelling = next(iter(spellings))
        if len(spellings) == 1 and spelling and set(plain_words(asked)) <= set(plain_words(spelling)):
            return spelling
    return asked
