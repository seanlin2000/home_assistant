"""The restaurant tools: a location found by Michelin's own names (a city meaning the city itself, aliases for New York and the Bay Area, a district by
its own words), the cuisine, price, and award filters, the nearest restaurants to any other place, descriptions read while answering and kept until
the next refresh, and one restaurant in full. The snapshot is built here; Michelin's restaurant page is the fixture the refresh tests use, and
Nominatim is a mock answering as it did on 2026-11-01."""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from mcp.server.mcpserver import MCPServer

from assistant_core.models import ToolCall
from assistant_core.tools import McpToolBox
from assistant_mcp.server import build_server
from restaurants_mcp.answers import NO_SNAPSHOT_MESSAGE, RestaurantAnswers
from restaurants_mcp.descriptions import DescriptionReader
from restaurants_mcp.locations import area_named
from restaurants_mcp.register import RESTAURANT_DETAILS_TOOL_NAME, RESTAURANTS_TOOL_NAME, register_restaurants_tools
from restaurants_mcp.render import clipped_with_ellipsis, first_sentence
from restaurants_mcp.restaurants import Award, Restaurant, RestaurantsSnapshot
from restaurants_mcp.selection import RestaurantFilters, best_awarded_first, miles_between, nearest_first
from restaurants_mcp.settings import RestaurantsSettings
from utils.geocoding_utils import Coordinates, Geocoder, PlaceNotFound, chosen_match, spoken_label
from utils.snapshot_utils import write_snapshot
from web_search_mcp.settings import SearchSettings

RESTAURANT_HTML = Path("tests/fixtures/michelin_restaurant_le_bernardin.html").read_text()
REFRESHED_AT = datetime(2026, 11, 1, 12, tzinfo=UTC)
UNION_SQUARE = {"name": "Union Square", "lat": "40.7361", "lon": "-73.9902", "category": "place", "address": {"city": "New York", "state": "New York"}}


def restaurant(name: str, where: tuple[str, str, str, str], award: Award, price_level: int, cuisine: str, position: tuple[float, float], description: str = "") -> Restaurant:
    town, district, region, guide_city = where
    return Restaurant(
        name=name,
        url=f"https://guide.michelin.com/us/en/restaurant/{name.lower().replace(' ', '-')}",
        guide_city=guide_city,
        town=town,
        district=district,
        region=region,
        award=award,
        price_level=price_level,
        price_symbols="$" * price_level,
        cuisine=cuisine,
        latitude=position[0],
        longitude=position[1],
        description=description,
    )


MANHATTAN = ("New York", "Manhattan", "New York State", "New York")
BROOKLYN = ("Brooklyn", "Brooklyn", "New York State", "New York")
OAKLAND = ("Oakland", "East Bay", "California", "California")
SAN_FRANCISCO = ("San Francisco", "San Francisco", "California", "California")
LOS_ANGELES = ("Los Angeles", "Los Angeles", "California", "California")
MIAMI = ("Miami", "", "Florida", "Miami")
MIAMI_BEACH = ("Miami Beach", "", "Florida", "Miami")
SHIBUYA = ("Tokyo", "Shibuya-ku", "Tokyo", "Tokyo")
SAO_PAULO = ("São Paulo", "Jardins", "São Paulo", "Sao Paulo")
RESTAURANTS = [
    restaurant("Le Bernardin", MANHATTAN, Award.THREE_STARS, 4, "Seafood", (40.7614, -73.9817), "Seafood has long been the calling card. It is French."),
    restaurant("Casa Mono", MANHATTAN, Award.ONE_STAR, 3, "Spanish", (40.7366, -73.9866), "There is something reassuring about a kitchen that butchers."),
    restaurant("Dim Sum Go Go", MANHATTAN, Award.BIB_GOURMAND, 2, "Chinese", (40.7134, -73.9974), "Dumplings in Chinatown."),
    restaurant("Alta Calidad", BROOKLYN, Award.BIB_GOURMAND, 2, "Mexican", (40.6802, -73.9676), "Bright and modern Mexican."),
    restaurant("Bombera", OAKLAND, Award.BIB_GOURMAND, 2, "Mexican", (37.7981, -122.2159), "A former fire station."),
    restaurant("Benu", SAN_FRANCISCO, Award.THREE_STARS, 4, "Asian", (37.7853, -122.3990), "An oasis in the center of the city."),
    restaurant("Kato", LOS_ANGELES, Award.ONE_STAR, 4, "Taiwanese", (34.0480, -118.2563)),
    restaurant("Ariete", MIAMI, Award.ONE_STAR, 4, "Contemporary", (25.7280, -80.2420)),
    restaurant("Stubborn Seed", MIAMI_BEACH, Award.ONE_STAR, 4, "Contemporary", (25.7700, -80.1340)),
    restaurant("Den", SHIBUYA, Award.TWO_STARS, 3, "Japanese", (35.6720, 139.7110)),
    restaurant("Tuju", SAO_PAULO, Award.THREE_STARS, 4, "Creative", (-23.5760, -46.6860)),
]


def names(restaurants: list[Restaurant]) -> list[str]:
    return [restaurant.name for restaurant in restaurants]


def area_names(location: str) -> list[str]:
    area = area_named(RESTAURANTS, location)
    return names(area.restaurants) if area else []


def test_a_city_means_the_city_itself() -> None:
    assert area_names("Miami") == ["Ariete"]  # not Stubborn Seed in Miami Beach, though Michelin's Miami listing holds both
    assert area_names("San Francisco") == ["Benu"]


def test_aliases_name_new_york_city_and_the_bay_area() -> None:
    assert area_names("NYC") == ["Le Bernardin", "Casa Mono", "Dim Sum Go Go", "Alta Calidad"]
    assert area_names("Bay Area") == ["Bombera", "Benu"]  # Los Angeles is in California but not the Bay Area


def test_boroughs_districts_and_a_districts_own_words_are_areas() -> None:
    assert area_names("Brooklyn") == ["Alta Calidad"]
    assert area_names("east bay") == ["Bombera"]
    assert area_names("Shibuya") == ["Den"] and area_named(RESTAURANTS, "Shibuya").label == "Shibuya-ku"


def test_a_name_is_matched_without_its_accents() -> None:
    area = area_named(RESTAURANTS, "Sao Paulo")
    assert names(area.restaurants) == ["Tuju"] and area.label == "São Paulo"


def test_a_place_the_guide_does_not_name_is_no_area() -> None:
    assert area_named(RESTAURANTS, "Cupertino") is None


def test_the_filters_admit_by_cuisine_word_price_ceiling_and_award() -> None:
    def admitted(filters: RestaurantFilters) -> list[str]:
        return names([restaurant for restaurant in RESTAURANTS if filters.admits(restaurant)])

    assert admitted(RestaurantFilters(cuisine="mexican")) == ["Alta Calidad", "Bombera"]
    assert admitted(RestaurantFilters(max_price=2)) == ["Dim Sum Go Go", "Alta Calidad", "Bombera"]
    assert admitted(RestaurantFilters(award="starred", max_price=3)) == ["Casa Mono", "Den"]
    assert admitted(RestaurantFilters(award="bib_gourmand", cuisine="chinese")) == ["Dim Sum Go Go"]


def test_a_citys_home_cuisine_is_one_umbrella_over_its_house_styles() -> None:
    paris = ("Paris", "", "Île-de-France", "Paris")
    in_paris = [
        restaurant("Kei", paris, Award.THREE_STARS, 4, "Modern Cuisine", (48.8630, 2.3420)),
        restaurant("Arpège", paris, Award.THREE_STARS, 4, "Creative", (48.8556, 2.3168)),
        restaurant("Chez Georges", paris, Award.SELECTED, 3, "Traditional Cuisine", (48.8660, 2.3410)),
        restaurant("Sushi B", paris, Award.ONE_STAR, 4, "Japanese", (48.8650, 2.3360)),
    ]
    creative_in_tokyo = restaurant("Florilège", SHIBUYA, Award.TWO_STARS, 4, "Creative", (35.6650, 139.7130))

    def admitted(cuisine: str) -> list[str]:
        return names([restaurant for restaurant in [*in_paris, creative_in_tokyo, *RESTAURANTS] if RestaurantFilters(cuisine=cuisine).admits(restaurant)])

    assert admitted("French") == ["Kei", "Arpège", "Chez Georges"]  # Michelin labels none of them "French" in Paris
    assert admitted("modern French") == ["Kei", "Arpège", "Chez Georges"]  # no split between modern and traditional
    assert admitted("Japanese") == ["Sushi B", "Den"]  # Tokyo names its own cuisine, so its Creative restaurant is not Japanese
    assert admitted("Brazilian") == ["Tuju"]


def test_restaurants_come_best_awarded_first_then_by_name() -> None:
    assert names(best_awarded_first(RESTAURANTS[:4])) == ["Le Bernardin", "Casa Mono", "Alta Calidad", "Dim Sum Go Go"]


def test_the_nearest_come_closest_first_within_the_radius() -> None:
    union_square = Coordinates(label="Union Square, New York", latitude=40.7361, longitude=-73.9902)
    nearby = nearest_first(RESTAURANTS, union_square)

    assert names([near.restaurant for near in nearby]) == ["Casa Mono", "Dim Sum Go Go", "Le Bernardin", "Alta Calidad"]
    assert round(miles_between(Coordinates(label="", latitude=40.0, longitude=-74.0), Coordinates(label="", latitude=41.0, longitude=-74.0)), 1) == 69.1


def test_a_description_in_a_list_is_its_first_sentence_cut_short_with_an_ellipsis() -> None:
    assert first_sentence("Chef Val M. Cantú has created a destination. It is singular.") == "Chef Val M. Cantú has created a destination."
    assert first_sentence("Dr. Smith cooks. Then he rests.") == "Dr. Smith cooks."
    assert clipped_with_ellipsis("one two three four", 2) == "one two…" and clipped_with_ellipsis("one two", 2) == "one two"


def test_the_geocoder_prefers_an_area_and_says_where_it_is() -> None:
    charging_station = {"name": "Revel - Mission District", "lat": "37.76", "lon": "-122.41", "category": "amenity"}
    neighbourhood = {"name": "Mission District", "lat": "37.75", "lon": "-122.42", "category": "place", "address": {"city": "San Francisco", "state": "California"}}

    assert chosen_match([charging_station, neighbourhood], "Mission District") is neighbourhood
    assert spoken_label(neighbourhood) == "Mission District, San Francisco, California"
    assert spoken_label({"name": "Cupertino", "address": {"city": "Cupertino", "state": "California"}}) == "Cupertino, California"
    with pytest.raises(PlaceNotFound):
        chosen_match([], "Atlantis")


class FakeMichelinPages:
    """Le Bernardin's page for every restaurant page, remembering which were read."""

    def __init__(self) -> None:
        self.paths: list[str] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        return httpx.Response(200, text=RESTAURANT_HTML)


async def resolve_public(host: str) -> list[str]:
    return ["93.184.216.34"]


def nominatim_answering(matches: list[dict[str, Any]]) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(200, json=matches))


def settings_in(tmp_path: Path) -> RestaurantsSettings:
    return RestaurantsSettings(snapshot_path=tmp_path / "restaurants.json", descriptions_path=tmp_path / "descriptions.json", today=date(2026, 11, 2))


async def call(settings: RestaurantsSettings, name: str, arguments: dict[str, Any], pages: FakeMichelinPages | None = None, nominatim: httpx.MockTransport | None = None) -> str:
    descriptions = DescriptionReader(settings, httpx.MockTransport((pages or FakeMichelinPages()).handle), resolve_public)
    geocoder = Geocoder(settings.timeout_seconds, nominatim or nominatim_answering([UNION_SQUARE]))
    server = MCPServer("restaurants-test")
    register_restaurants_tools(server, settings, RestaurantAnswers(settings, geocoder, descriptions))
    async with McpToolBox(server) as toolbox:
        return await toolbox.call(ToolCall(id=name, name=name, arguments=arguments))


def write_restaurants(settings: RestaurantsSettings, refreshed_at: datetime = REFRESHED_AT) -> None:
    write_snapshot(settings.snapshot_path, RestaurantsSnapshot(refreshed_at=refreshed_at, restaurants=RESTAURANTS))


async def test_the_tool_server_offers_both_restaurant_tools() -> None:
    async with McpToolBox(build_server(SearchSettings())) as toolbox:
        offered = {spec.name for spec in await toolbox.list_tools()}
    assert {RESTAURANTS_TOOL_NAME, RESTAURANT_DETAILS_TOOL_NAME} <= offered


async def test_recommendations_list_an_area_best_awarded_first_with_a_sentence_each(tmp_path: Path) -> None:
    settings = settings_in(tmp_path)
    write_restaurants(settings)
    reply = await call(settings, RESTAURANTS_TOOL_NAME, {"location": "Manhattan"})

    assert reply.splitlines() == [
        "Michelin Guide restaurants in Manhattan, best awarded first (3 of 3):",
        "1. Le Bernardin | three Michelin stars | $$$$ | Seafood | New York, Manhattan | Seafood has long been the calling card.",
        "2. Casa Mono | one Michelin star | $$$ | Spanish | New York, Manhattan | There is something reassuring about a kitchen that butchers.",
        "3. Dim Sum Go Go | Bib Gourmand | $$ | Chinese | New York, Manhattan | Dumplings in Chinatown.",
    ]


async def test_the_heading_names_the_filters_and_an_empty_answer_offers_to_drop_one(tmp_path: Path) -> None:
    settings = settings_in(tmp_path)
    write_restaurants(settings)
    filtered = await call(settings, RESTAURANTS_TOOL_NAME, {"location": "NYC", "cuisine": "Mexican", "max_price": 2})
    empty = await call(settings, RESTAURANTS_TOOL_NAME, {"location": "Brooklyn", "award": "three_stars"})

    assert filtered.splitlines()[0] == "Michelin Guide restaurants in New York City, Mexican cuisine, price level 2 of 4 or less, best awarded first (1 of 1):"
    assert empty == "No Michelin Guide restaurants in Brooklyn, with three stars. Tell the user, and offer to drop a filter."


async def test_a_description_the_snapshot_lacks_is_read_once_and_kept_until_the_next_refresh(tmp_path: Path) -> None:
    settings = settings_in(tmp_path)
    write_restaurants(settings)
    pages = FakeMichelinPages()
    first = await call(settings, RESTAURANTS_TOOL_NAME, {"location": "Miami"}, pages)
    await call(settings, RESTAURANTS_TOOL_NAME, {"location": "Miami"}, pages)
    assert pages.paths == ["/us/en/restaurant/ariete"]
    assert first.endswith("| Contemporary | Miami | Well-heeled patrons continue to hold court in this iconic Midtown restaurant led by the ever-gracious Chef Eric Ripert.")

    write_restaurants(settings, refreshed_at=datetime(2026, 12, 1, tzinfo=UTC))
    await call(settings, RESTAURANTS_TOOL_NAME, {"location": "Miami"}, pages)
    assert pages.paths == ["/us/en/restaurant/ariete"] * 2


async def test_a_page_that_cannot_be_read_leaves_the_restaurant_listed_without_a_description(tmp_path: Path) -> None:
    settings = settings_in(tmp_path)
    write_restaurants(settings)
    descriptions = DescriptionReader(settings, httpx.MockTransport(lambda request: httpx.Response(503)), resolve_public)
    [listed] = await descriptions.with_descriptions([RESTAURANTS[7]], REFRESHED_AT)

    assert listed.name == "Ariete" and listed.description == ""


async def test_near_a_place_lists_the_closest_with_their_distance(tmp_path: Path) -> None:
    settings = settings_in(tmp_path)
    write_restaurants(settings)
    reply = await call(settings, RESTAURANTS_TOOL_NAME, {"location": "near Union Square, Manhattan", "limit": 2})

    assert reply.splitlines()[0] == "Michelin Guide restaurants near Union Square, New York, closest first (2 of 4 within 15 miles):"
    assert reply.splitlines()[1].startswith("1. Casa Mono | one Michelin star | $$$ | Spanish | New York, Manhattan | 0.2 miles away |")


async def test_a_place_the_guide_does_not_name_is_found_on_the_map(tmp_path: Path) -> None:
    settings = settings_in(tmp_path)
    write_restaurants(settings)
    cupertino = {"name": "Cupertino", "lat": "37.3229", "lon": "-122.0323", "category": "boundary", "address": {"city": "Cupertino", "state": "California"}}
    reply = await call(settings, RESTAURANTS_TOOL_NAME, {"location": "Cupertino"}, nominatim=nominatim_answering([cupertino]))

    assert reply.startswith("No Michelin Guide restaurants within 15 miles of Cupertino, California.")


async def test_a_place_not_on_the_map_or_a_map_that_does_not_answer_is_one_sentence(tmp_path: Path) -> None:
    settings = settings_in(tmp_path)
    write_restaurants(settings)
    unknown = await call(settings, RESTAURANTS_TOOL_NAME, {"location": "near Atlantis"}, nominatim=nominatim_answering([]))
    down = await call(settings, RESTAURANTS_TOOL_NAME, {"location": "near Atlantis"}, nominatim=httpx.MockTransport(lambda request: httpx.Response(503)))

    assert unknown.startswith('No place called "Atlantis" on the map.')
    assert down.startswith("The map search did not answer")


async def test_details_give_one_restaurant_in_full(tmp_path: Path) -> None:
    settings = settings_in(tmp_path)
    write_restaurants(settings)
    reply = await call(settings, RESTAURANT_DETAILS_TOOL_NAME, {"restaurant": "le bernardin"})

    assert reply.splitlines() == [
        "Le Bernardin, from the Michelin Guide: three Michelin stars | $$$$ | Seafood | New York, Manhattan",
        "The inspector says: Seafood has long been the calling card. It is French.",
        "Michelin page: https://guide.michelin.com/us/en/restaurant/le-bernardin",
    ]


async def test_details_ask_which_restaurant_when_several_match_and_say_when_none_does(tmp_path: Path) -> None:
    settings = settings_in(tmp_path)
    write_restaurants(settings)
    one = await call(settings, RESTAURANT_DETAILS_TOOL_NAME, {"restaurant": "Ariete"})
    none = await call(settings, RESTAURANT_DETAILS_TOOL_NAME, {"restaurant": "Per Se"})
    assert one.startswith("Ariete, from the Michelin Guide")  # one match is answered, not offered
    assert none.startswith('No restaurant called "Per Se" in the Michelin Guide')

    write_snapshot(
        settings.snapshot_path, RestaurantsSnapshot(refreshed_at=REFRESHED_AT, restaurants=[*RESTAURANTS, RESTAURANTS[1].model_copy(update={"url": "x", "town": "Brooklyn", "district": "Brooklyn"})])
    )
    ambiguous = await call(settings, RESTAURANT_DETAILS_TOOL_NAME, {"restaurant": "Casa Mono"})
    in_brooklyn = await call(settings, RESTAURANT_DETAILS_TOOL_NAME, {"restaurant": "Casa Mono", "location": "Brooklyn"})
    assert ambiguous.splitlines()[0] == '2 restaurants in the Michelin Guide match "Casa Mono". Ask the user which one they mean:'
    assert in_brooklyn.startswith("Casa Mono, from the Michelin Guide: one Michelin star | $$$ | Spanish | Brooklyn")


async def test_no_snapshot_and_an_old_snapshot_are_said(tmp_path: Path) -> None:
    settings = settings_in(tmp_path)
    assert await call(settings, RESTAURANTS_TOOL_NAME, {"location": "Manhattan"}) == NO_SNAPSHOT_MESSAGE

    write_restaurants(settings, refreshed_at=datetime(2026, 9, 1, 12, tzinfo=UTC))
    reply = await call(settings, RESTAURANTS_TOOL_NAME, {"location": "Manhattan"})
    assert reply.splitlines()[-1].startswith("These listings were last refreshed 62 days ago")
