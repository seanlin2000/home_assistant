"""From what the user said to a ticker (design doc v2/16 section 3.2): the market words first, then the checked-in name table, then capitals shaped
like a ticker, then one Finnhub search. The table exists for names a search gets wrong: "Ford" ranks Ford's Vienna listing first, and "Berkshire
Hathaway" finds only the A shares."""

import json
import re
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from stocks_mcp.finnhub_client import LISTING_TYPES, Listing

COMPANIES_PATH = Path(__file__).with_name("companies.json")
TICKER_SHAPE = re.compile(r"[A-Z]{1,5}(\.[A-Z])?")
MARKET_WORDS = frozenset(
    {"market", "the market", "stock market", "the stock market", "stocks", "s and p", "s and p 500", "the s and p", "the s and p 500", "nasdaq", "the nasdaq", "dow", "the dow", "dow jones"}
)


@dataclass(frozen=True)
class Company:
    symbol: str
    name: str  # as the answer says it: the table's name, or Finnhub's listing


@dataclass(frozen=True)
class Fund:
    symbol: str
    described: str


# The market view (section 3.4). Finnhub's free plan has no index quotes, so each index is read from the fund that tracks it, and the answer says so.
MARKET_FUNDS = (Fund("SPY", "the S&P 500 fund"), Fund("QQQ", "the Nasdaq-100 fund"), Fund("DIA", "the Dow fund"))


class SymbolSearch(Protocol):
    async def search(self, query: str) -> list[Listing]: ...


class CompanyTable:
    def __init__(self, by_name: dict[str, Company], by_symbol: dict[str, Company]) -> None:
        self._by_name = by_name
        self._by_symbol = by_symbol

    @classmethod
    def from_file(cls, path: Path = COMPANIES_PATH) -> "CompanyTable":
        rows = json.loads(path.read_text())
        by_name: dict[str, Company] = {}
        by_symbol: dict[str, Company] = {}
        for row in rows:
            company = Company(symbol=row["symbol"], name=row["name"])
            by_symbol[company.symbol] = company
            by_name.update({normalized(name): company for name in [row["name"], *row["aliases"]]})
        return cls(by_name, by_symbol)

    def named(self, spoken: str) -> Company | None:
        return self._by_name.get(normalized(spoken))

    def with_symbol(self, symbol: str) -> Company | None:
        return self._by_symbol.get(symbol)


def asks_for_the_market(spoken: str) -> bool:
    return normalized(spoken) in MARKET_WORDS


def normalized(text: str) -> str:
    """Lowercase words with punctuation dropped and "&" said as "and": "S&P 500" is "s and p 500", "McDonald's" is "mcdonalds"."""
    spaced = re.sub(r"[^a-z0-9]+", " ", text.lower().replace("&", " and ").replace("'", "").replace("’", ""))
    return " ".join(spaced.split())


async def find_company(spoken: str, table: CompanyTable, search: SymbolSearch) -> Company | None:
    company = table.named(spoken)
    if company is not None:
        return company
    if TICKER_SHAPE.fullmatch(spoken):
        return table.with_symbol(spoken) or listed_symbol(spoken, await search.search(spoken))
    return best_listing(spoken, await search.search(spoken))


def listed_symbol(symbol: str, listings: list[Listing]) -> Company | None:
    """A ticker outside the table, confirmed by a search result with exactly that symbol, which also gives the company's name."""
    return next((Company(symbol=listing.symbol, name=spoken_name(listing.description)) for listing in listings if listing.symbol == symbol), None)


def best_listing(spoken: str, listings: list[Listing]) -> Company | None:
    """Shares and funds traded in the US only (a symbol with an exchange suffix is listed elsewhere), preferring a name that starts with the words said."""
    us_listings = [listing for listing in listings if "." not in listing.symbol and listing.kind in LISTING_TYPES]
    words = normalized(spoken)
    starting = [listing for listing in us_listings if f"{normalized(listing.description)} ".startswith(f"{words} ")]
    chosen = (starting or us_listings or [None])[0]
    return Company(symbol=chosen.symbol, name=spoken_name(chosen.description)) if chosen else None


def spoken_name(description: str) -> str:
    """Finnhub lists some companies in capitals ("NVIDIA CORP"), which a voice may spell out letter by letter; those are said as "Nvidia Corp"."""
    return string.capwords(description.lower()) if description.isupper() else description
