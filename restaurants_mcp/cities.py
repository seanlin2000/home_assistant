"""The Michelin Guide listing pages the monthly refresh reads, and the areas whose restaurant pages it reads too.

Each city's listing is the page Michelin itself links to it, which often covers the metro: its "San Francisco" page held 147 restaurants on
2026-10-31, only 97 of them in the city. California is read as one listing instead, because it is the only page that holds the whole Bay Area
(South Bay and Peninsula restaurants are on no city page) and it costs 11 pages against the 9 its San Francisco, Los Angeles, and San Diego pages
would. The paths with numbers are Michelin's own, taken from its sitemap (sitemap/restaurant-locations/us).

The user eats most often in New York and the Bay Area, so restaurants there have their inspector's description read every month and answered
instantly; elsewhere the tools read it the first time it is asked for (design agreed 2026-11-01).
"""

from pydantic import BaseModel


class GuideCity(BaseModel):
    name: str
    path: str  # under the guide URL, without the trailing /restaurants


def guide_city(name: str, path: str) -> GuideCity:
    return GuideCity(name=name, path=path)


GUIDE_CITIES = (
    guide_city("New York", "new-york-state/new-york"),
    guide_city("California", "california"),
    guide_city("Chicago", "illinois/chicago"),
    guide_city("Washington DC", "district-of-columbia/washington-dc"),
    guide_city("Miami", "florida/miami"),
    guide_city("Orlando", "florida/orlando"),
    guide_city("Tampa", "florida/tampa"),
    guide_city("Atlanta", "georgia/atlanta_2884144"),
    guide_city("Austin", "texas/austin_2958315"),
    guide_city("Houston", "texas/houston_2986624"),
    guide_city("Dallas", "texas/dallas_2954570"),
    guide_city("Denver", "colorado/denver_1261491"),
    guide_city("Boston", "massachusetts/boston_2914838"),
    guide_city("Philadelphia", "pennsylvania/philadelphia_2942787"),
    guide_city("New Orleans", "louisiana/new-orleans_2906000"),
    guide_city("Nashville", "tennessee/nashville_2790527"),
    guide_city("Charleston", "south-carolina/charleston_2952029"),
    guide_city("Las Vegas", "nevada/las-vegas_2935077"),
    guide_city("Paris", "ile-de-france/paris"),
    guide_city("London", "greater-london/london"),
    guide_city("Tokyo", "tokyo-region/tokyo"),
    guide_city("Kyoto", "kyoto-region/kyoto"),
    guide_city("Osaka", "osaka-region/osaka"),
    guide_city("Hong Kong", "hong-kong-region/hong-kong"),
    guide_city("Macau", "macau-region/macau"),
    guide_city("Singapore", "singapore-region/singapore"),
    guide_city("Seoul", "seoul-capital-area/kr-seoul"),
    guide_city("Bangkok", "bangkok-region/bangkok"),
    guide_city("Taipei", "taipei-region/taipei"),
    guide_city("Shanghai", "shanghai-municipality/shanghai"),
    guide_city("Beijing", "beijing-municipality/beijing"),
    guide_city("Guangzhou", "guangdong/guangzhou_1026985"),
    guide_city("Ho Chi Minh City", "ho-chi-minh/ho-chi-minh_2978179"),
    guide_city("Hanoi", "ha-noi/ha-noi_2974158"),
    guide_city("Kuala Lumpur", "kuala-lumpur-region"),
    guide_city("Rome", "lazio/roma"),
    guide_city("Milan", "lombardia/milano"),
    guide_city("Madrid", "comunidad-de-madrid/madrid"),
    guide_city("Barcelona", "catalunya/barcelona"),
    guide_city("Lisbon", "lisboa-region/lisboa"),
    guide_city("Copenhagen", "capital-region/copenhagen"),
    guide_city("Stockholm", "stockholm-region/stockholm"),
    guide_city("Berlin", "berlin-region/berlin"),
    guide_city("Munich", "bayern/mnchen"),
    guide_city("Amsterdam", "noord-holland/amsterdam"),
    guide_city("Brussels", "bruxelles-capitale/bruxelles"),
    guide_city("Vienna", "vienna/wien"),
    guide_city("Zurich", "zurich-region/zurich"),
    guide_city("Istanbul", "istanbul-province/istanbul"),
    guide_city("Dubai", "dubai-emirate/dubai"),
    guide_city("Abu Dhabi", "abu-dhabi-emirate/abu-dhabi"),
    guide_city("Toronto", "ontario/toronto"),
    guide_city("Vancouver", "british-columbia/ca-vancouver"),
    guide_city("Montreal", "quebec/montreal_2433514"),
    guide_city("Mexico City", "ciudad-de-mexico"),
    guide_city("Sao Paulo", "sao-paulo-region/sao-paulo"),
    guide_city("Buenos Aires", "ciudad-autonoma-de-buenos-aires/buenos-aires_7770009"),
)

NEW_YORK_BOROUGHS = frozenset({"Manhattan", "Brooklyn", "Queens", "The Bronx", "Staten Island"})
BAY_AREA_DISTRICTS = frozenset({"San Francisco", "East Bay", "South Bay", "Peninsula", "Marin"})
DESCRIBED_DISTRICTS = {"New York State": NEW_YORK_BOROUGHS, "California": BAY_AREA_DISTRICTS}  # Michelin's region, then its districts within it
