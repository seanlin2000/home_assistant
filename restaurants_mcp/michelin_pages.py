"""Reads the two kinds of Michelin Guide page the refresh fetches: a listing page's restaurant cards and how many pages the listing has, and a
restaurant page's description and address.

A card carries most of what the tools need in the data attributes Michelin sets for its analytics (data-dtm-*): the town, the district, the region,
the award, and the price category. Its footer prints the price as the guide shows it and the cuisine, such as "$$$$ · Japanese". The listing's own
results are in `js-restaurant__list_items`; a carousel of restaurants new to the guide in other states follows them and is skipped.

A restaurant page's structured data cuts the inspector's description short with "...", so the description is read from the page itself.
"""

import json
import re
from typing import Any
from urllib.parse import urljoin

import lxml.html
from pydantic import BaseModel

from restaurants_mcp.cities import GuideCity
from restaurants_mcp.restaurants import Award, Restaurant

AWARDS = {"3 star": Award.THREE_STARS, "2 star": Award.TWO_STARS, "1 star": Award.ONE_STAR, "bib": Award.BIB_GOURMAND, "": Award.SELECTED}
LISTING_CARDS = '//div[contains(@class, "js-restaurant__list_items")]//div[contains(@class, "selection-card")]'
PAGE_LINKS = '//a[contains(@href, "/restaurants/page/")]/@href'
PRICE_CATEGORY = re.compile(r"CAT_P0([1-4])")
PAGE_NUMBER = re.compile(r"/page/(\d+)")
PRICE_AND_CUISINE_SEPARATOR = " · "


class UnexpectedPage(ValueError):
    """A Michelin page did not have the shape this reader knows."""


class ListingPage(BaseModel):
    restaurants: list[Restaurant]
    last_page: int


class RestaurantPage(BaseModel):
    description: str
    address: str


def read_listing_page(html: str, city: GuideCity, page_url: str) -> ListingPage:
    tree = lxml.html.fromstring(html)
    page_numbers = [int(match.group(1)) for href in tree.xpath(PAGE_LINKS) if (match := PAGE_NUMBER.search(href))]
    return ListingPage(restaurants=[restaurant_from_card(card, city, page_url) for card in tree.xpath(LISTING_CARDS)], last_page=max(page_numbers, default=1))


def restaurant_from_card(card: lxml.html.HtmlElement, city: GuideCity, page_url: str) -> Restaurant:
    tagged = first(card.xpath(".//*[@data-dtm-city]"), "the card's data attributes")
    distinction = tagged.get("data-dtm-distinction", "")
    if distinction not in AWARDS:
        raise UnexpectedPage(f"a card's award is {distinction!r}, which the reader does not know")
    price_symbols, cuisine = price_and_cuisine(card)
    return Restaurant(
        name=spoken_text(first(card.xpath('.//*[contains(@class, "card__menu-content--title")]'), "the card's title")),
        url=urljoin(page_url, first(card.xpath('.//a[contains(@href, "/restaurant/")]/@href'), "the card's link")),
        guide_city=city.name,
        town=tagged.get("data-dtm-city", ""),
        district=tagged.get("data-dtm-district", ""),
        region=tagged.get("data-dtm-region", ""),
        award=AWARDS[distinction],
        price_level=price_level(tagged.get("data-dtm-price", ""), price_symbols),
        price_symbols=price_symbols,
        cuisine=cuisine,
        latitude=float(card.get("data-lat") or 0),
        longitude=float(card.get("data-lng") or 0),
    )


def price_and_cuisine(card: lxml.html.HtmlElement) -> tuple[str, str]:
    """From the footer line that reads like "$$$$ · Japanese"; the other footer line is the town."""
    footer_lines = [spoken_text(line) for line in card.xpath('.//*[contains(@class, "card__menu-footer--score")]')]
    line = next((line for line in footer_lines if PRICE_AND_CUISINE_SEPARATOR in line), "")
    price_symbols, _, cuisine = line.partition(PRICE_AND_CUISINE_SEPARATOR)
    return price_symbols, cuisine


def price_level(category: str, price_symbols: str) -> int | None:
    """Michelin's category when the card carries one; some cards carry none, and then the count of the printed symbols."""
    match = PRICE_CATEGORY.fullmatch(category)
    if match:
        return int(match.group(1))
    return len(price_symbols) or None


def read_restaurant_page(html: str) -> RestaurantPage:
    tree = lxml.html.fromstring(html)
    description = spoken_text(first(tree.xpath('//div[contains(@class, "data-sheet__description")]'), "the inspector's description"))
    return RestaurantPage(description=description, address=street_address(tree))


def street_address(tree: lxml.html.HtmlElement) -> str:
    for script in tree.xpath('//script[@type="application/ld+json"]'):
        data = json.loads(script.text or "{}")
        if isinstance(data, dict) and data.get("@type") == "Restaurant":
            address = data.get("address") or {}
            return ", ".join(part for part in (address.get("streetAddress"), address.get("addressLocality")) if part)
    return ""


def first(found: list[Any], what: str) -> Any:
    """The first element or attribute text an XPath selected."""
    if not found:
        raise UnexpectedPage(f"no {what} where the reader expects it")
    return found[0]


def spoken_text(element: lxml.html.HtmlElement) -> str:
    return " ".join(element.text_content().split())
