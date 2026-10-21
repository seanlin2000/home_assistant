# 03. Tool server

Status: designed 2026-10-08

## 1. Purpose

The tools the assistant can call, and what v2 changes about them. The tool server is still one MCP server, `assistant-tools`, with the search, page-reading, Wikipedia, calculator and weather tools of v1. v2 changes four things:
- **Weather anywhere.** The forecast tool takes an optional place, so "will it rain in Lisbon on Saturday?" gets a forecast instead of a web search (M4).
- **A tier for every tool.** Each tool has a tier and a trust setting, which the harness enforces (doc 12 §3.3). The table is in 3.1.
- **Fixture search for the benchmark.** The benchmark's own copy of the server can return prepared pages instead of live results, so the injection questions are the same on every run (M3, doc 01 §3.3).
- **Sports.** Four tools answer NBA and NFL scores, rosters and statistics from ESPN, so a question like "Brady's record against Manning" gets exact numbers instead of a web search (M7, 3.4).
- **Reddit, later.** Its section is a placeholder, filled in by M11.

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
| `game_scores`, `team_roster`, `player_stats`, `player_matchup` | Read public | No: numbers, and names reduced to letters | Team and player names, dates and seasons, to ESPN | M7 |
| The Reddit reader | Read public | Yes, and through the quarantined reader (doc 12 §3.6) | The thread's address, to Reddit | M11 |

A tool marks the exchange untrusted when its text is written by strangers. A forecast is numbers from Met.no, and a place name comes from Open-Meteo's gazetteer, so neither can carry an instruction worth worrying about. The sports tools return numbers and names from ESPN's database, and each name is cut down to letters and a few punctuation marks before it leaves the tool (3.4).

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

Four tools answer the three kinds of sports question asked at home: scores, today's and past ones; a team's current roster; and a player's statistics over time, including against another player. They cover the NBA and the NFL. Each returns a short table that code has already added up, so the model only reads numbers out. It never does the arithmetic or picks between disagreeing web pages, which is where web search failed: asked for the Warriors roster, the model named five players and said it had found no full list, although one page it read had all eighteen.

**The source is ESPN's public JSON, for both leagues.** These are the addresses espn.com and its app read from. They need no key, and every one below was tried from the apartment on 2026-10-20:

| Address | Gives |
|---|---|
| `site.api.espn.com/apis/site/v2/sports/{league}/scoreboard?dates=YYYYMMDD` | Every game on a day, live or past, back to the 1980s: status, score, period and clock, series note, each team's leader |
| `site.api.espn.com/apis/site/v2/sports/{league}/teams/{id}/schedule?season=&seasontype=` | A team's games in a season, regular or playoffs |
| `site.api.espn.com/apis/site/v2/sports/{league}/teams/{id}/roster` | The current roster |
| `site.web.api.espn.com/apis/search/v2?query=` | A player's name to ESPN's id |
| `site.web.api.espn.com/apis/common/v3/sports/{league}/athletes/{id}/stats` | A player's regular-season averages and totals for every season |
| `site.web.api.espn.com/apis/common/v3/sports/{league}/athletes/{id}/gamelog?season=` | Every game of one season, playoffs included, with the result and the stat line |

`{league}` is `basketball/nba` or `football/nfl`.

The sources v2/00 planned do not work here:
- **stats.nba.com and cdn.nba.com** (behind `nba_api`) refuse the apartment's address: a 403 from cdn.nba.com, and no answer at all from stats.nba.com even with browser headers.
- **balldontlie's** free tier has teams and games but no player statistics; those start at $10 a month per sport.
- **Sports Reference's** terms forbid using its data to prompt an AI model.
- **nflverse** works and is openly licensed, but it covers only the NFL. A second source, with its own downloader and database, buys nothing ESPN does not already give. It stays the fallback for NFL history if ESPN ever closes.

ESPN's feed is unofficial: it is undocumented, can change without notice, and Disney's terms of use forbid automated access and AI prompting. We accept that risk for a household assistant that asks a few dozen questions a day. Many hobby projects read the same feed, including Home Assistant's Team Tracker integration. When ESPN does not answer, the tools say so and the model searches the web instead.

**The four tools.** One per kind of question, so a small model picks the right one. Every tool takes `league`, either `nba` or `nfl`.

| Tool | Arguments | What it returns |
|---|---|---|
| `game_scores` | `team` (optional), `date` (optional, `YYYY-MM-DD`), `season` (optional), `playoffs` (optional, `true` or `false`) | **A team alone:** its last finished game, and a live or next game if there is one. **A date:** that day's games, only the team's if one is named. **A season:** the team's games that season, only the playoffs if asked. Each game is one line: status, score, period and clock when live, the series note in the playoffs ("NBA Finals, Game 7"), and each team's top scorer |
| `team_roster` | `team` | One line per player: number, name, position. NFL rosters are grouped into offense, defense and special teams, with injured players listed apart and the practice squad left out |
| `player_stats` | `player`, `from_season` and `to_season` (optional) | One row per regular season, then a career row. NBA columns: team, games, points, rebounds, assists, three-pointers made and attempted, field-goal percentage. NFL: the passing, rushing and receiving columns the player has numbers in |
| `player_matchup` | `player`, and either `opponent_player` or `opponent_team` | A summary line first: games, the player's wins and losses, split into regular season and playoffs. Then one line per game, newest first, with the date, score, result and both players' stat lines |

The argument rules:
- `team` is a city, nickname or abbreviation as spoken: `Warriors`, `Golden State`, `GSW`. At most 40 characters.
- `player` and `opponent_player` are a name as spoken. At most 60 characters.
- `date` must match `YYYY-MM-DD`. The model works it out from today's date in the per-question note: "last Monday" becomes a date before the call.
- A season is the year it started: 2015 means the NBA's 2015-16 season, or the NFL's 2015 season. ESPN names NBA seasons by the year they end, so the tool converts. Seasons run from 1980 to next year.

**How a matchup is worked out.** For "Tom Brady against Peyton Manning", `player_matchup` does this:
1. **Finds both players.** ESPN's search turns each name into an id, keeping only the asked league's players.
2. **Finds the seasons they shared.** Each player's season list comes from the stats address. Brady played 2000 to 2022 and Manning 1998 to 2015, missing 2011, so they shared fifteen seasons.
3. **Reads both game logs for those seasons,** up to four at a time.
4. **Keeps the games both appear in,** matched by ESPN's game id. A game one of them missed, such as Manning's injured 2015 week 12, is not in his log, so it drops out by itself.
5. **Adds up the record** from the first player's result in each game.

From the apartment, with nothing cached, this took 1.2 s and 34 requests for Brady and Manning (17 games, Brady 11 and 6), and 0.5 s and 38 requests for Stephen Curry and LeBron James (69 games, Curry 38 and 31). Against a team, only the player's own logs are read and kept where the opponent is that team.

**Results are short, and the heading names what was found.**
- The first line names the league and the team or player found, as the forecast names its place: `NFL: Tom Brady against Peyton Manning, 17 games, 2001 to 2015`. When the name was misheard, the answer can say who it found, and the benchmark checks the heading (doc 01 §3.3).
- Tables use one `a | b` row per line, and a result is clipped to 600 words, about 800 tokens, well inside a tool result's allowance (doc 04). A clipped result says how many games were left out.
- Numbers come straight from ESPN. The tool computes only counts, sums and averages, so the answer never depends on the model's arithmetic.

**Names are cut down before they leave the tool.** A player or team name in a result keeps only letters, spaces, digits and `.'-`, and at most 40 characters. A name in ESPN's database is not text a stranger can write freely, and this makes sure that even a tampered one cannot carry an instruction. So these tools, like the forecast, do not mark the exchange untrusted (doc 12 §3.7).

**What is cached, and for how long.** Unlike the other tools, sports keeps a cache in the product, in `~/Library/Caches/studio-assistant/sports`. Most of what it reads never changes, and a matchup reads dozens of game logs. The cache holds the parsed rows, not ESPN's JSON, which runs to 25 MB for one NBA matchup.

| What | Kept for |
|---|---|
| A player's id, a past day's scores, a finished season's stats and game logs | For good |
| Today's scores and any game in progress | 30 seconds |
| The current season's stats, game logs and schedules | 1 hour |
| Rosters | 12 hours |

The benchmark points the cache at its run's folder, as it does for search.

**Failure sentences.** The model can repeat each one:
- "Sports error: no NBA player called Steph Cury was found. Ask the user to say the name again."
- "Sports error: no NFL team called the Sonics was found. Ask the user which team they mean."
- "Sports error: Stephen Curry and Tom Brady never played in the same league."
- "Sports error: Tom Brady and Michael Jordan never played each other."
- "Sports error: ESPN did not answer. Search the web with search_and_read instead."

What changes around the tools:
- **The router.** It gains a `sports` family. A rule sends a question to it when it names a league, an NBA or NFL team, or a sports word ("score", "roster", "stats", "versus", "record against"), and the model router learns the family from its examples. When the sports tools are not offered, the route falls back to search, as weather does.
- **The system prompt.** A "Sports" section sends NBA and NFL scores, rosters and statistics to these tools, and tells the model to pass dates as `YYYY-MM-DD`. The Wikipedia rule stops claiming "a team's past players or seasons": Wikipedia keeps other leagues and history from before ESPN's records. And when the user asks for a list, every season or every player, the answer says each item in a compact spoken form, up to about 25. The one-to-three-sentence rule had cut the Warriors roster to five names.
- **The filler line.** "Let me check the numbers."

ESPN's terms, and how the tools behave toward ESPN:

| Term | How the tools behave |
|---|---|
| No published rate limit; automated access and AI use forbidden by Disney's terms | Read only when asked, at most four requests at a time, cached as above. A typical day is under a hundred requests |
| Unofficial, can change without notice | Every field is read defensively; a missing one gives the "ESPN did not answer" sentence, not a crash |

Privacy:
- ESPN sees the team and player names, dates and seasons asked about, and the apartment's IP address.
- ESPN never sees the question.
- Every argument passes the egress guard (doc 12 §3.4), so a name from memory that you did not say is never sent.

Doc 12's checklist for a new tool (§3.12):

| Item | Answer |
|---|---|
| Tier and trust mark | Read public; does not mark the exchange untrusted |
| Quarantined reader | No: the result is numbers and cut-down names |
| Argument schema | `league` from two values; `team` at most 40 characters; names at most 60; `date` a pattern; seasons whole numbers from 1980 to next year; `playoffs` true or false |
| What leaves the house | Names, dates and seasons, to ESPN; the egress guard sees each |
| Credentials | None |
| Terms and rate limits | The table above |
| Benchmark questions | Category J (doc 01 §3.3), including a name that carries an instruction |
| Failure sentences | Listed above |

### 3.5 The Reddit reader (M11)

Reddit threads will be read by their own reader, as Wikipedia is, through the quarantined reader (doc 12 §3.6) and with the agent account's session kept out of the general page fetcher. Designed in doc 13.

## 4. Packages and tools, and what each does for the business logic

| Package or service | Role |
|---|---|
| Open-Meteo geocoding API | Turns a spoken place name into coordinates and a time zone. Free, no key |
| ESPN's site and common APIs | Scores, schedules, rosters, player search, season statistics and game logs for the NBA and NFL. Free, no key, unofficial |
| `diskcache` | Already used for search results; holds the place lookups permanently, and the sports rows for as long as 3.4 says |
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
| Sports cache | `SPORTS_CACHE_DIR` | `~/Library/Caches/studio-assistant/sports`; the benchmark's run folder in a run |
| Sports fixtures | `SPORTS_FIXTURES_DIR`, set only by the benchmark | `benchmark/fixtures/sports/` |
| ESPN requests at a time | `sports_mcp/settings.py` | 4 |

## 6. Failure modes

| Failure | What happens | What to do |
|---|---|---|
| The place is misheard | No match, and the model asks for the place again | Say it again, with its country |
| The wrong place of that name is chosen | The heading names the wrong country, and the answer says so | Say the region or country after the name |
| Open-Meteo is down | New places fail with a sentence; cached places and home still work | Nothing |
| Met.no is down for a place | As for home: a held forecast is served, or the error sentence | Nothing |
| A fixture route in the product | Not possible: the product's launchd agent never sets `WEB_SEARCH_FIXTURES_DIR` | |
| A player's name is misheard | No player found, and the model asks for the name again; or the heading names someone else, and the answer says who | Say the full name |
| ESPN is down, blocks the apartment, or changes its JSON | The tools say ESPN did not answer, and the model searches the web; cached rows still answer | If it lasts, NFL history can move to nflverse |

## 7. Concepts for newcomers

**Geocoding.** Turning a place name into coordinates. A gazetteer is the list of names it searches.

**Fixture.** Prepared data a test uses instead of the live service, so every run sees the same input.

**Game log.** Every game a player played in one season, one line each, with the result and the stat line.

**Tier.** The class of power a tool has: computing locally, reading public data, reading private data, or acting. The harness decides what an exchange may combine from the tiers (doc 12 §3.3).

## 8. Sources

- Open-Meteo geocoding API: [open-meteo.com/en/docs/geocoding-api](https://open-meteo.com/en/docs/geocoding-api), and its terms: [open-meteo.com/en/terms](https://open-meteo.com/en/terms)
- Met.no Locationforecast terms: [api.met.no/doc/TermsOfService](https://api.met.no/doc/TermsOfService)
- Reserved names that never resolve (`.invalid`): RFC 2606
- Disney's terms of use, which cover ESPN: [disneytermsofuse.com/english](https://disneytermsofuse.com/english/)
- Home Assistant's Team Tracker, which reads the same ESPN feed: [github.com/vasqued2/ha-teamtracker](https://github.com/vasqued2/ha-teamtracker)
- Sports Reference terms of use: [sports-reference.com/termsofuse.html](https://www.sports-reference.com/termsofuse.html)
- balldontlie's plans: [balldontlie.io](https://www.balldontlie.io/)
- nflverse, the NFL fallback: [github.com/nflverse/nflverse-data](https://github.com/nflverse/nflverse-data)
