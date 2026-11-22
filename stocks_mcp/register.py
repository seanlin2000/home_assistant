"""Expose stock quotes as an MCP tool on the shared tool server (design doc v2/16 section 3.6).

The tool's rules live in its own description, since prompt 3.0 moved each tool's rules into its definition. Without the Finnhub key in the Keychain
the tool is not offered, unless recorded replies stand in for Finnhub, as in the benchmark and tests.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from stocks_mcp.companies import MARKET_FUNDS, CompanyTable, asks_for_the_market, find_company
from stocks_mcp.finnhub_client import KEYCHAIN_ACCOUNT, KEYCHAIN_SERVICE, FinnhubClient, StocksRateLimited, StocksUnavailable, finnhub_api_key, utc_now
from stocks_mcp.render import FundQuote, StockAnswer, market_text, stock_text
from stocks_mcp.settings import StocksSettings

STOCK_TOOL_NAME = "stock_quote"
MAX_COMPANY_CHARS = 60
NO_MATCH_MESSAGE = 'Stock error: no US-listed company matched "{company}". Ask the user for the company\'s full name or its ticker.'
SERVICE_DOWN_MESSAGE = "Stock error: the stock price service did not answer. Tell the user you could not get stock prices right now."
RATE_LIMITED_MESSAGE = "Stock error: too many stock lookups this minute. Tell the user to try again in a minute."
_LOGGER = logging.getLogger(__name__)


def register_stock_tools(server: MCPServer, settings: StocksSettings, clock: Callable[[], datetime] = utc_now, client: FinnhubClient | None = None) -> None:
    moment = (lambda: settings.now) if settings.now else clock
    client = client or finnhub_client_for(settings, moment)
    if client is None:
        _LOGGER.warning("%s is not offered: no Finnhub key in the Keychain (service %s, account %s; design doc v2/16 section 5)", STOCK_TOOL_NAME, KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)
        return
    table = CompanyTable.from_file()

    @server.tool(name=STOCK_TOOL_NAME)
    async def stock_quote(
        company: Annotated[
            str,
            Field(
                max_length=MAX_COMPANY_CHARS,
                description='one company, fund, or ticker as the user said it, e.g. "Apple", "NVDA", "Berkshire Hathaway"; "the market" for the S&P 500, Nasdaq, and Dow together',
            ),
        ],
    ) -> str:
        """Current share price and basic metrics for one US-listed company or fund: price, today's change, P/E ratio, 52-week high and low, and percent change over the past week, month to date, 3 months, 6 months, year, and year to date. For how the market or stocks are doing overall, pass "the market"; it returns the SPY, QQQ, and DIA funds, so call their prices fund prices, never the index level. Use this, never a web search, for a stock's price or performance; for why a stock moved or market news, use the newsletters tools or search. If the user names no company, ask which one; do not guess. Say the company name the result gives and only the numbers the user asked for, with the as-of time the result states."""
        try:
            return await quote_text(company.strip(), table, client, moment(), settings)
        except StocksRateLimited as error:
            _LOGGER.warning("%s failed: %s", STOCK_TOOL_NAME, error)
            return RATE_LIMITED_MESSAGE
        except StocksUnavailable as error:
            _LOGGER.warning("%s failed: %s", STOCK_TOOL_NAME, error)
            return SERVICE_DOWN_MESSAGE


def finnhub_client_for(settings: StocksSettings, clock: Callable[[], datetime]) -> FinnhubClient | None:
    """Recorded replies need no key; otherwise the key is read once, here, when the tool server starts."""
    api_key = "" if settings.fixtures_dir else finnhub_api_key()
    return FinnhubClient(settings, api_key, clock) if api_key is not None else None


async def quote_text(spoken: str, table: CompanyTable, client: FinnhubClient, now: datetime, settings: StocksSettings) -> str:
    if asks_for_the_market(spoken):
        return await market_answer(client, now, settings)
    company = await find_company(spoken, table, client)
    if company is None:
        return NO_MATCH_MESSAGE.format(company=spoken)
    quote, metrics = await asyncio.gather(client.quote(company.symbol), client.metrics(company.symbol))
    if quote is None:
        return NO_MATCH_MESSAGE.format(company=spoken)
    return stock_text(StockAnswer(company=company, quote=quote, metrics=metrics, now=now, fresh_trade_minutes=settings.fresh_trade_minutes))


async def market_answer(client: FinnhubClient, now: datetime, settings: StocksSettings) -> str:
    quotes = await asyncio.gather(*(client.quote(fund.symbol) for fund in MARKET_FUNDS))
    if all(quote is None for quote in quotes):
        raise StocksUnavailable("Finnhub returned no quote for any market fund")
    return market_text([FundQuote(fund=fund, quote=quote) for fund, quote in zip(MARKET_FUNDS, quotes)], now, settings.fresh_trade_minutes)
