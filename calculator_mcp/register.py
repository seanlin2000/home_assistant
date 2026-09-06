"""Expose the calculator functions as MCP tools on an existing server, alongside web search, so the agent sees one tool list."""

from mcp.server.mcpserver import MCPServer

from calculator_mcp import functions
from calculator_mcp.functions import CalculatorError, Result

CALCULATOR_TOOL_NAMES = ("calculate", "percent", "convert", "growth_schedule", "energy_cost", "loan_payment", "break_even", "date_math")


def rendered(function, *args, **kwargs) -> str:
    try:
        result: Result = function(*args, **kwargs)
    except CalculatorError as error:
        return f"Calculator error: {error}"
    except (TypeError, ValueError, OverflowError) as error:
        return f"Calculator error: {error}"
    return result.render()


def register_calculator_tools(server: MCPServer) -> None:
    @server.tool()
    def calculate(expression: str) -> str:
        """Do arithmetic exactly. Use this for any calculation with more than one step and always for money. Supports + - * / ** ( ), percent literals like 15%, and round, sqrt, abs, min, max. Example: "3500 * 1.05 * 12"."""
        return rendered(functions.calculate, expression)

    @server.tool()
    def percent(kind: str, a: float, b: float) -> str:
        """Percent questions. kind "of": a percent of b. "is_what_percent": a is what percent of b. "change": percent change from a to b. "increase_by" or "decrease_by": b changed by a percent."""
        return rendered(functions.percent, kind, a, b)

    @server.tool()
    def convert(value: float, from_unit: str, to_unit: str) -> str:
        """Convert units: length (km, mi, m, ft, in), mass (kg, lb, oz), volume (l, ml, cup, tbsp, gal), area (m2, ft2, acre), energy (wh, kwh), power (w, kw), speed (kmh, mph), time, data (gb, gib), temperature (c, f, k)."""
        return rendered(functions.convert, value, from_unit, to_unit)

    @server.tool()
    def growth_schedule(start: float, rate_percent: float, periods: int, per_period_multiplier: float = 1) -> str:
        """Compound growth laid out period by period, e.g. rent rising 3 percent a year for 2 years: start=3500, rate_percent=3, periods=2, per_period_multiplier=12 gives each year's monthly figure, yearly total, and the cumulative total."""
        return rendered(functions.growth_schedule, start, rate_percent, periods, per_period_multiplier)

    @server.tool()
    def energy_cost(watts: float, hours_per_day: float, price_per_kwh: float, days: int = 30, idle_watts: float = 0) -> str:
        """Electricity cost of a device: watts while active for hours_per_day, optionally idle_watts for the rest of the day, at price_per_kwh (state your assumed price), over days."""
        return rendered(functions.energy_cost, watts, hours_per_day, price_per_kwh, days, idle_watts)

    @server.tool()
    def loan_payment(principal: float, annual_rate_percent: float, years: float) -> str:
        """Monthly payment and total interest of a fixed-rate loan or mortgage."""
        return rendered(functions.loan_payment, principal, annual_rate_percent, years)

    @server.tool()
    def break_even(monthly_saving: float, upfront_cost: float) -> str:
        """Months until an upfront cost (for example refinancing closing costs) is recovered by a monthly saving."""
        return rendered(functions.break_even, monthly_saving, upfront_cost)

    @server.tool()
    def date_math(kind: str, date: str = "today", other_date: str = "today", days: int = 0) -> str:
        """Date arithmetic. kind "days_between" (date to other_date), "add_days" (date plus days), "weekday" (what day date falls on), "weeks_until" (today to date). Dates as YYYY-MM-DD or like "September 22"."""
        return rendered(functions.date_math, kind, date, other_date, days)
