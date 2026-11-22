"""Reads quotes, company metrics, and symbol searches from Finnhub's REST API (design doc v2/16 section 3.1).

Every reply is held in memory: a quote for quote_cache_seconds while the market trades and until the next opening bell when it does not, metrics for
metric_cache_seconds, searches for search_cache_seconds. With fixtures_dir set, recorded replies are read instead, and a reply that was not recorded
reads as Finnhub's own reply for an unknown symbol, so the benchmark never needs the key.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from stocks_mcp.market_hours import market_in_session, next_opening
from stocks_mcp.settings import StocksSettings
from utils.keychain_utils import keychain_item_stored, keychain_secret

KEYCHAIN_SERVICE = "studio-assistant"
KEYCHAIN_ACCOUNT = "finnhub-api"
TOO_MANY_REQUESTS = 429
# Shares and funds traded in the US: foreign companies such as Toyota and TSMC trade as ADRs, ASML as New York registry shares.
LISTING_TYPES = frozenset({"Common Stock", "ETP", "ADR", "NY Reg Shrs"})
# Finnhub's metric names for each period, in the order an answer says them. Finnhub has no trailing one-month return, only month to date.
PERIOD_RETURN_FIELDS = (
    ("5DayPriceReturnDaily", "past week"),
    ("monthToDatePriceReturnDaily", "month to date"),
    ("13WeekPriceReturnDaily", "3 months"),
    ("26WeekPriceReturnDaily", "6 months"),
    ("52WeekPriceReturnDaily", "past year"),
    ("yearToDatePriceReturnDaily", "year to date"),
)
UNRECORDED_REPLIES = {"quote": {"c": 0, "d": None, "dp": None, "t": 0}, "metric": {"metric": {}}, "search": {"count": 0, "result": []}}


class StocksUnavailable(RuntimeError):
    """Finnhub could not be read."""


class StocksRateLimited(StocksUnavailable):
    """Finnhub refused the call because this minute's allowance is spent."""


@dataclass(frozen=True)
class Quote:
    price: float
    change: float  # dollars since the previous close
    change_percent: float
    traded_at: datetime  # the last trade, which says how current the price is


@dataclass(frozen=True)
class Metrics:
    pe_ratio: float | None
    year_low: float | None
    year_low_date: date | None
    year_high: float | None
    year_high_date: date | None
    period_returns: tuple[tuple[str, float], ...]  # ("past week", -2.9), in PERIOD_RETURN_FIELDS order, only the periods Finnhub returned


@dataclass(frozen=True)
class Listing:
    symbol: str
    description: str  # the company's name as Finnhub lists it
    kind: str


@dataclass(frozen=True)
class HeldReply:
    body: dict[str, Any]
    held_until: datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def finnhub_api_key() -> str | None:
    return keychain_secret(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)


def finnhub_key_stored() -> bool:
    """Whether the key is in the Keychain, without reading it; works over SSH, where the Keychain is locked."""
    return keychain_item_stored(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)


class FinnhubClient:
    def __init__(self, settings: StocksSettings, api_key: str, clock: Callable[[], datetime] = utc_now, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._settings = settings
        self._api_key = api_key
        self._clock = clock
        self._transport = transport
        self._held: dict[tuple[str, str], HeldReply] = {}

    async def quote(self, symbol: str) -> Quote | None:
        """None for a symbol Finnhub does not know: it answers those with every field zero."""
        body = await self._reply("quote", symbol, self._quote_held_until)
        if not body.get("t"):
            return None
        return Quote(price=float(body["c"]), change=float(body.get("d") or 0), change_percent=float(body.get("dp") or 0), traded_at=datetime.fromtimestamp(body["t"], UTC))

    async def metrics(self, symbol: str) -> Metrics:
        body = await self._reply("metric", symbol, self._metric_held_until)
        return metrics_from(body.get("metric") or {})

    async def search(self, query: str) -> list[Listing]:
        body = await self._reply("search", query, self._search_held_until)
        return [Listing(symbol=row.get("symbol", ""), description=row.get("description", ""), kind=row.get("type", "")) for row in body.get("result") or []]

    async def _reply(self, kind: str, subject: str, held_until: Callable[[datetime], datetime]) -> dict[str, Any]:
        now = self._clock()
        held = self._held.get((kind, subject))
        if held is not None and now < held.held_until:
            return held.body
        body = self._recorded_reply(kind, subject) if self._settings.fixtures_dir else await self._fetched_reply(kind, subject)
        self._held[(kind, subject)] = HeldReply(body=body, held_until=held_until(now))
        return body

    def _quote_held_until(self, now: datetime) -> datetime:
        return now + timedelta(seconds=self._settings.quote_cache_seconds) if market_in_session(now) else next_opening(now)

    def _metric_held_until(self, now: datetime) -> datetime:
        return now + timedelta(seconds=self._settings.metric_cache_seconds)

    def _search_held_until(self, now: datetime) -> datetime:
        return now + timedelta(seconds=self._settings.search_cache_seconds)

    async def _fetched_reply(self, kind: str, subject: str) -> dict[str, Any]:
        path, params = request_for(kind, subject)
        headers = {"X-Finnhub-Token": self._api_key, "User-Agent": self._settings.user_agent}
        try:
            async with httpx.AsyncClient(base_url=self._settings.base_url, timeout=self._settings.timeout_seconds, transport=self._transport, headers=headers) as client:
                response = await client.get(path, params=params)
        except httpx.HTTPError as error:
            raise StocksUnavailable(f"no answer from Finnhub ({type(error).__name__})") from error
        return reply_body(response, path)

    def _recorded_reply(self, kind: str, subject: str) -> dict[str, Any]:
        path = self._settings.fixtures_dir / fixture_name(kind, subject)
        return json.loads(path.read_text()) if path.exists() else UNRECORDED_REPLIES[kind]


def request_for(kind: str, subject: str) -> tuple[str, dict[str, str]]:
    if kind == "quote":
        return "/quote", {"symbol": subject}
    if kind == "metric":
        return "/stock/metric", {"symbol": subject, "metric": "all"}
    return "/search", {"q": subject}


def reply_body(response: httpx.Response, path: str) -> dict[str, Any]:
    if response.status_code == TOO_MANY_REQUESTS:
        raise StocksRateLimited(f"Finnhub answered 429 for {path}")
    if response.status_code != 200:
        raise StocksUnavailable(f"Finnhub answered {response.status_code} for {path}")
    try:
        body = response.json()
    except ValueError as error:
        raise StocksUnavailable(f"Finnhub sent a reply for {path} that could not be read") from error
    if not isinstance(body, dict):
        raise StocksUnavailable(f"Finnhub sent a reply for {path} that is not an object")
    return body


def fixture_name(kind: str, subject: str) -> str:
    """A recorded reply's file: quote_AAPL.json, metric_BRK.B.json, search_costco.json."""
    return f"{kind}_{re.sub(r'[^a-z0-9]+', '-', subject.lower()).strip('-') if kind == 'search' else subject}.json"


def metrics_from(metric: dict[str, Any]) -> Metrics:
    return Metrics(
        pe_ratio=number_or_none(metric.get("peTTM")),
        year_low=number_or_none(metric.get("52WeekLow")),
        year_low_date=date_or_none(metric.get("52WeekLowDate")),
        year_high=number_or_none(metric.get("52WeekHigh")),
        year_high_date=date_or_none(metric.get("52WeekHighDate")),
        period_returns=tuple((label, float(metric[field])) for field, label in PERIOD_RETURN_FIELDS if number_or_none(metric.get(field)) is not None),
    )


def number_or_none(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def date_or_none(value: Any) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None
