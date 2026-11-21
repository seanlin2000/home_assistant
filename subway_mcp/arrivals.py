"""From live trips to what is coming at one station (design doc v2/15 section 3.3).

Lines come only from the trips in the feed. Each trip is grouped by its line, its direction, and its own last stop, so a rerouted train is named by
where it is really going. A train that ends its run at the station is left out, since nobody can board it there. The station's usual daytime lines
are used only to say that one of them has no train coming.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from subway_mcp.directions import direction_test
from subway_mcp.feeds import FeedSnapshot, Trip
from subway_mcp.settings import SubwaySettings
from subway_mcp.stations import Station, StationTable, Stop


@dataclass(frozen=True)
class ArrivalsRequest:
    station: Station
    line: str  # "" for every line
    direction: str  # "" for both ways


@dataclass(frozen=True)
class Arrival:
    trip: Trip
    stop: Stop  # the platform the trip stops at
    minutes: int


@dataclass
class ArrivalGroup:
    line: str
    direction: str
    last_stop_id: str
    stop: Stop
    arrivals: list[Arrival] = field(default_factory=list)

    @property
    def scheduled_only(self) -> bool:
        return not any(arrival.trip.assigned for arrival in self.arrivals)


@dataclass(frozen=True)
class StationBoard:
    groups: list[ArrivalGroup]
    missing_lines: list[str]  # daytime lines with no train in the window
    direction_unmatched: bool  # a direction was asked for and no train goes that way; groups then holds both ways


def station_board(snapshot: FeedSnapshot, request: ArrivalsRequest, table: StationTable, now: datetime, settings: SubwaySettings) -> StationBoard:
    arrivals = list(upcoming_arrivals(snapshot, request, now, settings))
    test = direction_test(request.direction, request.station, table) if request.direction else None
    kept = [arrival for arrival in arrivals if test is None or test(arrival.trip, stop_index(arrival.trip, request.station), arrival.stop)]
    direction_unmatched = bool(request.direction) and bool(arrivals) and (test is None or not kept)
    groups = grouped(arrivals if direction_unmatched else kept, settings.trains_per_direction)
    return StationBoard(groups=groups, missing_lines=missing_lines(request, arrivals), direction_unmatched=direction_unmatched)


def upcoming_arrivals(snapshot: FeedSnapshot, request: ArrivalsRequest, now: datetime, settings: SubwaySettings) -> Iterator[Arrival]:
    window_end = now + timedelta(minutes=settings.window_minutes)
    for trip in snapshot.trips:
        index = stop_index(trip, request.station)
        if index < 0 or index == len(trip.stops) - 1 or (request.line and trip.line != request.line):
            continue
        arrives = trip.stops[index].time
        if now <= arrives <= window_end:
            yield Arrival(trip=trip, stop=request.station.stop(trip.stops[index].stop_id), minutes=int((arrives - now).total_seconds() // 60))


def stop_index(trip: Trip, station: Station) -> int:
    return next((index for index, stop in enumerate(trip.stops) if stop.stop_id in station.stop_ids), -1)


def grouped(arrivals: list[Arrival], trains_per_direction: int) -> list[ArrivalGroup]:
    groups: dict[tuple[str, str, str], ArrivalGroup] = {}
    for arrival in sorted(arrivals, key=lambda arrival: arrival.minutes):
        key = (arrival.trip.line, arrival.trip.direction, arrival.trip.stops[-1].stop_id)
        group = groups.setdefault(key, ArrivalGroup(line=key[0], direction=key[1], last_stop_id=key[2], stop=arrival.stop))
        if len(group.arrivals) < trains_per_direction:
            group.arrivals.append(arrival)
    return sorted(groups.values(), key=lambda group: (group.line, group.direction, group.arrivals[0].minutes))


def missing_lines(request: ArrivalsRequest, arrivals: list[Arrival]) -> list[str]:
    running = {arrival.trip.line for arrival in arrivals}
    usual = [line for line in request.station.daytime_lines if not request.line or line == request.line]
    return [line for line in usual if line not in running]
