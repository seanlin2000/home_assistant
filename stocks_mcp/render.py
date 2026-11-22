"""The text the model speaks from (design doc v2/16 section 3.5): the company and ticker first, so a wrong match is heard, then the as-of time, then
one line per number, rounded for speech. A number Finnhub did not return is left out, never written as "n/a". The market view gives each fund's own
price, labelled as the fund's, never converted to an index level (section 3.4)."""

from dataclasses import dataclass
from datetime import date, datetime

from stocks_mcp.companies import Company, Fund
from stocks_mcp.finnhub_client import Metrics, Quote
from stocks_mcp.market_hours import NEW_YORK, as_of_phrase, market_in_session
from utils.text_utils import spoken_month_day

CENTS_BELOW_DOLLARS = 100.0  # "$11.37", not "$11" beside a 52-week low of "$11"; from $100 up, whole dollars
# A 52-week range that misses the price by this factor belongs to another listing: Finnhub gives BRK.B the A shares' range, and Toyota's
# US shares its Tokyo range in yen.
RANGE_MISMATCH_FACTOR = 2.0
MARKET_HEADER = "The market {as_of}, from the funds that track each index. These are fund prices, not index levels:"


@dataclass(frozen=True)
class StockAnswer:
    company: Company
    quote: Quote
    metrics: Metrics
    now: datetime
    fresh_trade_minutes: float


@dataclass(frozen=True)
class FundQuote:
    fund: Fund
    quote: Quote | None  # None when Finnhub had no quote for the fund


def stock_text(answer: StockAnswer) -> str:
    quote, metrics = answer.quote, answer.metrics
    lines = [
        f"{named(answer.company)}, {as_of_phrase(quote.traded_at, answer.now, answer.fresh_trade_minutes)}",
        f"Price: {spoken_price(quote.price)}, {spoken_change(quote.change, quote.change_percent)} on the day",
    ]
    lines.extend(pe_lines(metrics.pe_ratio))
    lines.extend(range_lines(metrics, quote.price, answer.now.astimezone(NEW_YORK).date()))
    lines.extend(return_lines(metrics.period_returns, market_in_session(answer.now)))
    return "\n".join(lines)


def market_text(fund_quotes: list[FundQuote], now: datetime, fresh_trade_minutes: float) -> str:
    quoted = [fund_quote for fund_quote in fund_quotes if fund_quote.quote is not None]
    as_of = as_of_phrase(max(fund_quote.quote.traded_at for fund_quote in quoted), now, fresh_trade_minutes)
    lines = [MARKET_HEADER.format(as_of=as_of)]
    lines.extend(f"{item.fund.symbol}, {item.fund.described}: {spoken_price(item.quote.price)}, {spoken_percent_change(item.quote.change_percent)} on the day" for item in quoted)
    return "\n".join(lines)


def named(company: Company) -> str:
    """ "Apple (AAPL)", or "IBM" alone when the name is the ticker."""
    return company.symbol if company.name == company.symbol else f"{company.name} ({company.symbol})"


def pe_lines(pe_ratio: float | None) -> list[str]:
    if pe_ratio is None:
        return []
    if pe_ratio <= 0:
        return ["P/E ratio: none, because the company lost money over the last twelve months"]
    return [f"P/E ratio: {pe_ratio:.1f}"]


def range_lines(metrics: Metrics, price: float, today: date) -> list[str]:
    if metrics.year_low is None or metrics.year_high is None or not range_fits_price(metrics.year_low, metrics.year_high, price):
        return []
    return [f"52-week range: {spoken_price(metrics.year_low)}{spoken_on(metrics.year_low_date, today)} to {spoken_price(metrics.year_high)}{spoken_on(metrics.year_high_date, today)}"]


def range_fits_price(year_low: float, year_high: float, price: float) -> bool:
    return year_low / RANGE_MISMATCH_FACTOR <= price <= year_high * RANGE_MISMATCH_FACTOR


def spoken_on(day: date | None, today: date) -> str:
    return f" ({spoken_month_day(day, today)})" if day else ""


def return_lines(period_returns: tuple[tuple[str, float], ...], market_trading: bool) -> list[str]:
    """While the market trades, Finnhub's returns still end at the last close (they are computed from daily closes), so the line says so."""
    if not period_returns:
        return []
    label = "Change through the last close" if market_trading else "Change"
    return [f"{label}: " + "; ".join(f"{period} {spoken_percent_change(percent)}" for period, percent in period_returns)]


def spoken_price(dollars: float) -> str:
    return f"${dollars:,.2f}" if dollars < CENTS_BELOW_DOLLARS else f"${dollars:,.0f}"


def spoken_change(dollars: float, percent: float) -> str:
    if round(dollars, 2) == 0:
        return "unchanged"
    return f"{'up' if dollars > 0 else 'down'} ${abs(dollars):,.2f} ({abs(percent):.1f} percent)"


def spoken_percent_change(percent: float) -> str:
    if round(percent, 1) == 0:
        return "unchanged"
    return f"{'up' if percent > 0 else 'down'} {abs(percent):.1f} percent"
