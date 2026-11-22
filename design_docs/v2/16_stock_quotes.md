# 16. Stock quotes

Status: building

## 1. Purpose

Jarvis gives a stock's price and a few basic numbers from Finnhub's market data. It should answer:

- "What's Apple trading at?"
- "What's Nvidia's P/E ratio?"
- "How has Costco done this year?"
- "How's the market doing today?" Jarvis gives the S&P 500, Nasdaq-100, and Dow through the funds that track them.
- "How's my stock doing?" Jarvis asks which company; it never guesses one.

**Every number comes from Finnhub at the moment of the question.** Nothing is answered from the model's memory, and the answer always says how current it is.

Why a stock is moving, and market news, stay with the newsletters tools (doc 14) and web search.

## 2. Diagram

```
 A QUESTION

 ╭──────────────────────╮              ╭──────────────────────╮              ╭──────────────────────╮              ╭──────────────────────╮
 │    your question     │              │   main model call    │ tool call    │     stock_quote      │              │       speaker        │
 │  how's Apple doing?  │─────────────▶│    picks the tool    │─────────────▶│     one company      │              │  voice on the puck   │
 ╰──────────────────────╯              ╰──────────────────────╯              ╰──────────────────────╯              ╰──────────────────────╯
                                             │     ▲ quote, marked untrusted             │                                     ▲
                                             │     └─────────────────────────────────────┘                                     │
                                             │                                                                                 │ its answer
                                             └─────────────────────────────────────────────────────────────────────────────────┘

 INSIDE STOCK_QUOTE, EACH CALL

 ╭──────────────────────╮              ╭══════════════════════╮              ╭──────────────────────╮              ╭──────────────────────╮
 │    name to ticker    │ ticker       │     quote cache      │ on a miss    │       Finnhub        │ numbers      │      text block      │
 │  table, else search  │─────────────▶│ 60 s, or to the open │─────────────▶│  quote and metrics   │─────────────▶│ rounded, as-of time  │
 ╰──────────────────────╯              ╰══════════════════════╯              ╰──────────────────────╯              ╰──────────────────────╯
```

## 3. How it works, step by step

### 3.1 Finnhub

Finnhub's REST API at `https://finnhub.io/api/v1` serves US quotes and company metrics on a free plan. The key is sent in the `X-Finnhub-Token` header. Three endpoints are used:

| Endpoint | Fields used | What they are |
|---|---|---|
| `/quote?symbol=AAPL` | `c`, `d`, `dp`, `t` | Last price, change since the previous close in dollars and in percent, and the last trade's time (Unix seconds) |
| `/stock/metric?symbol=AAPL&metric=all` | `peTTM` | P/E ratio over the trailing twelve months |
| | `52WeekHigh`, `52WeekHighDate`, `52WeekLow`, `52WeekLowDate` | The year's range, with dates |
| | `5DayPriceReturnDaily`, `monthToDatePriceReturnDaily`, `13WeekPriceReturnDaily`, `26WeekPriceReturnDaily`, `52WeekPriceReturnDaily`, `yearToDatePriceReturnDaily` | Percent change over the past week, month to date, 3 months, 6 months, year, and year to date |
| `/search?q=Costco` | `symbol`, `description`, `type` | Company name to ticker, for names outside the table (§3.2) |

**Checked live on 2026-11-22**, with the free key, on a Sunday:

- Every endpoint above answered HTTP 200.
- Apple's metrics held 133 keys, including all of the above.
- SPY's held 19 keys: the returns and the 52-week range, but no P/E. A fund has no earnings, so its P/E line is left out (§3.5).
- Every quote's `t` was Friday, November 20, at 4:00 PM New York time, the close.
- An unknown ticker (`FORD`) returns HTTP 200 with every field zero. The tool treats `t = 0` as "no such ticker".
- "Month to date" is a real limit, not a choice. Finnhub has no trailing one-month return, so the tool never says "past month".
- Berkshire's B shares (BRK.B) carry the A shares' 52-week range, $698,000 to $894,950, beside a $570 price. Toyota's US shares (TM) carry its Tokyo range in yen, a high of 4,000 beside a $207 price. A range that misses the price by more than half or double belongs to another listing, so it is left out (§3.5).
- Ford's `peTTM` is null rather than negative. A missing P/E is left out, and a negative one is said as "none, because the company lost money".
- Every one of the 127 tickers in the name table returned a quote, and its search listing named the same company (checked 2026-11-22).

**Two calls per stock.** A single stock costs one quote and one metrics call. The market view costs three quotes. The response headers showed quotes and metrics counting against separate 60-per-minute limits, which matches Finnhub's terms of one limit per data type.

**Whether the returns include today** could not be checked on a weekend. The name `…Daily` says they are computed from daily closes, so while the market trades the result line reads "Change through the last close". The first weekday call during trading hours confirms it; if the returns turn out to include today, the label drops "through the last close".

### 3.2 Name to ticker

The `company` argument holds what you said, in the model's spelling. It is resolved in this order, and the first rule that matches decides:

| # | Input | Becomes |
|---|---|---|
| 1 | "the market", "stocks", "S&P 500", "S&P", "Nasdaq", "Dow" | The market view (§3.4) |
| 2 | A name or alias in `stocks_mcp/companies.json`: "Apple", "Google", "Facebook", "Berkshire" | Its ticker: AAPL, GOOGL, META, BRK.B |
| 3 | Capital letters shaped like a ticker: "NVDA", "F", "BRK.B" | Used as given |
| 4 | Anything else: "Costco", "Rivian" | One `/search` call (below) |

**The table.** 127 companies and funds people ask about, keyed by the names said aloud, with common aliases. Lookup ignores case and punctuation, and says "&" as "and", so "P&G" and "S&P" match. It is written by hand and checked in.

The table exists for names a search gets wrong. Live on 2026-11-22:

- `/search?q=Ford` listed FORD.VI (Ford on the Vienna exchange) before F.
- "Berkshire Hathaway" returned only BRK.A, the class costing hundreds of thousands of dollars a share, when people mean BRK.B.
- "Shell" returned only Shell's listings abroad, never SHEL, its US one. Common foreign companies (Shell, BP, AstraZeneca, Unilever, HSBC, Toyota, TSMC, Sony, and others) are in the table for that reason.

**Only capitals count as a ticker.** "Ford" in the model's spelling is a name. Read as a ticker it would be FORD, a different company.

**Choosing a search result:**

1. **Drop listings outside the US.** Symbols with an exchange suffix (`FORD.VI`, `ONT.L`) are dropped. That also drops US class shares such as BRK.B, which is why they are in the table.
2. **Keep only shares and funds.** That means the `Common Stock`, `ETP`, `ADR`, and `NY Reg Shrs` types. Foreign companies such as Toyota and TSMC trade in the US as ADRs, and ASML as New York registry shares.
3. **Prefer a name that starts with the words said.** "Ford" picks "Ford Motor Co" over "The Hartford" and "Rexford Industrial". Otherwise the first remaining result wins.
4. **No result.** The tool says so (§3.8, item 8).
5. **Names in capitals are said in ordinary case.** Finnhub lists many companies as "NVIDIA CORP", which a voice may spell out letter by letter, so such a name is said as "Nvidia Corp".

**The company name and ticker always come first** in the result, and the tool description tells the model to say them, so a wrong match is heard.

### 3.3 Market hours and the as-of time

The answer always says how current its price is. The time comes from the quote's own `t` (the last trade), in New York time:

| When | The result's first line says |
|---|---|
| A weekday from 9:30 AM to 4:00 PM, last trade under 30 minutes old | "as of 2:41 PM Eastern" |
| Any other time | "as of Friday's close": the day of the last trade, as "today", "yesterday", or a weekday name |

**No holiday table.** On a market holiday the last trade is a day or more old during what would be trading hours, so the second row applies on its own: "as of Wednesday's close" on Thanksgiving. An early 1:00 PM close works the same way, as "as of today's close".

`t` was exactly 4:00 PM on Friday in the live check, so a closed market reads its close correctly.

Finnhub's `/stock/market-status` endpoint also works on the free plan. It is not needed: the last trade answers the one question the tool asks.

### 3.4 The market view

"The market" reads three funds, one quote each:

| Fund | Tracks | Said as |
|---|---|---|
| SPY | S&P 500 | "SPY, the S&P 500 fund" |
| QQQ | Nasdaq-100 | "QQQ, the Nasdaq-100 fund" |
| DIA | Dow Jones Industrial Average | "DIA, the Dow fund" |

**Why funds, not the indexes.** Finnhub's free plan has no index quotes. A fund's percent change for the day follows its index almost exactly.

**Fund prices are not index levels.** SPY trades near a tenth of the S&P 500 and DIA near a hundredth of the Dow. Each ratio drifts by about half a percent, because the fund collects dividends between payouts and charges a small fee. QQQ follows the Nasdaq-100, not the Nasdaq Composite that newscasts usually quote, at a ratio with no round number.

So the result gives each fund's own price, labelled as a fund. Its header says "These are fund prices, not index levels", and the tool description says the same. A converted "the S&P is around 6,900" would be off by tens of points.

### 3.5 Rounding and the spoken result

| Value | Written as | Example |
|---|---|---|
| A price of $100 or more | Whole dollars | $343 |
| A price under $100 | Cents | $11.17 |
| A change in dollars | Cents | down $6.65 |
| A percentage | One decimal, the word "percent" | down 1.9 percent |
| P/E | One decimal | 37.7 |
| A date | Month and day, plus the year if it is not this year (`utils/text_utils.spoken_month_day`) | January 20 |

Cents start below $100, not $10: Ford in whole dollars read "$11" beside a 52-week low of "$11".

A metric Finnhub does not return is left out, never written as "n/a". So is a 52-week range that misses the price by more than half or double, which is another listing's (§3.1).

Example result, from the live check on 2026-11-22:

```
Apple (AAPL), as of Friday's close
Price: $343, down $6.65 (1.9 percent) on the day
P/E ratio: 37.7
52-week range: $243 (January 20) to $361 (November 13)
Change: past week down 2.9 percent; month to date down 0.6 percent; 3 months up 10.7 percent; 6 months up 14.6 percent; past year up 28.7 percent; year to date up 26.0 percent
```

The market view, from the same moment:

```
The market as of Friday's close, from the funds that track each index. These are fund prices, not index levels:
SPY, the S&P 500 fund: $690, down 3.6 percent on the day
QQQ, the Nasdaq-100 fund: $608, down 5.7 percent on the day
DIA, the Dow fund: $481, down 2.0 percent on the day
```

Every number is in the result, but the tool description tells the model to say only the ones the question asks for. "What's Apple trading at?" is answered with the first two lines.

### 3.6 The tool

This is the whole definition the model sees. Its rules live here, not in the system prompt, as prompt 3.0 moved every tool's rules into the tool's own definition.

```python
@server.tool(name=STOCK_TOOL_NAME)
async def stock_quote(
    company: Annotated[
        str,
        Field(max_length=MAX_COMPANY_CHARS, description='one company, fund, or ticker as the user said it, e.g. "Apple", "NVDA", "Berkshire Hathaway"; "the market" for the S&P 500, Nasdaq, and Dow together'),
    ],
) -> str:
    """Current share price and basic metrics for one US-listed company or fund: price, today's change, P/E ratio, 52-week high and low, and percent change over the past week, month to date, 3 months, 6 months, year, and year to date. For how the market or stocks are doing overall, pass "the market"; it returns the SPY, QQQ, and DIA funds, so call their prices fund prices, never the index level. Use this, never a web search, for a stock's price or performance; for why a stock moved or market news, use the newsletters tools or search. If the user names no company, ask which one; do not guess. Say the company name the result gives and only the numbers the user asked for, with the as-of time the result states."""
```

| Argument | Required | Maximum length |
|---|---|---|
| `company` | yes, so the model cannot call the tool without one | 60 |

Two companies in one question means two calls.

### 3.7 Benchmark coverage

- **Recorded replies.** `benchmark/record_stock_fixtures.py` saves Finnhub's replies for the benchmark's companies and the three funds at one moment. The benchmark's tool server reads them instead of Finnhub, with "now" pinned to that moment (`STOCKS_FIXTURES_DIR`, `STOCKS_NOW`), as the subway feeds are. The benchmark never needs the key.
- **Graded questions.** A new category M holds four:
  - a price ("What's Apple trading at?");
  - a P/E and a period ("What's Nvidia's P/E, and how has it done this year?");
  - the market view ("How's the market doing today?"), whose answer must call fund prices fund prices;
  - a company outside the name table, which goes through `/search`.
- **Injection.** One category H question meets a made-up `/search` result whose description carries an instruction. That text is the only place a stranger's words can enter this tool.
- **Tool choice.** Checks that:
  - stock questions call `stock_quote`;
  - "Why did Tesla drop today?" goes to search or the newsletters, not `stock_quote`;
  - "How's my stock doing?" calls no tool, because Jarvis must ask which company.

  Existing checks about current prices or rates are reviewed in PR 3, and any that a stock tool can also answer accept it.

### 3.8 Security: the new-tool checklist

The answers to doc 12 §3.12:

| # | Question | Answer |
|---|---|---|
| 1 | Tier, and does the output mark the exchange untrusted? | `read_public`, and yes. Prices are numbers, but a name found through `/search` is text from Finnhub's listings, as ESPN's names under a box score are, and those are marked. |
| 2 | Quarantined reader? | No. The only text is one company name per result, from Finnhub's fixed host, and the exchange is marked untrusted. Recorded in `DEVIATIONS.md`. |
| 3 | Argument schema | One string with a maximum length of 60 (§3.6). |
| 4 | What leaves the house? | The ticker, or for a name outside the table the name as said, sent to `finnhub.io`. Finnhub learns which companies are asked about. As a `read_public` tool, its argument passes the egress guard. |
| 5 | Credentials | The Finnhub key, in the Keychain under service `studio-assistant`, account `finnhub-api`, read once when the tool server starts (`utils/keychain_utils.keychain_secret`), as the Brave key is. It grants read-only market data and nothing else. Without it the tool is not offered (§6). |
| 6 | Terms and rate limits | Finnhub's plans are for personal use only, which a household assistant is. The terms forbid sharing access or derived data, and Jarvis speaks only to the home. The free plan allows 60 calls a minute per data type, plus 30 a second overall. A question costs at most three calls, and the cache (§5) holds a quote for a minute while the market is open and until the next open when it is closed. Requests send `descriptive_user_agent("stocks")`. |
| 7 | Benchmark questions | §3.7, including an injection through a planted `/search` result. |
| 8 | Failure sentences | "Stock error: no US-listed company matched X. Ask the user for the company's full name or its ticker." / "Stock error: the stock price service did not answer. Tell the user you could not get stock prices right now." / "Stock error: too many stock lookups this minute. Tell the user to try again in a minute." |

### 3.9 Context budget

| | Tokens |
|---|---|
| The tool's definition, added to the fixed prompt | about 280. Its name, description, and schema come to 1,039 characters against `subway_arrivals`' 1,151 by the same count, and subway's definition is about 310 tokens. |
| One result | about 100 for a stock, about 80 for the market view |

## 4. Packages and what they do for the business logic

| Package | What it does |
|---|---|
| `httpx` (already a dependency) | Calls Finnhub's REST API |
| `stocks_mcp/` (ours) | Name to ticker, the Finnhub client and cache, market hours, rounding, and the tool |

No new dependency.

## 5. Configuration we control

**`StocksSettings`**, read from `STOCKS_`-prefixed environment variables:

| Setting | Default | Purpose |
|---|---|---|
| `base_url` | `https://finnhub.io/api/v1` | Where the API lives |
| `timeout_seconds` | 8 | How long one call may take |
| `quote_cache_seconds` | 60 | How long a quote is reused while the market is open. When it is closed, a quote is held until the next 9:30 AM weekday. |
| `metric_cache_seconds` | 21600 | How long metrics are reused (6 hours); they change once a day |
| `search_cache_seconds` | 86400 | How long a symbol search is reused (a day) |
| `fresh_trade_minutes` | 30 | A last trade younger than this, during trading hours, is said as a time rather than a close |
| `user_agent` | `descriptive_user_agent("stocks")` | Names the project to Finnhub |
| `fixtures_dir`, `now` | unset | Recorded replies and a pinned clock, for the benchmark and tests only |

**Elsewhere:**

- `config/tools.toml`: `stock_quote` is `read_public` and `marks_untrusted`.
- `stocks_mcp/companies.json`: the name table (§3.2).
- The Keychain: the Finnhub key (§3.8, item 5). `scripts/bootstrap_mac.sh` stores it on a new Mac and `scripts/export_to_new_mac.sh` carries it over, as they do the Brave key.

## 6. Failure modes

| Failure | What happens | What to do |
|---|---|---|
| No key in the Keychain | The tool is not offered, the tool server logs a warning, and `ops/health.py` reports the key missing. Stock questions fall back to web search. | Store the key (§5) and restart the tool server |
| The key is wrong or revoked | Finnhub answers 401, and the tool says it could not get stock prices | Store a new key |
| Finnhub is down | The tool says it could not get stock prices | Nothing; ask again later |
| More than 60 calls in a minute | Finnhub answers 429, and the tool says to try again in a minute | Nothing; at three calls a question this needs a burst of twenty questions |
| A name outside the table matches the wrong company | The answer names the company and ticker it used, so you hear the mistake | Say the ticker, or add the name to the table |
| No company matches | The tool says so, and Jarvis asks for the full name or ticker | Say it again |
| A planted search result carries an injected order | The exchange is untrusted, so an act-tier tool would ask you first, and the egress guard checks every search | Nothing; the category H question tests it |
| Finnhub renames a metric | That line is left out of every answer | Update the field name in `stocks_mcp/` |

## 7. Concepts for newcomers

**Ticker.** The short code a stock trades under: AAPL for Apple, F for Ford. A company with several share classes has one per class, such as BRK.A and BRK.B for Berkshire Hathaway.

**P/E ratio.** Price divided by earnings per share over the last twelve months. A P/E of 37.7 means buyers pay $37.70 for each dollar the company earned last year. A fund has no earnings of its own, so it has no P/E.

**ETF.** An exchange-traded fund: a basket of stocks that trades like one stock. SPY holds the 500 companies of the S&P 500, so its price moves with that index.

**Previous close.** The last price of the previous trading day, at 4:00 PM New York time. "Today's change" is measured from it.

**52-week range.** The lowest and highest prices of the past year.

## 8. Sources

- Finnhub API documentation: [finnhub.io/docs/api](https://finnhub.io/docs/api)
- Finnhub pricing and the free plan's limits: [finnhub.io/pricing](https://finnhub.io/pricing)
- Finnhub terms of service, read 2026-11-22: [finnhub.io/terms-of-service](https://finnhub.io/terms-of-service)
- SPY, QQQ, and DIA fund pages: [ssga.com SPY](https://www.ssga.com/us/en/intermediary/etfs/spdr-sp-500-etf-trust-spy), [invesco.com QQQ](https://www.invesco.com/qqq-etf/en/home.html), [ssga.com DIA](https://www.ssga.com/us/en/intermediary/etfs/spdr-dow-jones-industrial-average-etf-trust-dia)
