"""Turns a Met.no Locationforecast document into the few lines the model reads: one line per part of a day, or one line per day.

Met.no reports the weather in blocks: one hour long for the first two to three days, six hours long after that, stamped in UTC. Each block is
assigned to the local part of the day (or the local day) that contains its midpoint, so a six-hour block lands in one period even when the home
time zone does not line up with Met.no's six-hour grid. Everything the model reads is rounded, in local time, and in the home unit system,
because every extra token costs prefill time on the Mac and the answer is spoken, not read.
"""

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

TODAY = "today"
TOMORROW = "tomorrow"
WEEK = "week"
WEEKEND = "weekend"
WHOLE_DAY = "all"
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
SATURDAY, SUNDAY = 5, 6
DAYS_IN_WEEK_VIEW = 7
# Hours from the day's midnight. Night runs past midnight: "tomorrow night" is the night that follows tomorrow evening.
PARTS_OF_DAY = {"morning": (6, 12), "afternoon": (12, 18), "evening": (18, 24), "night": (24, 30)}
CLOCK_WORDS = {0: "midnight", 6: "6 am", 12: "noon", 18: "6 pm", 24: "midnight", 30: "6 am"}
WHOLE_DAY_WORDS = frozenset({WHOLE_DAY, "", "day", "whole day", "whole_day", "all day", "any"})

SKY_WORDS = {"clearsky": "clear", "fair": "mostly clear", "partlycloudy": "partly cloudy", "cloudy": "cloudy", "fog": "fog"}
# Every precipitation symbol in Met.no's legend (github.com/metno/weathericons, weather/legend.csv) has this shape. "lights" is not a typo here:
# Met.no spells two of its symbols that way (lightssleetshowersandthunder, lightssnowshowersandthunder).
PRECIPITATION_SYMBOL = re.compile(r"^(?P<intensity>lights?|heavy)?(?P<kind>rain|sleet|snow)(?P<showers>showers)?(?P<thunder>andthunder)?$")


class ForecastRequestError(ValueError):
    """Arguments the model should correct, described in plain words."""


@dataclass(frozen=True)
class UnitSystem:
    temperature_symbol: str
    precipitation_unit: str
    precipitation_decimals: int
    wind_unit: str
    from_celsius: Callable[[float], float]
    from_millimetres: Callable[[float], float]
    from_metres_per_second: Callable[[float], float]


UNIT_SYSTEMS = {
    "metric": UnitSystem("°C", "mm", 1, "km/h", lambda celsius: celsius, lambda millimetres: millimetres, lambda speed: speed * 3.6),
    "imperial": UnitSystem("°F", "in", 2, "mph", lambda celsius: celsius * 9 / 5 + 32, lambda millimetres: millimetres / 25.4, lambda speed: speed * 2.23694),
}


@dataclass(frozen=True)
class Block:
    """One forecast interval, in Met.no's own units (degrees Celsius, millimetres, metres per second)."""

    start: datetime
    end: datetime
    temperature_low: float
    temperature_high: float
    symbol: str | None
    precipitation_mm: float
    precipitation_probability: float | None
    wind_speed: float

    @property
    def midpoint(self) -> datetime:
        return self.start + (self.end - self.start) / 2


@dataclass(frozen=True)
class Period:
    label: str
    start: datetime
    end: datetime


def blocks_from_document(document: dict[str, Any]) -> list[Block]:
    entries = document["properties"]["timeseries"]
    following_times = [entry_time(entry) for entry in entries[1:]] + [None]
    return [block for entry, following in zip(entries, following_times) if (block := block_from_entry(entry, following)) is not None]


def entry_time(entry: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(entry["time"])


def block_from_entry(entry: dict[str, Any], following: datetime | None) -> Block | None:
    """An hourly entry carries both a one-hour and a six-hour summary; the one-hour summary is used while the next entry is an hour away, so blocks
    never overlap. The last entries carry no summary at all and are skipped."""
    data = entry["data"]
    start = entry_time(entry)
    hourly = following is not None and following - start == timedelta(hours=1)
    for key, hours, applies in (("next_1_hours", 1, hourly), ("next_6_hours", 6, True), ("next_1_hours", 1, True)):
        if applies and key in data:
            return block_over(start, hours, data["instant"]["details"], data[key])
    return None


def block_over(start: datetime, hours: int, instant: dict[str, float], interval: dict[str, Any]) -> Block:
    details = interval.get("details", {})
    temperature = instant["air_temperature"]
    return Block(
        start=start,
        end=start + timedelta(hours=hours),
        temperature_low=min(temperature, details.get("air_temperature_min", temperature)),
        temperature_high=max(temperature, details.get("air_temperature_max", temperature)),
        symbol=interval.get("summary", {}).get("symbol_code"),
        precipitation_mm=details.get("precipitation_amount", 0.0),
        precipitation_probability=details.get("probability_of_precipitation"),
        wind_speed=instant.get("wind_speed", 0.0),
    )


def date_for(day: str, today: date) -> date:
    if day == TODAY:
        return today
    if day == TOMORROW:
        return today + timedelta(days=1)
    if day in WEEKDAYS:
        return today + timedelta(days=(WEEKDAYS.index(day) - today.weekday()) % 7)
    raise ForecastRequestError(f'day "{day}" is not one of today, tomorrow, a weekday name such as saturday, weekend, or week')


def dates_for(day: str, today: date) -> list[date]:
    """The week is today and the six days after it; the weekend is the coming Saturday and Sunday, or only today when today is Sunday."""
    if day == WEEK:
        return [today + timedelta(days=offset) for offset in range(DAYS_IN_WEEK_VIEW)]
    if today.weekday() == SUNDAY:
        return [today]
    saturday = today + timedelta(days=SATURDAY - today.weekday())
    return [saturday, saturday + timedelta(days=1)]


def part_of_day(part: str) -> str:
    normalized = part.strip().lower()
    if normalized in WHOLE_DAY_WORDS:
        return WHOLE_DAY
    if normalized in PARTS_OF_DAY:
        return normalized
    raise ForecastRequestError(f'part_of_day "{part}" is not one of morning, afternoon, evening, night, or all')


def local_hour(day: date, hour: int, zone: ZoneInfo) -> datetime:
    return datetime.combine(day + timedelta(days=hour // 24), time(hour % 24), tzinfo=zone)


def part_period(day: date, part: str, zone: ZoneInfo) -> Period:
    start_hour, end_hour = PARTS_OF_DAY[part]
    return Period(f"{part} ({CLOCK_WORDS[start_hour]} to {CLOCK_WORDS[end_hour]})", local_hour(day, start_hour, zone), local_hour(day, end_hour, zone))


def day_period(day: date, zone: ZoneInfo) -> Period:
    return Period(spoken_date(day), local_hour(day, 0, zone), local_hour(day, 24, zone))


def spoken_date(day: date) -> str:
    return f"{day:%A %B} {day.day}"


def condition_words(symbol: str) -> str:
    base = symbol.split("_", 1)[0]
    if base in SKY_WORDS:
        return SKY_WORDS[base]
    match = PRECIPITATION_SYMBOL.match(base)
    if match is None:
        return base
    intensity = "heavy " if match["intensity"] == "heavy" else "light " if match["intensity"] else ""
    return f"{intensity}{match['kind']}{' showers' if match['showers'] else ''}{' with thunder' if match['thunder'] else ''}"


def is_precipitation(symbol: str | None) -> bool:
    return symbol is not None and PRECIPITATION_SYMBOL.match(symbol.split("_", 1)[0]) is not None


def conditions_of(blocks: list[Block]) -> str:
    """The most common sky, plus the wettest precipitation if it differs: "cloudy with light rain at times"."""
    words = [condition_words(block.symbol) for block in blocks if block.symbol]
    if not words:
        return "conditions unknown"
    usual = Counter(words).most_common(1)[0][0]
    wet_blocks = [block for block in blocks if is_precipitation(block.symbol)]
    if not wet_blocks:
        return usual
    wettest = condition_words(max(wet_blocks, key=lambda block: block.precipitation_mm).symbol)
    return usual if wettest == usual else f"{usual} with {wettest} at times"


class ForecastReader:
    """Answers one weather_forecast call from one Met.no document, relative to the moment of the call."""

    def __init__(self, document: dict[str, Any], now: datetime, zone: ZoneInfo, units: str) -> None:
        self._blocks = blocks_from_document(document)
        self._now = now
        self._zone = zone
        self._units = UNIT_SYSTEMS[units]

    @property
    def today(self) -> date:
        return self._now.astimezone(self._zone).date()

    def describe(self, day: str, part: str) -> str:
        day = day.strip().lower()
        part = part_of_day(part)
        if day in (WEEK, WEEKEND):
            return self.describe_days(day, dates_for(day, self.today))
        return self.describe_day(date_for(day, self.today), part)

    def describe_days(self, day: str, dates: list[date]) -> str:
        header = f"Home weather forecast for {'this weekend' if day == WEEKEND else 'the next seven days'}, by day, local time:"
        return "\n".join([header, *(self.day_line(day_period(each, self._zone)) for each in dates)])

    def describe_day(self, day: date, part: str) -> str:
        periods = self.periods_of(day, part)
        if not periods:
            return f"The {part} of {spoken_date(day)} has already passed; there is no forecast for it."
        if not any(self.blocks_in(period) for period in periods):
            return f"No forecast for {spoken_date(day)} yet: it is {self.beyond_range_note()}."
        lines = [f"Home weather forecast for {self.day_name(day)}, local time:"]
        if day == self.today and part == WHOLE_DAY:
            lines.append(self.now_line())
        lines.extend(self.period_line(period) for period in periods)
        return "\n".join(lines)

    def periods_of(self, day: date, part: str) -> list[Period]:
        """The periods of a day that have not ended yet. Today also includes the night that began yesterday, so "tonight" asked at 2 am means now."""
        named = [(name, part_period(day, name, self._zone)) for name in PARTS_OF_DAY]
        if day == self.today:
            overnight = part_period(day - timedelta(days=1), "night", self._zone)
            named.insert(0, ("night", Period(f"overnight ({CLOCK_WORDS[24]} to {CLOCK_WORDS[30]})", overnight.start, overnight.end)))
        upcoming = [(name, period) for name, period in named if period.end > self._now]
        if part == WHOLE_DAY:
            return [period for _, period in upcoming]
        return [period for name, period in upcoming if name == part][:1]

    def day_name(self, day: date) -> str:
        relative = {self.today: "today, ", self.today + timedelta(days=1): "tomorrow, "}.get(day, "")
        return f"{relative}{spoken_date(day)}"

    def blocks_in(self, period: Period) -> list[Block]:
        return [block for block in self._blocks if period.start <= block.midpoint < period.end and block.end > self._now]

    def now_line(self) -> str:
        current = next((block for block in self._blocks if block.end > self._now), None)
        if current is None:
            return "now: no current conditions in the forecast"
        return f"now: {self.temperature(current.temperature_low)}, {conditions_of([current])}, wind {self.wind(current.wind_speed)}"

    def period_line(self, period: Period) -> str:
        blocks = self.blocks_in(period)
        if not blocks:
            return f"{period.label}: {self.beyond_range_note()}"
        wind = self.wind(max(block.wind_speed for block in blocks))
        return f"{period.label}: {self.temperature_range(blocks)}, {conditions_of(blocks)}, {self.precipitation(blocks)}, wind up to {wind}"

    def day_line(self, period: Period) -> str:
        blocks = self.blocks_in(period)
        label = f"{period.label} (rest of today)" if period.start.date() == self.today else period.label
        if not blocks:
            return f"{label}: {self.beyond_range_note()}"
        return f"{label}: {self.temperature_range(blocks)}, {conditions_of(blocks)}, {self.precipitation(blocks)}"

    def beyond_range_note(self) -> str:
        last_day = self._blocks[-1].midpoint.astimezone(self._zone).date() if self._blocks else self.today
        return f"beyond the forecast, which reaches only to {spoken_date(last_day)}"

    def temperature(self, celsius: float) -> str:
        return f"{round(self._units.from_celsius(celsius))}{self._units.temperature_symbol}"

    def temperature_range(self, blocks: list[Block]) -> str:
        low = round(self._units.from_celsius(min(block.temperature_low for block in blocks)))
        high = round(self._units.from_celsius(max(block.temperature_high for block in blocks)))
        return f"{low}{self._units.temperature_symbol}" if low == high else f"{low} to {high}{self._units.temperature_symbol}"

    def precipitation(self, blocks: list[Block]) -> str:
        """Total precipitation over the period, and the highest chance of any when Met.no provides one (only in the Nordic area)."""
        total = sum(block.precipitation_mm for block in blocks)
        amount = round(self._units.from_millimetres(total), self._units.precipitation_decimals)
        words = "dry" if total == 0 else "a trace of precipitation" if amount == 0 else f"{amount:g} {self._units.precipitation_unit} of precipitation"
        chances = [block.precipitation_probability for block in blocks if block.precipitation_probability is not None]
        return f"{words}, {round(max(chances))}% chance of precipitation" if chances else words

    def wind(self, metres_per_second: float) -> str:
        return f"{round(self._units.from_metres_per_second(metres_per_second))} {self._units.wind_unit}"
