"""subway_arrivals (design doc v2/15): lines from the live feed only, directions named by each trip's last stop, the direction filter, alerts, and
what the tool says when MTA is slow or down.

tests/fixtures/mta_2026-11-21/ holds MTA's feeds as recorded at 5:09 PM on Saturday 2026-11-21, trimmed to the trips through Court Square,
Queensboro Plaza, and Queens Plaza, and to the alerts active then plus two upcoming ones. That evening the W (weekdays only) did not run, the F ran
via 21 St-Queensbridge instead of Court Sq-23 St and Queens Plaza, and the G had delays from a switch problem at Court Sq. The other tests build
feeds of their own, so one rule is tested at a time.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from google.transit import gtfs_realtime_pb2
from mcp.server.mcpserver import MCPServer

from assistant_core.agent_loop import filler_for
from assistant_core.models import AgentPolicy, Route, ToolCall
from assistant_core.router import DIRECTIVES
from assistant_core.tools import McpToolBox
from subway_mcp.build_stations import station_table
from subway_mcp.feeds import NYCT_TRIP, FeedClient
from subway_mcp.register import SERVICE_DOWN_MESSAGE, SUBWAY_TOOL_NAME, register_subway_tools
from subway_mcp.settings import ALERTS_FEED_NAME, SubwaySettings
from subway_mcp.stations import StationTable

SATURDAY_FEEDS = Path("tests/fixtures/mta_2026-11-21")
SATURDAY_EVENING = datetime.fromtimestamp(1795298995, UTC)  # 5:09:55 PM in New York, a few seconds after the feeds were written
SATURDAY_SETTINGS = SubwaySettings(fixtures_dir=SATURDAY_FEEDS, now=SATURDAY_EVENING)
MONDAY_MORNING = datetime(2026, 11, 23, 13, 0, tzinfo=UTC)
TABLE = StationTable.from_file()


async def ask(arguments: dict[str, Any], mta: "FakeMta | None" = None, client: FeedClient | None = None) -> str:
    """Asks on the recorded Saturday feeds, or on a fake MTA's feeds and clock, through one FeedClient when the test holds it across questions."""
    server = MCPServer("subway-test")
    if mta is None:
        register_subway_tools(server, SATURDAY_SETTINGS)
    else:
        register_subway_tools(server, SubwaySettings(), clock=mta.clock, feeds=client or mta.client())
    async with McpToolBox(server) as toolbox:
        return await toolbox.call(ToolCall(id="1", name=SUBWAY_TOOL_NAME, arguments=arguments))


def answer_lines(answer: str) -> list[str]:
    return answer.splitlines()


def lines_starting(answer: str, prefix: str) -> list[str]:
    return [line for line in answer_lines(answer) if line.startswith(prefix)]


async def test_a_saturday_at_queensboro_plaza_lists_the_lines_running_and_says_the_weekday_w_is_not_coming() -> None:
    answer = await ask({"station": "Queensboro Plaza"})
    assert answer_lines(answer)[0] == "Queensboro Plaza, as of 5:09 PM"
    assert lines_starting(answer, "7 toward Flushing-Main St: ") and lines_starting(answer, "N toward Astoria-Ditmars Blvd: ")
    assert lines_starting(answer, "7 toward 34 St-Hudson Yards (Manhattan): ")
    assert not lines_starting(answer, "W toward")
    assert "No W trains are coming. The W stops here in weekday daytime service." in answer_lines(answer)


async def test_court_square_drops_the_g_trains_ending_there_and_explains_the_f_running_elsewhere_that_day() -> None:
    answer = await ask({"station": "Court Square"})
    assert answer_lines(answer)[0] == "Court Sq, as of 5:09 PM"
    assert lines_starting(answer, "G toward Church Av (Brooklyn): ")
    assert not lines_starting(answer, "G toward Court Sq")
    assert "No F trains are coming. The F stops here in weekday daytime service." in answer_lines(answer)


async def test_court_square_carries_the_switch_problem_alert_with_line_bullets_said_as_words() -> None:
    alerts = lines_starting(await ask({"station": "Court Square"}), "Alert: ")
    assert "Alert: G trains are running with delays in both directions while we address a switch problem at Court Sq." in alerts
    assert "Alert: A, C and F trains are running with delays in both directions while we conduct planned work in Manhattan." in alerts


async def test_alerts_about_skipped_stops_elsewhere_on_a_line_stay_out() -> None:
    answer = await ask({"station": "Queensboro Plaza"})
    assert "skips" not in answer


async def test_a_line_narrows_the_answer_to_that_line() -> None:
    answer = await ask({"station": "Queens Plaza", "line": "e"})
    trains = [line for line in answer_lines(answer)[1:] if not line.startswith("Alert: ")]
    assert trains and all(line.startswith("E toward") for line in trains)


async def test_manhattan_keeps_every_train_that_reaches_manhattan_including_the_n_bound_for_coney_island() -> None:
    answer = await ask({"station": "Queensboro Plaza", "direction": "Manhattan-bound"})
    assert lines_starting(answer, "7 toward 34 St-Hudson Yards") and lines_starting(answer, "N toward Coney Island-Stillwell Av")
    assert not lines_starting(answer, "7 toward Flushing") and not lines_starting(answer, "N toward Astoria")


async def test_a_station_as_the_direction_keeps_the_trains_that_stop_there() -> None:
    answer = await ask({"station": "Queensboro Plaza", "direction": "toward Times Square"})
    assert lines_starting(answer, "7 toward 34 St-Hudson Yards") and lines_starting(answer, "N toward Coney Island-Stillwell Av")
    assert not lines_starting(answer, "N toward Astoria")


async def test_the_stations_own_borough_means_trains_that_end_their_run_in_it() -> None:
    answer = await ask({"station": "Court Square", "direction": "Queens"})
    assert lines_starting(answer, "7 toward Flushing-Main St") and lines_starting(answer, "E toward Jamaica Center")
    assert not lines_starting(answer, "7 toward 34 St-Hudson Yards") and not lines_starting(answer, "G toward")


async def test_uptown_and_a_platform_label_pick_mtas_north_direction() -> None:
    uptown = await ask({"station": "Queensboro Plaza", "direction": "uptown"})
    assert lines_starting(uptown, "7 toward Flushing-Main St") and lines_starting(uptown, "N toward Astoria-Ditmars Blvd")
    assert not lines_starting(uptown, "7 toward 34 St")
    astoria = await ask({"station": "Queensboro Plaza", "direction": "Astoria"})
    assert lines_starting(astoria, "N toward Astoria-Ditmars Blvd") and not lines_starting(astoria, "7 toward")


async def test_a_direction_no_train_takes_returns_both_ways_and_says_where_trains_here_go() -> None:
    answer = await ask({"station": "Court Square", "direction": "the Bronx"})
    assert answer_lines(answer)[1].startswith("No trains toward the Bronx in the next 40 minutes; trains here go toward Flushing-Main St, ")
    assert lines_starting(answer, "7 toward Flushing-Main St") and lines_starting(answer, "G toward Church Av")


async def test_a_shared_station_name_asks_which_one_and_a_line_settles_it() -> None:
    several = await ask({"station": "86 St"})
    assert several.startswith("Several stations are called 86 St: 86 St (1, Manhattan); ") and several.endswith("Ask the user which one.")
    assert (await ask({"station": "86th Street", "line": "Q"})).startswith("86 St, as of 5:09 PM")


async def test_an_unknown_station_asks_the_user_to_say_it_again() -> None:
    assert await ask({"station": "Narnia"}) == "Subway error: no station called Narnia was found. Ask the user to say the station again."


def test_queens_plaza_and_queensboro_plaza_stay_apart() -> None:
    assert [station.name for station in TABLE.find("Queens Plaza").stations] == ["Queens Plaza"]
    assert [station.name for station in TABLE.find("Queensboro").stations] == ["Queensboro Plaza"]


class FakeMta:
    """Answers like api-endpoint.mta.info: given train feeds by name, an empty feed for the rest, and the alerts given."""

    def __init__(self, now: datetime) -> None:
        self.now = now
        self.train_feeds: dict[str, bytes] = {}
        self.alerts: list[dict[str, Any]] = []
        self.written_at = now
        self.status = 200
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status)
        name = request.url.raw_path.decode().rsplit("/", 1)[1]
        if name == ALERTS_FEED_NAME:
            return httpx.Response(200, content=json.dumps({"entity": [{"id": str(index), "alert": alert} for index, alert in enumerate(self.alerts)]}))
        return httpx.Response(200, content=self.train_feeds.get(name) or feed_bytes([], self.written_at))

    def clock(self) -> datetime:
        return self.now

    def client(self) -> FeedClient:
        return FeedClient(SubwaySettings(), self.clock, transport=httpx.MockTransport(self.handle))


def feed_bytes(trips: list[tuple[str, list[tuple[str, datetime]], bool]], written_at: datetime) -> bytes:
    """A train feed: each trip is its route, its remaining stops with times, and whether MTA has assigned it."""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "1.0"
    feed.header.timestamp = int(written_at.timestamp())
    for index, (route, stops, assigned) in enumerate(trips):
        update = feed.entity.add(id=str(index)).trip_update
        update.trip.route_id = route
        update.trip.Extensions[NYCT_TRIP].is_assigned = assigned
        for stop_id, time in stops:
            update.stop_time_update.add(stop_id=stop_id).arrival.time = int(time.timestamp())
    return feed.SerializeToString()


def minutes_after(start: datetime, minutes: int) -> datetime:
    return start + timedelta(minutes=minutes)


async def test_a_rerouted_train_is_named_by_where_it_is_really_going() -> None:
    mta = FakeMta(MONDAY_MORNING)
    mta.train_feeds["nyct%2Fgtfs-ace"] = feed_bytes(
        [("E", [("G21S", minutes_after(MONDAY_MORNING, 4)), ("B04S", minutes_after(MONDAY_MORNING, 7)), ("B08S", minutes_after(MONDAY_MORNING, 10))], True)], MONDAY_MORNING
    )
    answer = await ask({"station": "Queens Plaza"}, mta)
    assert f"E toward {TABLE.stop_name('B08')} (Manhattan): 4 min" in answer_lines(answer)


async def test_a_train_not_yet_dispatched_is_said_to_be_scheduled() -> None:
    mta = FakeMta(MONDAY_MORNING)
    stops = [("718S", minutes_after(MONDAY_MORNING, 3)), ("725S", minutes_after(MONDAY_MORNING, 12))]
    mta.train_feeds["nyct%2Fgtfs"] = feed_bytes([("7", stops, False)], MONDAY_MORNING)
    assert lines_starting(await ask({"station": "Queensboro Plaza"}, mta), "7 toward Times Sq-42 St (Manhattan): 3 min (scheduled, not yet tracked)")


async def test_data_more_than_a_minute_behind_is_said_to_be_possibly_not_real_time() -> None:
    mta = FakeMta(MONDAY_MORNING)
    mta.written_at = MONDAY_MORNING - timedelta(seconds=150)
    assert answer_lines(await ask({"station": "Queens Plaza"}, mta))[1] == "These times are 3 minutes old and may not be real time."


async def test_a_held_copy_answers_while_mta_is_down_until_it_is_five_minutes_old() -> None:
    mta = FakeMta(MONDAY_MORNING)
    client = mta.client()
    await ask({"station": "Queens Plaza"}, mta, client)
    mta.status = 503
    mta.now = MONDAY_MORNING + timedelta(minutes=2)
    held = await ask({"station": "Queens Plaza"}, mta, client)
    assert answer_lines(held)[1] == "These times are 2 minutes old and may not be real time."
    mta.now = MONDAY_MORNING + timedelta(minutes=6)
    assert await ask({"station": "Queens Plaza"}, mta, client) == SERVICE_DOWN_MESSAGE


async def test_a_second_question_within_twenty_seconds_reuses_the_fetched_feeds() -> None:
    mta = FakeMta(MONDAY_MORNING)
    client = mta.client()
    await ask({"station": "Queens Plaza"}, mta, client)
    mta.now += timedelta(seconds=15)
    await ask({"station": "Court Square"}, mta, client)
    assert len(mta.requests) == 9


async def test_a_direction_through_a_station_a_rerouted_train_skips_does_not_keep_it() -> None:
    mta = FakeMta(MONDAY_MORNING)
    skipping = [("718S", minutes_after(MONDAY_MORNING, 3)), ("719S", minutes_after(MONDAY_MORNING, 5)), ("723S", minutes_after(MONDAY_MORNING, 9))]
    mta.train_feeds["nyct%2Fgtfs"] = feed_bytes([("7", skipping, True)], MONDAY_MORNING)
    answer = await ask({"station": "Queensboro Plaza", "direction": "Times Square"}, mta)
    assert answer_lines(answer)[1].startswith("No trains toward Times Square in the next 40 minutes")


async def test_an_alert_shows_when_it_names_the_station_or_its_line_alone_and_not_for_other_stops() -> None:
    mta = FakeMta(MONDAY_MORNING)
    mta.alerts = [
        alert_about("[7] trains are delayed.", routes=["7"]),
        alert_about("[7] skips 52 St.", routes=["7"], stops=["713N"]),
        alert_about("Elevator out at Queensboro Plaza.", routes=["N"], stops=["R09"]),
        alert_about("[G] trains are delayed.", routes=["G"]),
    ]
    alerts = lines_starting(await ask({"station": "Queensboro Plaza"}, mta), "Alert: ")
    assert alerts == ["Alert: 7 trains are delayed.", "Alert: Elevator out at Queensboro Plaza."]


async def test_an_alert_outside_its_active_period_is_left_out() -> None:
    mta = FakeMta(MONDAY_MORNING)
    tomorrow = MONDAY_MORNING + timedelta(days=1)
    mta.alerts = [alert_about("[7] trains run local.", routes=["7"], active=(tomorrow, tomorrow + timedelta(hours=4)))]
    assert "Alert:" not in await ask({"station": "Queensboro Plaza"}, mta)


def alert_about(header: str, routes: list[str], stops: list[str] | None = None, active: tuple[datetime, datetime] | None = None) -> dict[str, Any]:
    informed = [{"route_id": route} for route in routes] + [{"stop_id": stop} for stop in stops or []]
    periods = [{"start": int(active[0].timestamp()), "end": int(active[1].timestamp())}] if active else []
    return {"active_period": periods, "informed_entity": informed, "header_text": {"translation": [{"text": header, "language": "en"}, {"text": f"<p>{header}</p>", "language": "en-html"}]}}


def test_the_station_table_groups_stops_into_complexes_with_spoken_boroughs() -> None:
    rows = [
        {"gtfs_stop_id": "F09", "complex_id": "606", "stop_name": "Court Sq-23 St", "daytime_routes": "E F", "north_direction_label": "Outbound", "south_direction_label": "Manhattan", "borough": "Q"},
        {"gtfs_stop_id": "G22", "complex_id": "606", "stop_name": "Court Sq", "daytime_routes": "G", "north_direction_label": "Last Stop", "south_direction_label": "Brooklyn", "borough": "Q"},
        {
            "gtfs_stop_id": "101",
            "complex_id": "293",
            "stop_name": "Van Cortlandt Park-242 St",
            "daytime_routes": "1",
            "north_direction_label": "",
            "south_direction_label": "Manhattan",
            "borough": "Bx",
        },
    ]
    stations = station_table(rows)
    assert [station["complex_id"] for station in stations] == ["293", "606"]
    assert [(stop["stop_id"], stop["daytime_lines"], stop["borough"]) for stop in stations[1]["stops"]] == [("F09", ["E", "F"], "Queens"), ("G22", ["G"], "Queens")]


def test_the_filler_names_the_trains_and_is_dropped_from_replayed_answers() -> None:
    policy = AgentPolicy()
    assert filler_for(SUBWAY_TOOL_NAME, policy) in policy.subway_filler_phrases
    assert set(policy.subway_filler_phrases) <= set(policy.every_filler_phrase)


def test_the_subway_directive_names_the_tool_and_asks_for_a_station_when_none_was_named() -> None:
    assert "subway_arrivals" in DIRECTIVES[Route.SUBWAY] and "ask which station" in DIRECTIVES[Route.SUBWAY]
