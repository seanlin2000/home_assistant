"""Which way a user means, matched against each live trip's own remaining stops (design doc v2/15 section 3.4).

Nothing here is a table of where lines go, so a reroute or a weekend pattern is followed: the trip's stops are the ones MTA predicts for it now.
Closed sets of words are tried before station names, so "Queens" is the borough, not Queens Plaza. The first rule that recognises the words
decides, even when it keeps no train; the caller then says where the trains here do go.
"""

import re
from collections.abc import Callable

from subway_mcp.feeds import Trip
from subway_mcp.stations import Station, StationTable, Stop, spoken_station_name

BOROUGHS = {"manhattan": "Manhattan", "brooklyn": "Brooklyn", "queens": "Queens", "bronx": "Bronx", "staten island": "Staten Island"}
COMPASS_WORDS = {"uptown": "N", "northbound": "N", "north": "N", "downtown": "S", "southbound": "S", "south": "S"}
WORDS_AROUND_A_DIRECTION = re.compile(r"\b(the|to|toward|towards|going|heading|bound|trains?|direction)\b")

TripTest = Callable[[Trip, int, Stop], bool]  # the trip, the index of this station in its stops, and the platform it stops at


def direction_test(asked: str, station: Station, table: StationTable) -> TripTest | None:
    """The test the words call for, or None when they name nothing known."""
    words = plain_direction(asked)
    if not words:
        return None
    for rule in (borough_test, compass_test, label_test, station_name_test):
        test = rule(words, station, table)
        if test is not None:
            return test
    return None


def plain_direction(asked: str) -> str:
    return " ".join(WORDS_AROUND_A_DIRECTION.sub(" ", re.sub(r"[^a-z ]", " ", asked.lower())).split())


def borough_test(words: str, station: Station, table: StationTable) -> TripTest | None:
    borough = BOROUGHS.get(words)
    if borough is None:
        return None
    if borough == station.borough:
        return lambda trip, index, stop: table.borough_of(trip.stops[-1].stop_id) == borough
    return lambda trip, index, stop: any(table.borough_of(ahead.stop_id) == borough for ahead in trip.stops[index + 1 :])


def compass_test(words: str, station: Station, table: StationTable) -> TripTest | None:
    direction = COMPASS_WORDS.get(words)
    if direction is None:
        return None
    return lambda trip, index, stop: trip.direction == direction


def label_test(words: str, station: Station, table: StationTable) -> TripTest | None:
    if not any(words == plain_direction(stop.label_for(direction)) for stop in station.stops for direction in ("N", "S")):
        return None
    return lambda trip, index, stop: words == plain_direction(stop.label_for(trip.direction))


def station_name_test(words: str, station: Station, table: StationTable) -> TripTest | None:
    destinations = table.find(spoken_station_name(words)).stations
    if not destinations:
        return None
    stop_ids = frozenset(stop_id for destination in destinations for stop_id in destination.stop_ids) - station.stop_ids
    return lambda trip, index, stop: any(ahead.stop_id in stop_ids for ahead in trip.stops[index + 1 :])
