"""The text the model speaks from: the station's name first, then one line per line and direction, then missing lines and alerts (design doc v2/15
section 3.3). The station name always leads, because Queens Plaza and Queensboro Plaza are a block apart and speech to text can swap them."""

import math
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from subway_mcp.arrivals import ArrivalGroup, StationBoard
from subway_mcp.stations import Station, StationTable
from utils.text_utils import spoken_time

NEW_YORK = ZoneInfo("America/New_York")
UNSPOKEN_LABELS = frozenset({"", "Outbound", "Last Stop"})
COMPASS_LABELS = frozenset({"Uptown", "Downtown", "Northbound", "Southbound"})


@dataclass(frozen=True)
class StationAnswer:
    station: Station
    board: StationBoard
    alerts: list[str]
    direction: str  # as the user said it; "" for both ways
    now: datetime
    stale_seconds: float  # how far behind the data is, or 0 while it is current
    window_minutes: int


def answer_text(answer: StationAnswer, table: StationTable) -> str:
    board = answer.board
    lines = [f"{answer.station.name}, as of {spoken_time(answer.now, NEW_YORK)}"]
    lines.extend(staleness_lines(answer.stale_seconds))
    if board.direction_unmatched:
        lines.append(f"No trains toward {answer.direction} in the next {answer.window_minutes} minutes; trains here go toward {spoken_list(destinations(board, table))}.")
    if not board.groups:
        lines.append(f"No trains are due here in the next {answer.window_minutes} minutes.")
    lines.extend(group_line(group, table) for group in board.groups)
    lines.extend(f"No {line} trains are coming. The {line} stops here in weekday daytime service." for line in board.missing_lines)
    lines.extend(f"Alert: {alert}" for alert in answer.alerts)
    return "\n".join(lines)


def staleness_lines(stale_seconds: float) -> list[str]:
    """MTA's terms ask for a warning once data may be more than a minute behind (design doc v2/15 section 3.8, item 6)."""
    if stale_seconds <= 0:
        return []
    return [f"These times are {math.ceil(stale_seconds / 60)} minutes old and may not be real time."]


def group_line(group: ArrivalGroup, table: StationTable) -> str:
    minutes = ", ".join("now" if arrival.minutes == 0 else str(arrival.minutes) for arrival in group.arrivals)
    unit = "" if minutes == "now" else " min"
    scheduled = " (scheduled, not yet tracked)" if group.scheduled_only else ""
    return f"{group.line} toward {table.stop_name(group.last_stop_id)}{direction_label(group, table)}: {minutes}{unit}{scheduled}"


def direction_label(group: ArrivalGroup, table: StationTable) -> str:
    """MTA's name for the platform's direction, such as "Manhattan", when it adds something the last stop does not already say."""
    label = group.stop.label_for(group.direction)
    if label in UNSPOKEN_LABELS or label.lower() in table.stop_name(group.last_stop_id).lower():
        return ""
    return f" ({label.lower() if label in COMPASS_LABELS else label})"


def destinations(board: StationBoard, table: StationTable) -> list[str]:
    return list(dict.fromkeys(table.stop_name(group.last_stop_id) for group in board.groups))


def spoken_list(items: list[str]) -> str:
    if len(items) <= 2:
        return " and ".join(items)
    return f"{', '.join(items[:-1])}, and {items[-1]}"
