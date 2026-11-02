"""A restaurant as the snapshot keeps it: what its card on a Michelin listing says, and the inspector's description once its own page has been read."""

from enum import StrEnum

from pydantic import BaseModel

from restaurants_mcp.cities import DESCRIBED_DISTRICTS
from utils.snapshot_utils import DatedSnapshot


class Award(StrEnum):
    THREE_STARS = "three_stars"
    TWO_STARS = "two_stars"
    ONE_STAR = "one_star"
    BIB_GOURMAND = "bib_gourmand"
    SELECTED = "selected"  # in the guide without a star or a Bib Gourmand


class Restaurant(BaseModel):
    name: str
    url: str
    guide_city: str  # the GuideCity whose listing it came from, such as "Tokyo" or "California"
    town: str  # Michelin's own: "New York" for Manhattan, "Oakland", "Tokyo"
    district: str  # Michelin's own: a New York borough, a Bay Area district such as "East Bay", a Tokyo ward; empty for some
    region: str  # Michelin's own: "New York State", "California", "Tokyo"
    award: Award
    price_level: int | None  # 1 to 4, Michelin's price category
    price_symbols: str  # the level as the guide prints it there: "$$$$", "¥¥¥", "€€"
    cuisine: str
    latitude: float
    longitude: float
    description: str = ""  # the inspector's text, read from the restaurant's own page
    address: str = ""  # the street address, read from the same page

    @property
    def is_in_described_area(self) -> bool:
        return self.district in DESCRIBED_DISTRICTS.get(self.region, frozenset())


class RestaurantsSnapshot(DatedSnapshot):
    restaurants: list[Restaurant]
