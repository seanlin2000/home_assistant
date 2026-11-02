"""Choosing restaurants for an answer: the cuisine, price, and award filters, then the order, by award or, near a place, by distance."""

import math
from typing import Literal, Protocol

from pydantic import BaseModel

from restaurants_mcp.locations import plain_words
from restaurants_mcp.restaurants import Award, Restaurant

AwardFilter = Literal["any", "starred", "three_stars", "two_stars", "one_star", "bib_gourmand", "selected"]
DEFAULT_LIMIT = 10  # the user's choice, 2026-11-01
NEAR_RADIUS_MILES = 15.0  # far enough for Cupertino, which has no Michelin restaurant, to reach Los Altos, Saratoga, and San Jose
EARTH_RADIUS_MILES = 3958.8
AWARD_ORDER = [Award.THREE_STARS, Award.TWO_STARS, Award.ONE_STAR, Award.BIB_GOURMAND, Award.SELECTED]
STARS = frozenset({Award.THREE_STARS, Award.TWO_STARS, Award.ONE_STAR})


class RestaurantFilters(BaseModel):
    cuisine: str = ""
    max_price: int | None = None  # 1 to 4, Michelin's price level
    award: AwardFilter = "any"

    def admits(self, restaurant: Restaurant) -> bool:
        return self.serves_cuisine(restaurant) and self.within_price(restaurant) and self.has_award(restaurant)

    def serves_cuisine(self, restaurant: Restaurant) -> bool:
        """Every word asked is in Michelin's cuisine: "seafood" finds "Fish and Seafood", "japanese" does not find "Sushi"."""
        return set(plain_words(self.cuisine)) <= set(plain_words(restaurant.cuisine))

    def within_price(self, restaurant: Restaurant) -> bool:
        return self.max_price is None or (restaurant.price_level is not None and restaurant.price_level <= self.max_price)

    def has_award(self, restaurant: Restaurant) -> bool:
        if self.award == "any":
            return True
        if self.award == "starred":
            return restaurant.award in STARS
        return restaurant.award == Award(self.award)


class Located(Protocol):
    latitude: float
    longitude: float


class NearbyRestaurant(BaseModel):
    restaurant: Restaurant
    miles: float


def best_awarded_first(restaurants: list[Restaurant]) -> list[Restaurant]:
    return sorted(restaurants, key=lambda restaurant: (AWARD_ORDER.index(restaurant.award), restaurant.name.lower()))


def nearest_first(restaurants: list[Restaurant], place: Located) -> list[NearbyRestaurant]:
    """Those within NEAR_RADIUS_MILES, closest first."""
    measured = [NearbyRestaurant(restaurant=restaurant, miles=miles_between(place, restaurant)) for restaurant in restaurants]
    return sorted((nearby for nearby in measured if nearby.miles <= NEAR_RADIUS_MILES), key=lambda nearby: nearby.miles)


def miles_between(place: Located, other: Located) -> float:
    """Great-circle distance by the haversine formula."""
    rise = math.radians(other.latitude - place.latitude)
    run = math.radians(other.longitude - place.longitude)
    chord = math.sin(rise / 2) ** 2 + math.cos(math.radians(place.latitude)) * math.cos(math.radians(other.latitude)) * math.sin(run / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(chord))
