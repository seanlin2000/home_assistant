"""Fetches MTA's subway feeds and turns them into trips and alerts (design doc v2/15 section 3.1).

Every call reads all eight train feeds and the alerts feed together, because a rerouted train can arrive in another line's feed. A fetched copy is
reused for cache_seconds; when MTA does not answer, a copy up to keep_stale_seconds old answers instead, and the answer says how old it is.

MTA adds fields to GTFS-realtime in its own extension, nyct-subway.proto. The one read here, is_assigned (field 2 of NyctTripDescriptor, which
extends TripDescriptor as field 1001), says whether a train has a crew and has been dispatched. It is registered below from those field numbers, so
no generated protobuf module is checked in.
"""

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from subway_mcp.settings import ALERTS_FEED_NAME, TRAIN_FEED_NAMES, SubwaySettings

NYCT_TRIP_DESCRIPTOR_FIELD = 1001
NYCT_PROTO_NAME = "subway_mcp/nyct_subway.proto"
DIRECTION_LETTERS = ("N", "S")


class SubwayUnavailable(RuntimeError):
    """MTA's feeds could not be read and no copy recent enough is held."""


@dataclass(frozen=True)
class TripStop:
    stop_id: str  # the station's stop, without the direction letter MTA appends
    time: datetime


@dataclass(frozen=True)
class Trip:
    line: str
    direction: str  # "N" or "S", MTA's direction, not the compass
    stops: tuple[TripStop, ...]  # the stops still ahead of the train, in order
    assigned: bool


@dataclass(frozen=True)
class FeedSnapshot:
    trips: tuple[Trip, ...]
    alerts: tuple[dict[str, Any], ...]
    written_at: datetime  # the oldest train feed's own timestamp, which says how current the predictions are
    fetched_at: datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def nyct_trip_extension() -> Any:
    """The is_assigned extension, added to protobuf's default pool once per process."""
    pool = descriptor_pool.Default()
    try:
        return pool.FindExtensionByName("subway_mcp.nyct.nyct_trip_descriptor")
    except KeyError:
        pass
    field = descriptor_pb2.FieldDescriptorProto
    proto = descriptor_pb2.FileDescriptorProto(name=NYCT_PROTO_NAME, package="subway_mcp.nyct", dependency=["gtfs-realtime.proto"], syntax="proto2")
    message = proto.message_type.add(name="NyctTripDescriptor")
    message.field.add(name="train_id", number=1, type=field.TYPE_STRING, label=field.LABEL_OPTIONAL)
    message.field.add(name="is_assigned", number=2, type=field.TYPE_BOOL, label=field.LABEL_OPTIONAL)
    proto.extension.add(
        name="nyct_trip_descriptor",
        number=NYCT_TRIP_DESCRIPTOR_FIELD,
        type=field.TYPE_MESSAGE,
        label=field.LABEL_OPTIONAL,
        type_name=".subway_mcp.nyct.NyctTripDescriptor",
        extendee=".transit_realtime.TripDescriptor",
    )
    pool.Add(proto)
    message_factory.GetMessageClassesForFiles([NYCT_PROTO_NAME], pool)
    return pool.FindExtensionByName("subway_mcp.nyct.nyct_trip_descriptor")


NYCT_TRIP = nyct_trip_extension()


class FeedClient:
    def __init__(self, settings: SubwaySettings, clock: Callable[[], datetime] = utc_now, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._settings = settings
        self._clock = clock
        self._transport = transport
        self._held: FeedSnapshot | None = None

    async def snapshot(self) -> FeedSnapshot:
        now = self._clock()
        if self._held is not None and now - self._held.fetched_at < timedelta(seconds=self._settings.cache_seconds):
            return self._held
        try:
            self._held = await self._read_feeds(now)
        except SubwayUnavailable:
            if self._held is None or now - self._held.fetched_at > timedelta(seconds=self._settings.keep_stale_seconds):
                raise
        return self._held

    async def _read_feeds(self, now: datetime) -> FeedSnapshot:
        names = [*TRAIN_FEED_NAMES, ALERTS_FEED_NAME]
        bodies = await self._fixture_bodies(names) if self._settings.fixtures_dir else await self._fetched_bodies(names)
        train_feeds = [parsed_feed(body) for body in bodies[:-1]]
        return FeedSnapshot(
            trips=tuple(trip for feed in train_feeds for trip in trips_in(feed)),
            alerts=tuple(alerts_in(bodies[-1])),
            written_at=min(datetime.fromtimestamp(feed.header.timestamp, UTC) for feed in train_feeds),
            fetched_at=now,
        )

    async def _fetched_bodies(self, names: list[str]) -> list[bytes]:
        headers = {"User-Agent": self._settings.user_agent}
        try:
            async with httpx.AsyncClient(timeout=self._settings.timeout_seconds, transport=self._transport, headers=headers) as client:
                responses = await asyncio.gather(*(client.get(self._settings.feeds_base_url + name) for name in names))
        except httpx.HTTPError as error:
            raise SubwayUnavailable(f"no answer from MTA ({type(error).__name__})") from error
        failed = [name for name, response in zip(names, responses) if response.status_code != 200]
        if failed:
            raise SubwayUnavailable(f"MTA answered {responses[names.index(failed[0])].status_code} for {failed[0]}")
        return [response.content for response in responses]

    async def _fixture_bodies(self, names: list[str]) -> list[bytes]:
        return [fixture_path(self._settings.fixtures_dir, name).read_bytes() for name in names]


def fixture_path(fixtures_dir: Path, feed_name: str) -> Path:
    """A recorded feed's file: nyct%2Fgtfs-ace is mta_gtfs-ace.pb, camsys%2Fsubway-alerts.json is mta_subway-alerts.json."""
    base = feed_name.split("%2F", 1)[1]
    return fixtures_dir / f"mta_{base}{'' if base.endswith('.json') else '.pb'}"


def parsed_feed(body: bytes) -> gtfs_realtime_pb2.FeedMessage:
    feed = gtfs_realtime_pb2.FeedMessage()
    try:
        feed.ParseFromString(body)
    except DecodeError as error:
        raise SubwayUnavailable("MTA sent a train feed that could not be read") from error
    return feed


def trips_in(feed: gtfs_realtime_pb2.FeedMessage) -> list[Trip]:
    return [trip for entity in feed.entity if entity.HasField("trip_update") and (trip := trip_from(entity.trip_update)) is not None]


def trip_from(update: gtfs_realtime_pb2.TripUpdate) -> Trip | None:
    stops = tuple(TripStop(stop_id=stop.stop_id[:-1], time=datetime.fromtimestamp(stop.arrival.time or stop.departure.time, UTC)) for stop in update.stop_time_update if stop_time(stop))
    directions = {stop.stop_id[-1] for stop in update.stop_time_update if stop.stop_id[-1:] in DIRECTION_LETTERS}
    if not stops or len(directions) != 1:
        return None
    return Trip(line=line_of(update.trip.route_id), direction=directions.pop(), stops=stops, assigned=update.trip.Extensions[NYCT_TRIP].is_assigned)


def stop_time(stop: gtfs_realtime_pb2.TripUpdate.StopTimeUpdate) -> int:
    return stop.arrival.time or stop.departure.time


def line_of(route_id: str) -> str:
    """A diamond express runs as its line: MTA's 6X, 7X and FX are the 6, the 7 and the F."""
    return route_id[:-1] if len(route_id) > 1 and route_id.endswith("X") else route_id


def alerts_in(body: bytes) -> list[dict[str, Any]]:
    try:
        document = json.loads(body)
    except ValueError as error:
        raise SubwayUnavailable("MTA sent an alerts feed that could not be read") from error
    return [entity["alert"] for entity in document.get("entity", []) if "alert" in entity]
