"""Expose Michelin Guide restaurant recommendations, and what one restaurant is like, as MCP tools on the existing server, so the agent sees one tool
list. They answer from the snapshot the monthly refresh writes (restaurants_mcp/michelin.py); see restaurants_mcp/answers.py."""

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from restaurants_mcp.answers import RestaurantAnswers
from restaurants_mcp.descriptions import DescriptionReader
from restaurants_mcp.selection import DEFAULT_LIMIT, AwardFilter, RestaurantFilters
from restaurants_mcp.settings import RestaurantsSettings
from utils.geocoding_utils import Geocoder

RESTAURANTS_TOOL_NAME = "restaurant_recommendations"
RESTAURANT_DETAILS_TOOL_NAME = "restaurant_details"
MAX_LOCATION_CHARS = 80
MOST_RESTAURANTS_LISTED = 25


def register_restaurants_tools(server: MCPServer, settings: RestaurantsSettings, answers: RestaurantAnswers | None = None) -> None:
    answers = answers or RestaurantAnswers(settings, Geocoder(settings.timeout_seconds), DescriptionReader(settings))

    @server.tool(name=RESTAURANTS_TOOL_NAME)
    async def restaurant_recommendations(
        location: Annotated[str, Field(max_length=MAX_LOCATION_CHARS)],
        cuisine: str = "",
        max_price: Annotated[int | None, Field(ge=1, le=4)] = None,
        award: AwardFilter = "any",
        limit: Annotated[int, Field(ge=1, le=MOST_RESTAURANTS_LISTED)] = DEFAULT_LIMIT,
    ) -> str:
        """Restaurants from the Michelin Guide, with each one's award, price, cuisine, neighbourhood, and a sentence from the inspector. location: a city such as "Tokyo" or "San Francisco" (the city itself, not its suburbs), a New York borough such as "Brooklyn", a Bay Area district such as "East Bay", "South Bay", or "Peninsula", "Bay Area", a town such as "Palo Alto", or a neighbourhood the guide names such as "Shibuya". For anywhere else, or for the closest restaurants to a place, start with "near" and give the place with its city: "near Cupertino", "near Union Square, Manhattan"; those come closest first, with the distance. cuisine: a word such as "Japanese", "Italian", or "seafood", or empty for any. max_price: the most expensive price level the user wants, 1 to 4 ($ to $$$$). award: "starred" for any Michelin star, "three_stars", "two_stars", "one_star", "bib_gourmand" for good value, "selected" for in the guide without a star, or "any". limit: how many restaurants to list."""
        filters = RestaurantFilters(cuisine=cuisine, max_price=max_price, award=award)
        return await answers.recommendations(location, filters, limit)

    @server.tool(name=RESTAURANT_DETAILS_TOOL_NAME)
    async def restaurant_details(restaurant: str, location: str = "") -> str:
        """One Michelin Guide restaurant in full: the inspector's whole description, its award, price, cuisine, neighbourhood, street address, and Michelin page. restaurant: its name alone, as the user said it, such as "Le Bernardin"; part of a name is enough. location: its city or district, such as "Manhattan", when the name could be in several cities, or empty."""
        return await answers.details(restaurant, location)
