"""Expose the calculator functions as MCP tools on an existing server, alongside web search, so the agent sees one tool list."""

from collections.abc import Callable
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from calculator_mcp import functions
from calculator_mcp.functions import CalculatorError, Result

CALCULATOR_TOOL_NAMES = ("calculate", "percent", "convert", "growth_schedule", "energy_cost", "loan_payment", "break_even", "date_math")


def rendered(function: Callable[..., Result], *args: object, **kwargs: object) -> str:
    try:
        result: Result = function(*args, **kwargs)
    except CalculatorError as error:
        return f"Calculator error: {error}"
    except (TypeError, ValueError, OverflowError) as error:
        return f"Calculator error: {error}"
    return result.render()


def register_calculator_tools(server: MCPServer) -> None:
    @server.tool()
    def calculate(expression: Annotated[str, Field(description='e.g. "3500 * 1.05 * 12"; + - * / ** ( ), 15%, round, sqrt, abs, min, max')]) -> str:
        """Do arithmetic exactly. Use it for any calculation with more than one step, and always for money."""
        return rendered(functions.calculate, expression)

    @server.tool()
    def percent(
        kind: Annotated[
            Literal["of", "is_what_percent", "change", "increase_by", "decrease_by"],
            Field(description="of: a% of b; is_what_percent: a as a % of b; change: % change from a to b; increase_by, decrease_by: b changed by a%"),
        ],
        a: Annotated[float, Field(description="first number")],
        b: Annotated[float, Field(description="second number")],
    ) -> str:
        """Answer a percent question exactly."""
        return rendered(functions.percent, kind, a, b)

    @server.tool()
    def convert(
        value: Annotated[float, Field(description="amount to convert")],
        from_unit: Annotated[str, Field(description="e.g. km mi m ft in kg lb oz l ml cup tbsp gal m2 ft2 acre wh kwh w kw kmh mph s min h day week gb gib c f k")],
        to_unit: Annotated[str, Field(description="unit of the same kind")],
    ) -> str:
        """Convert a value from one unit to another."""
        return rendered(functions.convert, value, from_unit, to_unit)

    @server.tool()
    def growth_schedule(
        start: Annotated[float, Field(description="starting value")],
        rate_percent: Annotated[float, Field(description="growth per period, in percent")],
        periods: Annotated[int, Field(description="number of periods")],
        per_period_multiplier: Annotated[float, Field(description="repeats per period, e.g. 12 months a year")] = 1,
    ) -> str:
        """Compound growth period by period, with running totals. Rent of 3500 a month rising 3% a year for 2 years: start=3500, rate_percent=3, periods=2, per_period_multiplier=12."""
        return rendered(functions.growth_schedule, start, rate_percent, periods, per_period_multiplier)

    @server.tool()
    def energy_cost(
        watts: Annotated[float, Field(description="watts while on")],
        hours_per_day: Annotated[float, Field(description="hours on per day")],
        price_per_kwh: Annotated[float, Field(description="price per kWh")],
        days: Annotated[int, Field(description="number of days")] = 30,
        idle_watts: Annotated[float, Field(description="watts the rest of the day")] = 0,
    ) -> str:
        """Electricity cost of running a device. Say the price per kWh you assumed."""
        return rendered(functions.energy_cost, watts, hours_per_day, price_per_kwh, days, idle_watts)

    @server.tool()
    def loan_payment(
        principal: Annotated[float, Field(description="amount borrowed")],
        annual_rate_percent: Annotated[float, Field(description="yearly rate in percent")],
        years: Annotated[float, Field(description="term in years")],
    ) -> str:
        """Monthly payment and total interest of a fixed-rate loan or mortgage."""
        return rendered(functions.loan_payment, principal, annual_rate_percent, years)

    @server.tool()
    def break_even(
        monthly_saving: Annotated[float, Field(description="saved per month")],
        upfront_cost: Annotated[float, Field(description="one-time cost")],
    ) -> str:
        """Months until an upfront cost, such as refinancing closing costs, is paid back by a monthly saving."""
        return rendered(functions.break_even, monthly_saving, upfront_cost)

    @server.tool()
    def date_math(
        kind: Annotated[
            Literal["days_between", "add_days", "weekday", "weeks_until"],
            Field(description="days_between: date to other_date; add_days: date plus days; weekday: weekday of date; weeks_until: today to date"),
        ],
        date: Annotated[str, Field(description='YYYY-MM-DD or like "September 22"')] = "today",
        other_date: Annotated[str, Field(description="second date, for days_between")] = "today",
        days: Annotated[int, Field(description="days to add, for add_days")] = 0,
    ) -> str:
        """Date arithmetic: days between dates, a date plus days, a date's weekday, or weeks until a date."""
        return rendered(functions.date_math, kind, date, other_date, days)
