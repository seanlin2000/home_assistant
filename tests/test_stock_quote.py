"""stock_quote (design doc v2/16): names to tickers, the as-of time from the last trade, the market view in fund prices, rounding for speech, the
cache, and what the tool says when Finnhub refuses or is down.

tests/fixtures/finnhub_2026-11-22/ holds Finnhub's replies as recorded early on Sunday 2026-11-22, trimmed to the fields the tool reads. Every quote's
last trade is Friday's 4:00 PM close. Ford's P/E is null there, and Berkshire's B shares carry the A shares' 52-week range, both as Finnhub sent them.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from mcp.server.mcpserver import MCPServer

from assistant_core.agent_loop import filler_for
from assistant_core.models import AgentPolicy, Route, ToolCall
from assistant_core.router import DIRECTIVES
from assistant_core.tools import McpToolBox
from stocks_mcp.companies import CompanyTable, asks_for_the_market, best_listing, normalized, spoken_name
from stocks_mcp.finnhub_client import FinnhubClient, Listing
from stocks_mcp.market_hours import as_of_phrase, market_in_session, next_opening
from stocks_mcp.register import NO_MATCH_MESSAGE, RATE_LIMITED_MESSAGE, SERVICE_DOWN_MESSAGE, STOCK_TOOL_NAME, register_stock_tools
from stocks_mcp.render import pe_lines, return_lines, spoken_change, spoken_percent_change, spoken_price
from stocks_mcp.settings import StocksSettings, stocks_settings_from_environment

RECORDED = Path("tests/fixtures/finnhub_2026-11-22")
FRIDAY_CLOSE = datetime.fromtimestamp(1795208400, UTC)  # 4:00 PM in New York on Friday 2026-11-20
SUNDAY_NIGHT = datetime(2026, 11, 22, 5, 25, tzinfo=UTC)  # 12:25 AM in New York, when the replies were recorded
RECORDED_SETTINGS = StocksSettings(fixtures_dir=RECORDED, now=SUNDAY_NIGHT)
MONDAY_MIDDAY = datetime(2026, 11, 23, 19, 41, tzinfo=UTC)  # 2:41 PM in New York


async def ask(company: str, settings: StocksSettings = RECORDED_SETTINGS, client: FinnhubClient | None = None) -> str:
    server = MCPServer("stocks-test")
    register_stock_tools(server, settings, client=client)
    async with McpToolBox(server) as toolbox:
        return await toolbox.call(ToolCall(id="1", name=STOCK_TOOL_NAME, arguments={"company": company}))


def recorded(name: str) -> dict[str, Any]:
    return json.loads((RECORDED / name).read_text())


class FakeFinnhub:
    """Answers from the recorded replies by URL, counts every request, and can be told to fail; its clock is moved by the test."""

    def __init__(self, now: datetime) -> None:
        self.now = now
        self.status = 200
        self.requests: list[str] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(f"{request.url.path}?{request.url.query.decode()}")
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "refused"})
        symbol = request.url.params.get("symbol", "")
        if request.url.path.endswith("/quote"):
            return httpx.Response(200, json=recorded(f"quote_{symbol}.json"))
        if request.url.path.endswith("/stock/metric"):
            return httpx.Response(200, json=recorded(f"metric_{symbol}.json"))
        return httpx.Response(200, json={"count": 0, "result": []})

    def clock(self) -> datetime:
        return self.now

    def client(self) -> FinnhubClient:
        return FinnhubClient(StocksSettings(), "test-key", self.clock, transport=httpx.MockTransport(self.handle))


async def test_apple_at_fridays_close_gives_every_number_rounded_for_speech() -> None:
    assert (await ask("Apple")).splitlines() == [
        "Apple (AAPL), as of Friday's close",
        "Price: $343, down $6.65 (1.9 percent) on the day",
        "P/E ratio: 37.7",
        "52-week range: $243 (January 20) to $361 (November 13)",
        "Change: past week down 2.9 percent; month to date down 0.6 percent; 3 months up 10.7 percent; 6 months up 14.6 percent; past year up 28.7 percent; year to date up 26.0 percent",
    ]


async def test_the_market_gives_each_funds_own_price_labelled_as_a_fund_never_an_index_level() -> None:
    assert (await ask("the market")).splitlines() == [
        "The market as of Friday's close, from the funds that track each index. These are fund prices, not index levels:",
        "SPY, the S&P 500 fund: $690, down 3.6 percent on the day",
        "QQQ, the Nasdaq-100 fund: $608, down 5.7 percent on the day",
        "DIA, the Dow fund: $481, down 2.0 percent on the day",
    ]


async def test_naming_an_index_asks_for_the_market_view() -> None:
    assert (await ask("S&P 500")).startswith("The market as of Friday's close")
    assert all(asks_for_the_market(words) for words in ("the Dow", "Nasdaq", "the stock market", "S&P"))
    assert not asks_for_the_market("Apple")


async def test_ford_comes_from_the_table_in_cents_and_leaves_out_the_pe_finnhub_did_not_send() -> None:
    lines = (await ask("Ford")).splitlines()
    assert lines[:3] == ["Ford (F), as of Friday's close", "Price: $11.17, down $0.07 (0.6 percent) on the day", "52-week range: $11.04 (November 19) to $17.78 (May 29)"]
    assert not any(line.startswith("P/E") for line in lines)


async def test_berkshire_is_the_b_shares_and_a_range_from_the_a_shares_is_left_out() -> None:
    lines = (await ask("Berkshire Hathaway")).splitlines()
    assert lines[:3] == ["Berkshire Hathaway (BRK.B), as of Friday's close", "Price: $570, down $2.04 (0.4 percent) on the day", "P/E ratio: 14.1"]
    assert not any(line.startswith("52-week range") for line in lines)


async def test_a_ticker_outside_the_table_is_confirmed_by_search_which_gives_its_name() -> None:
    assert (await ask("HIMS")).splitlines()[0] == "Hims & Hers Health Inc (HIMS), as of Friday's close"


async def test_a_name_nothing_matches_asks_the_user_for_the_full_name_or_ticker() -> None:
    assert await ask("Xyzzy Widgets") == NO_MATCH_MESSAGE.format(company="Xyzzy Widgets")
    assert await ask("ZZZZ") == NO_MATCH_MESSAGE.format(company="ZZZZ")


def test_search_drops_foreign_listings_and_prefers_a_name_starting_with_the_words_said() -> None:
    listings = [Listing(symbol=row["symbol"], description=row["description"], kind=row["type"]) for row in recorded("search_ford.json")["result"]]
    assert listings[0].symbol == "FORD.VI"
    chosen = best_listing("Ford", listings)
    assert chosen is not None and (chosen.symbol, chosen.name) == ("F", "Ford Motor Co")


def test_search_keeps_adrs_and_falls_back_to_the_first_us_listing() -> None:
    listings = [Listing("TM", "TOYOTA MOTOR CORP -SPON ADR", "ADR"), Listing("7203.T", "TOYOTA MOTOR CORP", "Common Stock")]
    chosen = best_listing("Toyota Motor", listings)
    assert chosen is not None and (chosen.symbol, chosen.name) == ("TM", "Toyota Motor Corp -spon Adr")
    assert best_listing("Toyota", [Listing("7203.T", "TOYOTA MOTOR CORP", "Common Stock")]) is None


def test_the_table_ignores_case_and_punctuation_and_knows_the_aliases() -> None:
    table = CompanyTable.from_file()
    named = {spoken: table.named(spoken) for spoken in ("apple", "Google", "facebook", "mcdonalds", "P&G", "Coca Cola")}
    assert {spoken: company.symbol for spoken, company in named.items() if company} == {"apple": "AAPL", "Google": "GOOGL", "facebook": "META", "mcdonalds": "MCD", "P&G": "PG", "Coca Cola": "KO"}
    assert normalized("S&P 500") == "s and p 500"


def test_a_name_finnhub_lists_in_capitals_is_said_in_ordinary_case() -> None:
    assert spoken_name("NVIDIA CORP") == "Nvidia Corp"
    assert spoken_name("Hims & Hers Health, Inc.") == "Hims & Hers Health, Inc."


def test_during_trading_hours_a_fresh_trade_is_said_as_a_time_and_the_returns_as_ending_at_the_last_close() -> None:
    traded = MONDAY_MIDDAY - timedelta(minutes=2)
    assert as_of_phrase(traded, MONDAY_MIDDAY, 30) == "as of 2:39 PM Eastern"
    assert return_lines((("past week", 1.24),), market_trading=True) == ["Change through the last close: past week up 1.2 percent"]


def test_a_closed_market_reads_as_the_close_of_the_last_trades_own_day() -> None:
    assert as_of_phrase(FRIDAY_CLOSE, SUNDAY_NIGHT, 30) == "as of Friday's close"
    assert as_of_phrase(FRIDAY_CLOSE, datetime(2026, 11, 23, 13, 0, tzinfo=UTC), 30) == "as of Friday's close"  # Monday, 8 AM
    assert as_of_phrase(FRIDAY_CLOSE, datetime(2026, 11, 21, 1, 0, tzinfo=UTC), 30) == "as of today's close"  # Friday, 8 PM


def test_a_holiday_needs_no_table_because_the_last_trade_is_a_day_old() -> None:
    wednesday_close = datetime(2026, 11, 25, 21, 0, tzinfo=UTC)
    thanksgiving_morning = datetime(2026, 11, 26, 16, 0, tzinfo=UTC)
    assert market_in_session(thanksgiving_morning)
    assert as_of_phrase(wednesday_close, thanksgiving_morning, 30) == "as of yesterday's close"


def test_the_next_opening_skips_the_weekend() -> None:
    assert next_opening(FRIDAY_CLOSE) == datetime(2026, 11, 23, 14, 30, tzinfo=UTC)
    assert next_opening(datetime(2026, 11, 23, 13, 0, tzinfo=UTC)) == datetime(2026, 11, 23, 14, 30, tzinfo=UTC)


def test_prices_are_whole_dollars_from_a_hundred_up_and_cents_below() -> None:
    assert [spoken_price(price) for price in (1102.4, 342.56, 100.0, 99.5, 11.106, 4.371)] == ["$1,102", "$343", "$100", "$99.50", "$11.11", "$4.37"]
    assert spoken_change(-6.65, -1.9043) == "down $6.65 (1.9 percent)" and spoken_change(0.001, 0.0) == "unchanged"
    assert spoken_percent_change(26.006) == "up 26.0 percent" and spoken_percent_change(-0.04) == "unchanged"


def test_a_company_that_lost_money_is_said_to_have_no_pe() -> None:
    assert pe_lines(-12.3) == ["P/E ratio: none, because the company lost money over the last twelve months"]
    assert pe_lines(None) == []


async def test_a_quote_is_reused_for_a_minute_while_the_market_trades() -> None:
    finnhub = FakeFinnhub(MONDAY_MIDDAY)
    client = finnhub.client()
    await client.quote("AAPL")
    finnhub.now += timedelta(seconds=59)
    await client.quote("AAPL")
    finnhub.now += timedelta(seconds=2)
    await client.quote("AAPL")
    assert finnhub.requests == ["/api/v1/quote?symbol=AAPL"] * 2


async def test_a_closed_markets_quote_is_held_until_the_next_opening_bell() -> None:
    finnhub = FakeFinnhub(SUNDAY_NIGHT)
    client = finnhub.client()
    await client.quote("AAPL")
    finnhub.now = datetime(2026, 11, 23, 14, 29, tzinfo=UTC)  # Monday, 9:29 AM
    await client.quote("AAPL")
    finnhub.now = datetime(2026, 11, 23, 14, 30, tzinfo=UTC)
    await client.quote("AAPL")
    assert len(finnhub.requests) == 2


async def test_metrics_are_reused_for_six_hours() -> None:
    finnhub = FakeFinnhub(MONDAY_MIDDAY)
    client = finnhub.client()
    await client.metrics("AAPL")
    finnhub.now += timedelta(hours=5, minutes=59)
    await client.metrics("AAPL")
    finnhub.now += timedelta(minutes=2)
    await client.metrics("AAPL")
    assert finnhub.requests == ["/api/v1/stock/metric?symbol=AAPL&metric=all"] * 2


async def test_a_refusal_for_too_many_calls_says_to_try_again_in_a_minute() -> None:
    finnhub = FakeFinnhub(MONDAY_MIDDAY)
    finnhub.status = 429
    assert await ask("Apple", StocksSettings(), finnhub.client()) == RATE_LIMITED_MESSAGE


@pytest.mark.parametrize("status", [401, 500, 503])
async def test_any_other_refusal_says_the_service_did_not_answer(status: int) -> None:
    finnhub = FakeFinnhub(MONDAY_MIDDAY)
    finnhub.status = status
    assert await ask("Apple", StocksSettings(), finnhub.client()) == SERVICE_DOWN_MESSAGE


async def test_no_answer_at_all_says_the_service_did_not_answer() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    client = FinnhubClient(StocksSettings(), "test-key", lambda: MONDAY_MIDDAY, transport=httpx.MockTransport(unreachable))
    assert await ask("the market", StocksSettings(), client) == SERVICE_DOWN_MESSAGE


async def test_the_key_goes_in_finnhubs_header_with_the_projects_user_agent() -> None:
    seen: list[httpx.Request] = []

    def keep(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=recorded("quote_AAPL.json"))

    await FinnhubClient(StocksSettings(), "test-key", lambda: MONDAY_MIDDAY, transport=httpx.MockTransport(keep)).quote("AAPL")
    assert seen[0].headers["X-Finnhub-Token"] == "test-key" and seen[0].headers["User-Agent"].startswith("studio-assistant-stocks/")
    assert "test-key" not in str(seen[0].url)


async def test_without_a_key_the_tool_is_not_offered_but_recorded_replies_need_none() -> None:
    bare, recorded_server = MCPServer("no-key"), MCPServer("recorded")
    register_stock_tools(bare, StocksSettings())  # tests/conftest.py makes every Keychain read find nothing
    register_stock_tools(recorded_server, RECORDED_SETTINGS)
    assert STOCK_TOOL_NAME not in {tool.name for tool in await bare.list_tools()}
    assert STOCK_TOOL_NAME in {tool.name for tool in await recorded_server.list_tools()}


def test_settings_come_from_stocks_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKS_QUOTE_CACHE_SECONDS", "30")
    monkeypatch.setenv("STOCKS_FIXTURES_DIR", "")
    settings = stocks_settings_from_environment()
    assert settings.quote_cache_seconds == 30 and settings.fixtures_dir is None


def test_the_filler_names_the_markets_and_is_dropped_from_replayed_answers() -> None:
    policy = AgentPolicy()
    assert filler_for(STOCK_TOOL_NAME, policy) in policy.stocks_filler_phrases
    assert set(policy.stocks_filler_phrases) <= set(policy.every_filler_phrase)


def test_the_stocks_directive_names_the_tool_asks_for_a_company_and_keeps_fund_prices_apart_from_index_levels() -> None:
    directive = DIRECTIVES[Route.STOCKS]
    assert "stock_quote" in directive and "ask which one" in directive and "never index levels" in directive


async def test_a_fund_asked_about_alone_has_no_pe_line_and_says_its_own_name() -> None:
    lines = (await ask("SPY")).splitlines()
    assert lines[0] == "SPDR S&P 500 ETF (SPY), as of Friday's close"
    assert not any(line.startswith("P/E") for line in lines) and any(line.startswith("52-week range") for line in lines)
