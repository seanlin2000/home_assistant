"""The station table, and finding the station a user named in it (design doc v2/15 section 3.2).

A station is one MTA complex: the stops a rider can transfer between without leaving the system, such as Court Square's three platforms. Names are
matched loosely with the same matcher the listings tools use, after the table's abbreviations are spelled out, so "Court Square" finds "Court Sq"
and "Times Square" finds "Times Sq-42 St".
"""

import json
import re
from collections import Counter
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from subway_mcp.build_stations import STATIONS_PATH
from utils.title_matching_utils import TitleMatcher

WORDS_AROUND_A_STATION = frozenset({"the", "station", "stop", "subway", "train", "trains"})
SPELLED_OUT_WORDS = {
    "sq": "square",
    "av": "avenue",
    "ave": "avenue",
    "blvd": "boulevard",
    "pkwy": "parkway",
    "hts": "heights",
    "ctr": "center",
    "pl": "place",
    "rd": "road",
    "jct": "junction",
    "ft": "fort",
    "hwy": "highway",
    "sts": "streets",
    "avs": "avenues",
}
SAINT_ABBREVIATION = "st"  # "St George" is a saint, "86 St" a street: the first word of a name is the saint
ORDINAL_NUMBER = re.compile(r"\b(\d+)(st|nd|rd|th)\b")


@dataclass(frozen=True)
class Stop:
    stop_id: str
    name: str
    daytime_lines: tuple[str, ...]
    north_label: str
    south_label: str
    borough: str

    def label_for(self, direction: str) -> str:
        return self.north_label if direction == "N" else self.south_label


@dataclass(frozen=True)
class Station:
    complex_id: str
    stops: tuple[Stop, ...]

    @cached_property
    def name(self) -> str:
        """The name most of its platforms carry, the shortest among equals: Court Square's three are "Court Sq", "Court Sq", and "Court Sq-23 St"."""
        counts = Counter(stop.name for stop in self.stops)
        return min(counts, key=lambda name: (-counts[name], len(name)))

    @cached_property
    def stop_ids(self) -> frozenset[str]:
        return frozenset(stop.stop_id for stop in self.stops)

    @cached_property
    def daytime_lines(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(line for stop in self.stops for line in stop.daytime_lines))

    @property
    def borough(self) -> str:
        return self.stops[0].borough

    def stop(self, stop_id: str) -> Stop:
        return next(stop for stop in self.stops if stop.stop_id == stop_id)

    def described(self) -> str:
        return f"{self.name} ({' '.join(self.daytime_lines)}, {self.borough})"


@dataclass(frozen=True)
class StationMatches:
    asked: str
    stations: tuple[Station, ...]  # empty when nothing matched; several when the name is shared


class StationTable:
    def __init__(self, stations: list[Station]) -> None:
        self.stations = stations
        self.stops_by_id = {stop.stop_id: stop for station in stations for stop in station.stops}
        self._stations_by_name: dict[str, list[Station]] = {}
        for station in stations:
            for spoken_name in dict.fromkeys(spoken_station_name(stop.name) for stop in station.stops):
                self._stations_by_name.setdefault(spoken_name, []).append(station)
        self._matcher = TitleMatcher(WORDS_AROUND_A_STATION)

    @classmethod
    def from_file(cls, path: Path = STATIONS_PATH) -> "StationTable":
        return cls([station_from_entry(entry) for entry in json.loads(path.read_text())])

    def find(self, asked: str, line: str = "") -> StationMatches:
        """The stations whose names fit best. A line narrows a shared name to the stations it serves in the daytime, unless it serves none of them."""
        matched = self._matcher.matches(spoken_station_name(asked), list(self._stations_by_name))
        stations = list(dict.fromkeys(station for name in matched.titles for station in self._stations_by_name[name]))
        on_line = [station for station in stations if line and line in station.daytime_lines]
        return StationMatches(asked=asked, stations=tuple(on_line if len(stations) > 1 and on_line else stations))

    def stop_name(self, stop_id: str) -> str:
        stop = self.stops_by_id.get(stop_id)
        return stop.name if stop else stop_id

    def borough_of(self, stop_id: str) -> str:
        stop = self.stops_by_id.get(stop_id)
        return stop.borough if stop else ""


def station_from_entry(entry: dict) -> Station:
    return Station(complex_id=entry["complex_id"], stops=tuple(stop_from_entry(stop) for stop in entry["stops"]))


def stop_from_entry(entry: dict) -> Stop:
    return Stop(
        stop_id=entry["stop_id"],
        name=entry["name"],
        daytime_lines=tuple(entry["daytime_lines"]),
        north_label=entry["north_label"],
        south_label=entry["south_label"],
        borough=entry["borough"],
    )


def spoken_station_name(name: str) -> str:
    """The name as it is said: abbreviations spelled out, ordinals as bare numbers ("86th" is "86"), and a leading St as Saint."""
    words = re.sub(r"[^A-Za-z0-9']+", " ", ORDINAL_NUMBER.sub(r"\1", name.lower())).split()
    spoken = ["saint" if index == 0 and word == SAINT_ABBREVIATION else spelled_out(word) for index, word in enumerate(words)]
    return " ".join(spoken)


def spelled_out(word: str) -> str:
    if word == SAINT_ABBREVIATION:
        return "street"
    return SPELLED_OUT_WORDS.get(word, word)
