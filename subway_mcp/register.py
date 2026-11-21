"""Expose live subway arrivals as an MCP tool on the shared tool server (design doc v2/15 section 3.6).

The tool's rules live in its own description, since prompt 3.0 moved each tool's rules into its definition. Station names are matched against the
checked-in table on this machine; only fixed feed addresses reach MTA.
"""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from subway_mcp.alerts import station_alerts
from subway_mcp.arrivals import ArrivalsRequest, station_board
from subway_mcp.feeds import FeedClient, FeedSnapshot, SubwayUnavailable, utc_now
from subway_mcp.render import StationAnswer, answer_text
from subway_mcp.settings import SubwaySettings
from subway_mcp.stations import StationMatches, StationTable

SUBWAY_TOOL_NAME = "subway_arrivals"
MAX_STATION_CHARS = 60
MAX_LINE_CHARS = 3
MAX_DIRECTION_CHARS = 40
STATION_NOT_FOUND_MESSAGE = "Subway error: no station called {station} was found. Ask the user to say the station again."
SEVERAL_STATIONS_MESSAGE = "Several stations are called {station}: {stations}. Ask the user which one."
SERVICE_DOWN_MESSAGE = "Subway error: MTA's train times did not answer. Tell the user you could not get train times right now."
_LOGGER = logging.getLogger(__name__)


def register_subway_tools(server: MCPServer, settings: SubwaySettings, clock: Callable[[], datetime] = utc_now, feeds: FeedClient | None = None) -> None:
    table = StationTable.from_file()
    moment = (lambda: settings.now) if settings.now else clock
    client = feeds or FeedClient(settings, moment)

    @server.tool(name=SUBWAY_TOOL_NAME)
    async def subway_arrivals(
        station: Annotated[str, Field(max_length=MAX_STATION_CHARS, description='New York City subway station as the user said it, e.g. "Court Square", "Queensboro Plaza", "Times Square"')],
        line: Annotated[str, Field(max_length=MAX_LINE_CHARS, description='one line, e.g. "7", "E", "N"; empty for every line at the station')] = "",
        direction: Annotated[
            str,
            Field(
                max_length=MAX_DIRECTION_CHARS, description='where the user is going, as they said it: a station ("Times Square"), a borough ("Manhattan") or "uptown"/"downtown"; empty for both ways'
            ),
        ] = "",
    ) -> str:
        """Live New York City subway arrivals at one station: which lines are running now, the next trains each way with minutes until they arrive, and MTA service alerts there. Use this, never a web search, for subway times or whether a line is running at a station. If the user names no station, ask which station; do not guess one. Say the station name the result gives, since similar names differ. Give the minutes as listed, and mention an alert in one short sentence."""
        line = line.strip().upper()
        matches = table.find(station.strip(), line)
        if len(matches.stations) != 1:
            return station_match_message(matches)
        try:
            snapshot = await client.snapshot()
        except SubwayUnavailable as error:
            _LOGGER.warning("%s failed: %s", SUBWAY_TOOL_NAME, error)
            return SERVICE_DOWN_MESSAGE
        request = ArrivalsRequest(station=matches.stations[0], line=line, direction=direction.strip())
        return answer_text(station_answer(snapshot, request, table, moment(), settings), table)


def station_match_message(matches: StationMatches) -> str:
    if not matches.stations:
        return STATION_NOT_FOUND_MESSAGE.format(station=matches.asked)
    return SEVERAL_STATIONS_MESSAGE.format(station=matches.asked, stations="; ".join(station.described() for station in matches.stations))


def station_answer(snapshot: FeedSnapshot, request: ArrivalsRequest, table: StationTable, now: datetime, settings: SubwaySettings) -> StationAnswer:
    board = station_board(snapshot, request, table, now, settings)
    lines = {request.line} if request.line else {group.line for group in board.groups} | set(request.station.daytime_lines)
    age_seconds = (now - snapshot.written_at).total_seconds()
    return StationAnswer(
        station=request.station,
        board=board,
        alerts=station_alerts(snapshot.alerts, request.station, lines, now, settings),
        direction=request.direction,
        now=now,
        stale_seconds=age_seconds if age_seconds > settings.stale_after_seconds else 0,
        window_minutes=settings.window_minutes,
    )
