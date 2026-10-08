# 03. Tool server

Status: designed 2026-10-08

## 1. Purpose

The tools the assistant can call, and what v2 changes about them. The tool server is still one MCP server, `assistant-tools`, with the search, page-reading, Wikipedia, calculator and weather tools of v1. v2 changes four things:
- **Weather anywhere.** The forecast tool takes an optional place, so "will it rain in Lisbon on Saturday?" gets a forecast instead of a web search (M4).
- **A tier for every tool.** Each tool has a tier and a trust setting, which the harness enforces (doc 12 §3.3). The table is in 3.1.
- **Fixture search for the benchmark.** The benchmark's own copy of the server can return prepared pages instead of live results, so the injection questions are the same on every run (M3, doc 01 §3.3).
- **Sports, and later Reddit.** Their sections here are placeholders, filled in by the milestones that build them (M7 and M11).

v1/03 still describes how search, page reading, Wikipedia, the calculator and the home forecast work.

Two rules from doc 12 are applied in the harness, not here:
- removing hidden characters and marking tool output as data (doc 12 §3.7);
- `fetch_page` provenance (doc 12 §3.5).

The harness sees every tool's output, and every conversation's search results, so one check there covers every tool server.

From M2 the server listens on `127.0.0.1` only, because only the harness and the benchmark call it (doc 08 §3.2).

## 2. Diagram

v1/03's figures still apply. The only new path is the place lookup for weather anywhere (3.2):

1. The model passes `place`.
2. The tool server asks Open-Meteo's geocoding service for the place's coordinates and time zone, once per place name.
3. It asks Met.no for that place's forecast, exactly as it does for home.

## 3. How it works, step by step

### 3.1 Every tool, with its tier

The harness keeps this table in `config/tools.toml` and refuses any tool that is not in it (doc 12 §3.3):

| Tool | Tier | Marks the exchange untrusted | What leaves the house | Since |
|---|---|---|---|---|
| `search_and_read`, `web_search` | Read public | Yes | The query, to SearXNG's engines; then the result pages are fetched | v1 |
| `fetch_page` | Read public | Yes | The address, which must have come from this conversation's results or your words (doc 12 §3.5) | v1 |
| `wikipedia_lookup` | Read public | Yes | The article title, to Wikipedia | v1 |
| `calculate`, `percent`, `convert`, `growth_schedule`, `energy_cost`, `loan_payment`, `break_even`, `date_math` | Local | No | Nothing | v1 |
| `weather_forecast` | Read public | No: numbers and place names from fixed services | For home, coordinates rounded to four decimals, as in v1. For another place, its name to Open-Meteo and its coordinates to Met.no | v1, place in M4 |
| Sports statistics | Read public | No | The team or player, to the data source | M7 |
| The Reddit reader | Read public | Yes, and through the quarantined reader (doc 12 §3.6) | The thread's address, to Reddit | M11 |

A tool marks the exchange untrusted when its text is written by strangers. A forecast is numbers from Met.no, and a place name comes from Open-Meteo's gazetteer, so neither can carry an instruction worth worrying about.

### 3.2 Weather anywhere (M4)

`weather_forecast` gains one optional argument, `place`:

| Argument | Values | Default |
|---|---|---|
| `day` | `today`, `tomorrow`, a weekday, `weekend`, `week`, as in v1 | `today` |
| `part_of_day` | `morning`, `afternoon`, `evening`, `night`, `all`, as in v1 | `all` |
| `place` | A place name as spoken, with a region or country after a comma when needed: `Lisbon`, `Paris, Texas`. At most 80 characters | Home |

Without `place`, nothing changes from v1: home's coordinates come from the server's environment and never appear in the conversation.

With `place`, the server:
1. **Looks the place up.** It asks Open-Meteo's geocoding service for the name before the comma, at most ten matches, in English.
2. **Picks one match.**
   - When the name has a part after the comma, the first match whose region, country or country code starts with that part is used. "Paris, Texas" picks Texas, not France.
   - Otherwise the first match is used. Open-Meteo orders matches by population, so "Paris" is Paris, France.
3. **Remembers the answer.** The match is cached permanently by the spoken name, because places do not move: the place's name, region, country, coordinates (rounded to four decimals) and time zone.
4. **Reads the forecast.** It asks Met.no for those coordinates through the same client and the same rules as for home:
   - the User-Agent;
   - four decimals;
   - holding each forecast until its `Expires` time.

   The client holds one forecast per place instead of one in total, at most 32 places, dropping the oldest.
5. **Groups the forecast in the place's own time.** It groups the time steps into days and parts of the day in the place's time zone, so "tomorrow afternoon in Tokyo" is Tokyo's afternoon. Units stay the household's.
6. **Names the place in the heading.** For example, "Forecast for Lisbon, Lisbon, Portugal, tomorrow, Saturday October 10:". The answer can then say which Lisbon it means, and the benchmark can check the place (doc 01 §3.4).

When nothing matches, the result is a sentence the model can repeat: "Weather error: no place called Lisbonn was found. Ask the user to say the place again, with its country." When the geocoding service does not answer and the name is not cached, the result says the forecast for that place is unavailable right now.

What changes around the tool:
- **The router.** A question about coming or current weather now routes to `weather` whether or not it names another place. The rule layer no longer has to tell places apart from times. The weather directive's example shows a call with a place: `weather_forecast(day="saturday", part_of_day="all", place="Lisbon")`.
- **The system prompt.** Its "Weather at home" section becomes "Weather": call `weather_forecast` for the weather anywhere, and pass `place` unless the question is about home.
- **The filler line.** It is unchanged: "Checking the forecast."

Open-Meteo's terms and how the server meets them:

| Term | How it is met |
|---|---|
| Free for non-commercial use, without a key, up to 10,000 requests a day | One request per new place name, then never again for that name |
| Credit the data (CC BY 4.0) | This doc names Open-Meteo as the source of place coordinates; nothing is republished |

Privacy:
- Open-Meteo sees the place name and the apartment's IP address.
- Met.no sees the place's coordinates.
- Neither sees the question.
- The place name passes the egress guard like any other argument (doc 12 §3.4), so a private place from memory that you did not say is never sent.

### 3.3 Fixture search for the benchmark (M3)

The injection questions (doc 01 §3.3) need pages whose content is known, on every run. The benchmark therefore starts its own copy of the tool server with `WEB_SEARCH_FIXTURES_DIR` pointing at `benchmark/fixtures/pages/`, and the server then behaves differently in three ways:
1. **A route to choose a set.** It adds one HTTP route, `POST /benchmark/fixture`, that selects a named set of pages, or none.
2. **Searches return only that set.** While a set is selected, `search_and_read` and `web_search` return that set's pages for any query, in the same format as live results, and contact no search engine.
3. **Fetches of a set's addresses read the file.** `fetch_page` on one of the set's addresses returns the page from the file. Any other address is fetched as usual, so a model that obeys an injected "fetch this address" is visible in the log. In the benchmark that address is a reserved name that cannot resolve (`.invalid`).

Each set is one YAML file: a list of pages, each with an address, a title, a snippet and the page's text.

The product's server never has the route. It exists only when `WEB_SEARCH_FIXTURES_DIR` is set, which only the benchmark does, and the benchmark's server listens on `127.0.0.1`.

### 3.4 Sports statistics (M7)

Planned from v2/00: NFL statistics from nflreadpy and NBA statistics from nba_api, with balldontlie as the NBA backup. Not Sports Reference, whose terms forbid automated access. The tools' names, arguments, caches and failure sentences are designed in M7, which updates this section and adds category J to doc 01.

### 3.5 The Reddit reader (M11)

Reddit threads will be read by their own reader, as Wikipedia is, through the quarantined reader (doc 12 §3.6) and with the agent account's session kept out of the general page fetcher. Designed in doc 13.

## 4. Packages and tools, and what each does for the business logic

| Package or service | Role |
|---|---|
| Open-Meteo geocoding API | Turns a spoken place name into coordinates and a time zone. Free, no key |
| `diskcache` | Already used for search results; holds the place lookups permanently |
| `httpx`, `zoneinfo`, `pydantic` | As in v1's weather tool |

No package is added.

## 5. Configuration we control

| Setting | Where | Value |
|---|---|---|
| Geocoding address | `weather_mcp/settings.py` | `https://geocoding-api.open-meteo.com/v1/search` |
| Places held in memory | `weather_mcp/settings.py` | 32 forecasts |
| Place cache | The tool server's cache directory | Permanent, keyed by the lower-cased spoken name |
| Fixture pages | `WEB_SEARCH_FIXTURES_DIR`, set only by the benchmark | `benchmark/fixtures/pages/` |
| Tool tiers | `config/tools.toml`, read by the harness | The table in 3.1 |

## 6. Failure modes

| Failure | What happens | What to do |
|---|---|---|
| The place is misheard | No match, and the model asks for the place again | Say it again, with its country |
| The wrong place of that name is chosen | The heading names the wrong country, and the answer says so | Say the region or country after the name |
| Open-Meteo is down | New places fail with a sentence; cached places and home still work | Nothing |
| Met.no is down for a place | As for home: a held forecast is served, or the error sentence | Nothing |
| A fixture route in the product | Not possible: the product's launchd agent never sets `WEB_SEARCH_FIXTURES_DIR` | |

## 7. Concepts for newcomers

**Geocoding.** Turning a place name into coordinates. A gazetteer is the list of names it searches.

**Fixture.** Prepared data a test uses instead of the live service, so every run sees the same input.

**Tier.** The class of power a tool has: computing locally, reading public data, reading private data, or acting. The harness decides what an exchange may combine from the tiers (doc 12 §3.3).

## 8. Sources

- Open-Meteo geocoding API: [open-meteo.com/en/docs/geocoding-api](https://open-meteo.com/en/docs/geocoding-api), and its terms: [open-meteo.com/en/terms](https://open-meteo.com/en/terms)
- Met.no Locationforecast terms: [api.met.no/doc/TermsOfService](https://api.met.no/doc/TermsOfService)
- Reserved names that never resolve (`.invalid`): RFC 2606
