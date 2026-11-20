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
        location: Annotated[
            str,
            Field(
                max_length=MAX_LOCATION_CHARS,
                description='city ("Tokyo"), borough ("Brooklyn"), Bay Area district ("East Bay", "Bay Area"), town ("Palo Alto") or neighbourhood ("Shibuya"); else "near" a place and its city, e.g. "near Union Square, Manhattan"',
            ),
        ],
        cuisine: Annotated[str, Field(description='e.g. "Japanese"; empty for any')] = "",
        max_price: Annotated[
            int | None,
            Field(
                ge=1,
                le=4,
                description='highest price level: 1 on a budget ($), 2 moderate ($$), 3 special occasion ($$$), 4 spare no expense ($$$$); "cheap" is 1, "three dollar signs or less" is 3',
            ),
        ] = None,
        award: Annotated[AwardFilter, Field(description="starred: any star; bib_gourmand: good value; selected: no star")] = "any",
        limit: Annotated[int, Field(ge=1, le=MOST_RESTAURANTS_LISTED, description="how many")] = DEFAULT_LIMIT,
    ) -> str:
        """Michelin Guide restaurants with award, price, cuisine and an inspector's line. Use this first for any restaurant recommendation, before searching the web. If the user named no place, ask where. Name them in the order given, with each award and price in Michelin's words. No hours, menus or reservations: search the web only for those."""
        filters = RestaurantFilters(cuisine=cuisine, max_price=max_price, award=award)
        return await answers.recommendations(location, filters, limit)

    @server.tool(name=RESTAURANT_DETAILS_TOOL_NAME)
    async def restaurant_details(
        restaurant: Annotated[str, Field(description="name as the user said it; part is enough")],
        location: Annotated[str, Field(description="city or district, if the name is in several cities")] = "",
    ) -> str:
        """One Michelin Guide restaurant in full: description, award, price, cuisine, address, Michelin page. Use this first for what one restaurant is like. No hours, menus or reservations: search the web only for those."""
        return await answers.details(restaurant, location)
