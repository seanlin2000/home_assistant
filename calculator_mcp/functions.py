"""The calculator functions, pure and synchronous. Each returns a Result with the exact number(s) and a short sentence the model can say aloud.

Design rules (design_docs/v1/03, calculator section): round only in the spoken sentence, never in the number; reject anything outside the
whitelist with a message the model can act on; keep every function small enough that a 4B model can fill its arguments from a spoken question.
"""

import ast
import math
import operator
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable

MAX_EXPONENT = 1000
MAX_ABS_VALUE = 1e30


class CalculatorError(ValueError):
    """Bad input that the model should correct, described in plain words."""


@dataclass
class Result:
    number: float | int | None
    spoken: str
    details: dict[str, Any] = field(default_factory=dict)

    def render(self) -> str:
        lines = [] if self.number is None else [f"result: {format_number(self.number)}"]
        lines.append(f"spoken: {self.spoken}")
        lines.extend(f"{key}: {value}" for key, value in self.details.items())
        return "\n".join(lines)


def format_number(value: float | int) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int) or float(value).is_integer():
        return f"{int(round(value)):,}"
    return f"{value:,.2f}" if abs(value) >= 0.01 else f"{value:.4g}"


# ---------------------------------------------------------------- calculate

_BINARY: dict[type, Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY: dict[type, Callable[[float], float]] = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCTIONS: dict[str, Callable[..., float]] = {
    "round": round,
    "sqrt": math.sqrt,
    "abs": abs,
    "min": min,
    "max": max,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "floor": math.floor,
    "ceil": math.ceil,
}
_NAMES: dict[str, float] = {"pi": math.pi, "e": math.e}
_PERCENT_LITERAL = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_THOUSANDS_COMMA = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")


def calculate(expression: str) -> Result:
    """Evaluate arithmetic: + - * / // % ** parentheses, percent literals like 15%, and round, sqrt, abs, min, max, log, exp, floor, ceil."""
    cleaned = normalize_expression(expression)
    try:
        tree = ast.parse(cleaned, mode="eval")
    except SyntaxError as error:
        raise CalculatorError(f"could not parse '{expression}': {error.msg}") from error
    value = _evaluate(tree.body)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise CalculatorError("the result is not a finite number (division by zero or overflow)")
    return Result(number=value, spoken=f"{expression.strip()} equals {format_number(value)}")


def normalize_expression(expression: str) -> str:
    text = _THOUSANDS_COMMA.sub("", expression).replace("×", "*").replace("÷", "/").replace("^", "**").replace("$", "").strip()
    return _PERCENT_LITERAL.sub(r"(\1/100)", text)


def _evaluate(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name) and node.id in _NAMES:
        return _NAMES[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_evaluate(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise CalculatorError(f"exponent {right} is too large")
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
            raise CalculatorError("division by zero")
        value = _BINARY[type(node.op)](left, right)
        if abs(value) > MAX_ABS_VALUE:
            raise CalculatorError("the result is too large to be meaningful")
        return value
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS and not node.keywords:
        return _FUNCTIONS[node.func.id](*(_evaluate(argument) for argument in node.args))
    raise CalculatorError(f"unsupported syntax near '{ast.dump(node)[:40]}'; use numbers, + - * / ** ( ), and round/sqrt/abs/min/max")


# ---------------------------------------------------------------- percent

PERCENT_KINDS = ("of", "is_what_percent", "change", "increase_by", "decrease_by")


def percent(kind: str, a: float, b: float) -> Result:
    """Percent arithmetic. of: a% of b. is_what_percent: a is what percent of b. change: percent change from a to b. increase_by / decrease_by: b changed by a percent."""
    if kind == "of":
        value = a / 100 * b
        return Result(value, f"{format_number(a)} percent of {format_number(b)} is {format_number(value)}")
    if kind == "is_what_percent":
        _nonzero(b, "the base")
        value = a / b * 100
        return Result(value, f"{format_number(a)} is {format_number(value)} percent of {format_number(b)}")
    if kind == "change":
        _nonzero(a, "the starting value")
        value = (b - a) / a * 100
        direction = "increase" if value >= 0 else "decrease"
        return Result(value, f"from {format_number(a)} to {format_number(b)} is a {format_number(abs(value))} percent {direction}")
    if kind == "increase_by":
        value = b * (1 + a / 100)
        return Result(value, f"{format_number(b)} increased by {format_number(a)} percent is {format_number(value)}")
    if kind == "decrease_by":
        value = b * (1 - a / 100)
        return Result(value, f"{format_number(b)} decreased by {format_number(a)} percent is {format_number(value)}")
    raise CalculatorError(f"kind must be one of {', '.join(PERCENT_KINDS)}")


def _nonzero(value: float, label: str) -> None:
    if value == 0:
        raise CalculatorError(f"{label} cannot be zero")


# ---------------------------------------------------------------- convert

# Factors to a base unit per dimension. Temperature is handled separately because it is affine, not proportional.
_UNITS: dict[str, dict[str, float]] = {
    "length": {"m": 1, "km": 1000, "cm": 0.01, "mm": 0.001, "mi": 1609.344, "ft": 0.3048, "in": 0.0254, "yd": 0.9144},
    "mass": {"kg": 1, "g": 0.001, "lb": 0.45359237, "oz": 0.028349523125, "st": 6.35029318},
    "volume": {"l": 1, "ml": 0.001, "cup": 0.2365882365, "tbsp": 0.01478676478125, "tsp": 0.00492892159375, "gal": 3.785411784, "qt": 0.946352946, "pt": 0.473176473, "floz": 0.0295735295625},
    "area": {"m2": 1, "km2": 1e6, "cm2": 1e-4, "ft2": 0.09290304, "mi2": 2589988.110336, "acre": 4046.8564224, "ha": 10000},
    "energy": {"wh": 1, "kwh": 1000, "mwh": 1e6, "j": 1 / 3600, "kj": 1000 / 3600, "cal": 4.184 / 3600, "kcal": 4184 / 3600, "btu": 1055.05585 / 3600},
    "power": {"w": 1, "kw": 1000, "mw": 1e6, "hp": 745.69987},
    "speed": {"ms": 1, "kmh": 1000 / 3600, "mph": 1609.344 / 3600, "kn": 1852 / 3600},
    "time": {"s": 1, "min": 60, "h": 3600, "day": 86400, "week": 604800},
    "data": {"b": 1, "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12, "kib": 1024, "mib": 1024**2, "gib": 1024**3, "tib": 1024**4},
}
_ALIASES: dict[str, str] = {
    "meter": "m",
    "meters": "m",
    "metre": "m",
    "metres": "m",
    "kilometer": "km",
    "kilometers": "km",
    "kilometre": "km",
    "kilometres": "km",
    "centimeter": "cm",
    "centimeters": "cm",
    "millimeter": "mm",
    "millimeters": "mm",
    "mile": "mi",
    "miles": "mi",
    "foot": "ft",
    "feet": "ft",
    "inch": "in",
    "inches": "in",
    "yard": "yd",
    "yards": "yd",
    "kilogram": "kg",
    "kilograms": "kg",
    "gram": "g",
    "grams": "g",
    "pound": "lb",
    "pounds": "lb",
    "lbs": "lb",
    "ounce": "oz",
    "ounces": "oz",
    "stone": "st",
    "liter": "l",
    "liters": "l",
    "litre": "l",
    "litres": "l",
    "milliliter": "ml",
    "milliliters": "ml",
    "cups": "cup",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "gallon": "gal",
    "gallons": "gal",
    "quart": "qt",
    "quarts": "qt",
    "pint": "pt",
    "pints": "pt",
    "fl oz": "floz",
    "fluid ounce": "floz",
    "fluid ounces": "floz",
    "sqm": "m2",
    "square meter": "m2",
    "square meters": "m2",
    "sqft": "ft2",
    "square foot": "ft2",
    "square feet": "ft2",
    "square mile": "mi2",
    "square miles": "mi2",
    "square kilometer": "km2",
    "square kilometers": "km2",
    "acres": "acre",
    "hectare": "ha",
    "hectares": "ha",
    "watt hour": "wh",
    "watt hours": "wh",
    "kilowatt hour": "kwh",
    "kilowatt hours": "kwh",
    "joule": "j",
    "joules": "j",
    "calorie": "cal",
    "calories": "cal",
    "kilocalorie": "kcal",
    "kilocalories": "kcal",
    "watt": "w",
    "watts": "w",
    "kilowatt": "kw",
    "kilowatts": "kw",
    "horsepower": "hp",
    "m/s": "ms",
    "km/h": "kmh",
    "kph": "kmh",
    "mi/h": "mph",
    "knot": "kn",
    "knots": "kn",
    "sec": "s",
    "second": "s",
    "seconds": "s",
    "minute": "min",
    "minutes": "min",
    "hour": "h",
    "hours": "h",
    "hr": "h",
    "days": "day",
    "weeks": "week",
    "byte": "b",
    "bytes": "b",
    "kilobyte": "kb",
    "megabyte": "mb",
    "gigabyte": "gb",
    "terabyte": "tb",
    "c": "c",
    "celsius": "c",
    "°c": "c",
    "f": "f",
    "fahrenheit": "f",
    "°f": "f",
    "k": "k",
    "kelvin": "k",
}


def convert(value: float, from_unit: str, to_unit: str) -> Result:
    """Convert between units of length, mass, volume, area, energy, power, speed, time, data, and temperature (c, f, k)."""
    source, target = _unit(from_unit), _unit(to_unit)
    if source in ("c", "f", "k") or target in ("c", "f", "k"):
        converted = _temperature(value, source, target)
        return Result(converted, f"{format_number(value)} degrees {from_unit} is {format_number(round(converted, 1))} degrees {to_unit}")
    dimension = next((name for name, table in _UNITS.items() if source in table and target in table), None)
    if dimension is None:
        raise CalculatorError(f"cannot convert {from_unit} to {to_unit}: not the same kind of quantity, or unknown unit")
    converted = value * _UNITS[dimension][source] / _UNITS[dimension][target]
    return Result(converted, f"{format_number(value)} {from_unit} is {format_number(round(converted, 2))} {to_unit}")


def _unit(text: str) -> str:
    key = text.strip().lower().replace("²", "2")
    key = _ALIASES.get(key, key)
    known = {unit for table in _UNITS.values() for unit in table} | {"c", "f", "k"}
    if key not in known:
        raise CalculatorError(f"unknown unit '{text}'")
    return key


def _temperature(value: float, source: str, target: str) -> float:
    if source not in ("c", "f", "k") or target not in ("c", "f", "k"):
        raise CalculatorError("temperature can only be converted between c, f, and k")
    celsius = {"c": value, "f": (value - 32) * 5 / 9, "k": value - 273.15}[source]
    return {"c": celsius, "f": celsius * 9 / 5 + 32, "k": celsius + 273.15}[target]


# ---------------------------------------------------------------- growth schedule


def growth_schedule(start: float, rate_percent: float, periods: int, per_period_multiplier: float = 1) -> Result:
    """Compound growth period by period. start grows by rate_percent each period; per_period_multiplier turns a monthly figure into a yearly total (12)."""
    if periods < 1 or periods > 600:
        raise CalculatorError("periods must be between 1 and 600")
    rows = []
    amount = start
    running = 0.0
    for period in range(1, periods + 1):
        amount = amount * (1 + rate_percent / 100)
        total = amount * per_period_multiplier
        running += total
        rows.append(f"period {period}: {format_number(amount)} each, {format_number(total)} for the period, {format_number(running)} cumulative")
    spoken = f"starting from {format_number(start)} and growing {format_number(rate_percent)} percent per period, after {periods} periods the figure is {format_number(amount)} and the cumulative total is {format_number(running)}"
    return Result(running, spoken, {"schedule": "\n" + "\n".join(rows), "final_amount": format_number(amount)})


# ---------------------------------------------------------------- energy cost


def energy_cost(watts: float, hours_per_day: float, price_per_kwh: float, days: int = 30, idle_watts: float = 0) -> Result:
    """Electricity cost: watts for hours_per_day each day, optionally idle_watts for the remaining hours, at price_per_kwh, over days."""
    if not 0 <= hours_per_day <= 24:
        raise CalculatorError("hours_per_day must be between 0 and 24")
    active_kwh = watts * hours_per_day / 1000
    idle_kwh = idle_watts * (24 - hours_per_day) / 1000
    daily_kwh = active_kwh + idle_kwh
    cost = daily_kwh * days * price_per_kwh
    spoken = f"about {format_number(round(daily_kwh, 2))} kilowatt hours a day, {format_number(round(daily_kwh * days, 1))} over {days} days, costing about {format_number(round(cost, 2))} at {format_number(price_per_kwh)} per kilowatt hour"
    return Result(cost, spoken, {"daily_kwh": format_number(round(daily_kwh, 3)), "active_share": f"{active_kwh / daily_kwh:.0%}" if daily_kwh else "n/a"})


# ---------------------------------------------------------------- loans


def loan_payment(principal: float, annual_rate_percent: float, years: float) -> Result:
    """Fixed-rate amortizing loan: monthly payment and total interest."""
    months = int(round(years * 12))
    if months < 1 or principal <= 0:
        raise CalculatorError("principal must be positive and the term at least one month")
    monthly_rate = annual_rate_percent / 100 / 12
    payment = principal / months if monthly_rate == 0 else principal * monthly_rate / (1 - (1 + monthly_rate) ** -months)
    total_interest = payment * months - principal
    spoken = f"{format_number(principal)} at {format_number(annual_rate_percent)} percent over {format_number(years)} years is about {format_number(round(payment, 2))} a month, {format_number(round(total_interest))} in total interest"
    return Result(payment, spoken, {"total_interest": format_number(round(total_interest, 2)), "months": months})


def break_even(monthly_saving: float, upfront_cost: float) -> Result:
    """Months until a one-time cost is recovered by a monthly saving."""
    if monthly_saving <= 0:
        raise CalculatorError("monthly_saving must be positive; with no saving there is no break-even")
    months = upfront_cost / monthly_saving
    years = months / 12
    spoken = f"{format_number(upfront_cost)} up front against {format_number(monthly_saving)} a month breaks even after about {format_number(round(months, 1))} months, roughly {format_number(round(years, 1))} years"
    return Result(months, spoken, {"years": format_number(round(years, 2))})


# ---------------------------------------------------------------- dates

DATE_KINDS = ("days_between", "add_days", "weekday", "weeks_until")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def date_math(kind: str, date_text: str = "today", other_date_text: str = "today", days: int = 0, today: date | None = None) -> Result:
    """Date arithmetic. days_between: from date to other_date. add_days: date plus days. weekday: which weekday date falls on. weeks_until: from today to date."""
    today = today or date.today()
    first = _parse_date(date_text, today)
    if kind == "days_between":
        second = _parse_date(other_date_text, today)
        delta = (second - first).days
        return Result(delta, f"there are {format_number(abs(delta))} days between {first.isoformat()} and {second.isoformat()}")
    if kind == "add_days":
        target = first + timedelta(days=days)
        return Result(None, f"{format_number(days)} days from {first.isoformat()} is {WEEKDAYS[target.weekday()]} {target.isoformat()}", {"date": target.isoformat()})
    if kind == "weekday":
        return Result(None, f"{first.isoformat()} is a {WEEKDAYS[first.weekday()]}", {"weekday": WEEKDAYS[first.weekday()]})
    if kind == "weeks_until":
        delta = (first - today).days
        return Result(delta / 7, f"{first.isoformat()} is {format_number(abs(delta))} days away, about {format_number(round(abs(delta) / 7, 1))} weeks", {"days": delta})
    raise CalculatorError(f"kind must be one of {', '.join(DATE_KINDS)}")


def _parse_date(text: str, today: date) -> date:
    cleaned = text.strip().lower()
    if cleaned in ("", "today"):
        return today
    if cleaned == "tomorrow":
        return today + timedelta(days=1)
    if cleaned == "yesterday":
        return today - timedelta(days=1)
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%B %d %Y", "%b %d %Y", "%d %B %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text.strip(), pattern).date()
        except ValueError:
            continue
    for pattern in ("%B %d", "%b %d", "%d %B", "%m/%d"):
        try:
            parsed = datetime.strptime(text.strip(), pattern).date().replace(year=today.year)
            return parsed if parsed >= today else parsed.replace(year=today.year + 1)
        except ValueError:
            continue
    raise CalculatorError(f"could not read the date '{text}'; use YYYY-MM-DD or a form like 'September 22'")
