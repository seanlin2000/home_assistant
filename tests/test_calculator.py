"""The calculator must be exact on the benchmark's arithmetic, reject unsafe input, and speak sensible sentences."""

from datetime import date

import pytest

from calculator_mcp import functions
from calculator_mcp.functions import CalculatorError, break_even, calculate, convert, date_math, energy_cost, growth_schedule, loan_payment, percent


def test_calculate_handles_the_lease_question() -> None:
    assert calculate("3500 * 1.05 * 12").number == pytest.approx(44100)
    assert calculate("3500*1.03*12 + 3500*1.03**2*12").number == pytest.approx(87817.80)
    assert calculate("$3,500 * 1.05").number == pytest.approx(3675)
    assert "44,100" in calculate("3500 * 1.05 * 12").render()


def test_calculate_supports_percent_literals_and_functions() -> None:
    assert calculate("15% * 84").number == pytest.approx(12.6)
    assert calculate("round(sqrt(2), 3)").number == pytest.approx(1.414)
    assert calculate("2^10").number == 1024


@pytest.mark.parametrize("bad", ["__import__('os')", "a.b", "1 if 2 else 3", "2 ** 5000", "1 / 0", "[1,2]", "open('x')"])
def test_calculate_rejects_anything_outside_the_whitelist(bad: str) -> None:
    with pytest.raises(CalculatorError):
        calculate(bad)


def test_percent_kinds() -> None:
    assert percent("of", 15, 84).number == pytest.approx(12.6)
    assert percent("is_what_percent", 84, 120).number == pytest.approx(70)
    assert percent("change", 3500, 3675).number == pytest.approx(5)
    assert percent("increase_by", 5, 3500).number == pytest.approx(3675)
    assert percent("decrease_by", 10, 200).number == pytest.approx(180)
    with pytest.raises(CalculatorError):
        percent("of_course", 1, 2)


def test_convert_units_and_temperature() -> None:
    assert convert(26, "c", "f").number == pytest.approx(78.8)
    assert convert(10, "miles", "km").number == pytest.approx(16.09344)
    assert convert(500, "square feet", "m2").number == pytest.approx(46.45, abs=0.01)
    assert convert(1.45, "kwh", "wh").number == pytest.approx(1450)
    with pytest.raises(CalculatorError):
        convert(1, "kg", "km")
    with pytest.raises(CalculatorError):
        convert(1, "parsecs", "km")


def test_growth_schedule_matches_the_reference_answer() -> None:
    result = growth_schedule(start=3500, rate_percent=3, periods=2, per_period_multiplier=12)
    assert result.number == pytest.approx(87817.80)
    assert result.details["final_amount"] == "3,713.15"
    assert "period 1: 3,605 each, 43,260 for the period" in result.details["schedule"]


def test_energy_cost_matches_the_reference_answer() -> None:
    result = energy_cost(watts=300, hours_per_day=1, price_per_kwh=0.30, days=30, idle_watts=50)
    assert result.details["daily_kwh"] == "1.45"
    assert result.number == pytest.approx(13.05)


def test_loan_and_break_even() -> None:
    payment = loan_payment(principal=400000, annual_rate_percent=6, years=30)
    assert payment.number == pytest.approx(2398.20, abs=0.01)
    assert break_even(monthly_saving=150, upfront_cost=4500).number == pytest.approx(30)
    with pytest.raises(CalculatorError):
        break_even(monthly_saving=0, upfront_cost=100)


def test_date_math_with_a_fixed_today() -> None:
    today = date(2026, 9, 6)
    assert date_math("days_between", "2026-09-06", "2026-09-22", today=today).number == 16
    assert date_math("weeks_until", "September 22", today=today).number == pytest.approx(16 / 7)
    assert date_math("weekday", "2026-09-22", today=today).details["weekday"] == "Tuesday"
    assert date_math("add_days", "today", days=8, today=today).details["date"] == "2026-09-14"
    with pytest.raises(CalculatorError):
        date_math("days_between", "someday", today=today)


def test_render_shows_exact_number_and_spoken_sentence() -> None:
    text = functions.percent("change", 3500, 3675).render()
    assert text.startswith("result: 5")
    assert "spoken: from 3,500 to 3,675 is a 5 percent increase" in text
