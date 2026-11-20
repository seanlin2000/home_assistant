"""Finding the restaurant a user named, with the title matching the listings tools share (utils/title_matching_utils.py). The words left out of a
restaurant's name are the ones people put around one: the, restaurant, Michelin."""

from pydantic import BaseModel

from restaurants_mcp.restaurants import Restaurant
from restaurants_mcp.selection import best_awarded_first
from utils.title_matching_utils import MatchRule, TitleMatcher

RESTAURANT_NAMES = TitleMatcher(frozenset({"the", "a", "an", "restaurant", "michelin"}))


class RestaurantsNamed(BaseModel):
    rule: MatchRule | None  # None when no restaurant matched
    restaurants: list[Restaurant]  # shortest name first, then best awarded


def restaurants_named(restaurants: list[Restaurant], asked: str) -> RestaurantsNamed:
    candidates = best_awarded_first(restaurants)
    matches = RESTAURANT_NAMES.matches(asked, [restaurant.name for restaurant in candidates])
    position = {name: index for index, name in enumerate(matches.titles)}
    found = sorted((restaurant for restaurant in candidates if restaurant.name in position), key=lambda restaurant: position[restaurant.name])
    return RestaurantsNamed(rule=matches.rule, restaurants=found)
