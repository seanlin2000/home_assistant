"""The restaurant tools' replies as the model reads them: a heading saying which restaurants and in what order, then one "a | b" line per restaurant
with a sentence of the inspector's description; or one restaurant in full.

The heading names the filters, so the model can tell the user when nothing matched which filter to drop.
"""

import re

from restaurants_mcp.restaurants import Award, Restaurant
from restaurants_mcp.selection import NEAR_RADIUS_MILES, NearbyRestaurant, RestaurantFilters
from utils.text_utils import clip_to_words, word_count

AWARD_LABELS = {
    Award.THREE_STARS: "three Michelin stars",
    Award.TWO_STARS: "two Michelin stars",
    Award.ONE_STAR: "one Michelin star",
    Award.BIB_GOURMAND: "Bib Gourmand",
    Award.SELECTED: "in the guide, no star",
}
AWARD_FILTER_LABELS = {
    "starred": "with a Michelin star",
    "three_stars": "with three stars",
    "two_stars": "with two stars",
    "one_star": "with one star",
    "bib_gourmand": "Bib Gourmand",
    "selected": "in the guide without a star",
}
DESCRIPTION_WORDS_IN_A_LIST = 30
SENTENCE_END = re.compile(r"[.!?]\s+(?=[A-Z“\"‘])")
WORDS_ENDING_IN_A_PERIOD = frozenset({"Mr", "Mrs", "Ms", "Dr", "St", "Jr"})  # "Dr. Smith" does not end a sentence
MATCHES_TO_OFFER = 6


def restaurants_text(listed: list[Restaurant], total: int, place: str, filters: RestaurantFilters) -> str:
    if total == 0:
        return f"No Michelin Guide restaurants in {place}{filter_text(filters)}. Tell the user, and offer to drop a filter."
    lines = [f"Michelin Guide restaurants in {place}{filter_text(filters)}, best awarded first ({len(listed)} of {total}):"]
    lines.extend(f"{rank}. {restaurant_line(restaurant)}" for rank, restaurant in enumerate(listed, start=1))
    return "\n".join(lines)


def nearby_text(listed: list[NearbyRestaurant], total: int, place: str, filters: RestaurantFilters) -> str:
    if total == 0:
        return f"No Michelin Guide restaurants within {NEAR_RADIUS_MILES:g} miles of {place}{filter_text(filters)}. Tell the user; the guide may not cover it, or a filter may be too narrow."
    lines = [f"Michelin Guide restaurants near {place}{filter_text(filters)}, closest first ({len(listed)} of {total} within {NEAR_RADIUS_MILES:g} miles):"]
    lines.extend(f"{rank}. {restaurant_line(nearby.restaurant, f'{nearby.miles:.1f} miles away')}" for rank, nearby in enumerate(listed, start=1))
    return "\n".join(lines)


def filter_text(filters: RestaurantFilters) -> str:
    labels = [f"{filters.cuisine} cuisine"] if filters.cuisine else []
    if filters.max_price is not None:
        labels.append(f"price level {filters.max_price} of 4 or less")
    if filters.award != "any":
        labels.append(AWARD_FILTER_LABELS[filters.award])
    return "".join(f", {label}" for label in labels)


def restaurant_line(restaurant: Restaurant, *extra_parts: str) -> str:
    parts = [restaurant.name, AWARD_LABELS[restaurant.award], restaurant.price_symbols, restaurant.cuisine, where(restaurant), *extra_parts]
    if restaurant.description:
        parts.append(clipped_with_ellipsis(first_sentence(restaurant.description), DESCRIPTION_WORDS_IN_A_LIST))
    return " | ".join(part for part in parts if part)


def where(restaurant: Restaurant) -> str:
    """The town, then Michelin's district when it says more: "Oakland, East Bay", "Tokyo, Minato-ku", "New York, Manhattan"."""
    return ", ".join(part for part in dict.fromkeys([restaurant.town, restaurant.district]) if part)


def first_sentence(text: str) -> str:
    """Up to the first full stop that ends a sentence: not one after an initial ("Chef Val M. Cantu") or a title such as "Dr."."""
    for end in SENTENCE_END.finditer(text):
        last_word = text[: end.start()].split()[-1]
        if not (len(last_word) == 1 and last_word.isupper()) and last_word not in WORDS_ENDING_IN_A_PERIOD:
            return text[: end.start() + 1]
    return text


def clipped_with_ellipsis(text: str, max_words: int) -> str:
    return text if word_count(text) <= max_words else f"{clip_to_words(text, max_words)}…"


def restaurant_details_text(restaurant: Restaurant) -> str:
    facts = " | ".join(part for part in (AWARD_LABELS[restaurant.award], restaurant.price_symbols, restaurant.cuisine, where(restaurant), restaurant.address) if part)
    description = f"The inspector says: {restaurant.description}" if restaurant.description else "The inspector's description could not be read just now."
    return f"{restaurant.name}, from the Michelin Guide: {facts}\n{description}\nMichelin page: {restaurant.url}"


def several_matches_text(restaurants: list[Restaurant], asked: str) -> str:
    offered = restaurants[:MATCHES_TO_OFFER]
    lines = [f'{len(restaurants)} restaurants in the Michelin Guide match "{asked}". Ask the user which one they mean:']
    lines.extend(f"{rank}. {restaurant.name} ({where(restaurant)}, {AWARD_LABELS[restaurant.award]})" for rank, restaurant in enumerate(offered, start=1))
    return "\n".join(lines)


def no_match_text(asked: str) -> str:
    return f'No restaurant called "{asked}" in the Michelin Guide\'s cities. Tell the user it may not be in the guide, or search the web for it.'
