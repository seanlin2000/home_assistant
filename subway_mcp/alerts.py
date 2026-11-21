"""MTA's service alerts that matter at one station (design doc v2/15 section 3.5).

An alert counts when it is active now and names one of the station's stops, or names one of its lines and no stops at all, as line-wide delays do.
A notice about skipped stops elsewhere on a line names those stops, so it is left out. Only the header is used, never the long description.
"""

import re
from datetime import UTC, datetime
from typing import Any

from subway_mcp.settings import SubwaySettings
from subway_mcp.stations import Station
from utils.text_utils import clip_to_words

LINE_BULLETS = re.compile(r"(?:\[[A-Z0-9]+\])+")  # "[A][C][F]" is said "A, C and F"
BULLET_NAME = re.compile(r"\[([A-Z0-9]+)\]")
SENTENCE_END = (".", "!", "?", ":")
ENGLISH = "en"


def station_alerts(alerts: tuple[dict[str, Any], ...], station: Station, lines: set[str], now: datetime, settings: SubwaySettings) -> list[str]:
    headers = [header_text(alert) for alert in alerts if is_active(alert, now) and concerns_station(alert, station, lines)]
    spoken = [clip_to_words(header, settings.alert_words) for header in dict.fromkeys(headers) if header]
    return spoken[: settings.max_alerts]


def is_active(alert: dict[str, Any], now: datetime) -> bool:
    periods = alert.get("active_period") or [{}]
    moment = now.astimezone(UTC).timestamp()
    return any(float(period.get("start", 0)) <= moment <= float(period.get("end", "inf")) for period in periods)


def concerns_station(alert: dict[str, Any], station: Station, lines: set[str]) -> bool:
    informed = alert.get("informed_entity", [])
    stops = {parent_stop_id(entity["stop_id"]) for entity in informed if entity.get("stop_id")}
    routes = {entity["route_id"] for entity in informed if entity.get("route_id")}
    if stops:
        return bool(stops & station.stop_ids) and (not routes or bool(routes & lines))
    return bool(routes & lines)


def parent_stop_id(stop_id: str) -> str:
    return stop_id[:-1] if stop_id[-1:] in ("N", "S") and len(stop_id) > 3 else stop_id


def header_text(alert: dict[str, Any]) -> str:
    """The English header in one line: "[F]" said as "F", and its lines joined as sentences."""
    translations = alert.get("header_text", {}).get("translation", [])
    text = next((translation["text"] for translation in translations if translation.get("language") == ENGLISH), "")
    lines = [" ".join(line.split()) for line in LINE_BULLETS.sub(spoken_lines, text).splitlines() if line.strip()]
    return " ".join(line if line.endswith(SENTENCE_END) else f"{line}." for line in lines)


def spoken_lines(bullets: re.Match) -> str:
    names = BULLET_NAME.findall(bullets.group(0))
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
