# 03. Web search MCP server

## 1. Purpose

Give the language model Google-quality web results without an API key, an account, or a per-query fee, and hand it readable page text rather than ten-word snippets so it can synthesize an answer. Two parts: SearXNG, a self-hosted search aggregator running in Docker, and a small Python MCP server we write that turns a question into a compact block of grounded excerpts. The server is the only bespoke service in the system and the same one the benchmark and the product use.

## 2. Diagram

```
  model emits tool call                    web_search_mcp (ours, Python, runs from .venv)
  search_and_read(                         ┌────────────────────────────────────────────────────┐
    query="current fed funds rate")        │ server.py        FastMCP over streamable HTTP        │
          │                                │   tools: search_and_read, web_search, fetch_page    │
          ▼                                │                                                    │
  ┌──────────────┐   MCP (HTTP, JSON)      │ searxng_client.py                                  │
  │ agent loop   │────────────────────────▶│   GET http://localhost:8080/search                  │
  │ (MCP client) │                         │       ?q=...&format=json&language=en&safesearch=0  │
  └──────────────┘                         │   → ranked results: title, url, snippet, engines    │
          ▲                                │                                                    │
          │                                │ page_extractor.py                                  │
          │  grounded excerpts             │   fetch top N urls concurrently (httpx, timeouts)   │
          │  [1] title, url, 600-word text │   trafilatura extracts main text, drops nav/ads     │
          │  [2] ...                       │   cap words, dedupe, keep url for attribution       │
          └────────────────────────────────│                                                    │
                                           └───────────────┬────────────────────────────────────┘
                                                           │
                                            ┌──────────────▼──────────────┐
                                            │ SearXNG (Docker, localhost) │
                                            │  settings.yml: json output, │
                                            │  engines google, bing,      │
                                            │  brave, duckduckgo          │
                                            └──────────────┬──────────────┘
                                                           │ plain HTTPS, no cookies, no account
                                                           ▼
                                             Google   Bing   Brave   DuckDuckGo
```

## 3. How it works, step by step

1. The model decides it needs current information and emits a tool call, usually `search_and_read(query)`. The agent loop forwards it over MCP to our server.
2. `searxng_client` issues one GET to the local SearXNG instance with `format=json`. SearXNG fans the query out to the configured engines in parallel, merges and re-ranks the results, and returns a JSON list with title, URL, snippet, and which engines returned it. Results that several engines agree on rank higher.
3. `page_extractor` fetches the top N URLs concurrently with short timeouts, skipping PDFs and known paywalls. `trafilatura` pulls the main article text out of each page and drops navigation, ads, and boilerplate.
4. The server assembles a compact block: every result keeps its search rank and number; a page that was read carries its URL and up to 350 words of the passages that best match the query, and one that could not be read carries its title and snippet. A total word budget caps the block so the prompt does not balloon, and a closing line tells the model to say plainly when the sources do not answer. This block is the tool result (§16).
5. The model reads the block and writes the answer, citing source numbers in its reasoning if asked (the spoken answer itself omits URLs).
6. During a benchmark run, SearXNG responses are cached by query string so every candidate model that issues the same query sees the same pages.

The two lower-level tools exist for flexibility: `web_search` returns only the ranked list with snippets, and `fetch_page` returns one page's text. A capable model can chain them; small models do better with the single `search_and_read`.

## 4. Why this design

- **SearXNG rather than a search API.** Google has no general-purpose search API for this use. Brave dropped its free tier in February 2026 and now bills $5 per thousand queries against a required card. SearXNG aggregates the major engines' results for free, with no account, so the engines see a query and an IP address but nothing tied to you. Result quality is the engines' own.
- **Fetch full pages rather than trust snippets.** Snippets are ten to thirty words chosen for a human skimming a results page. A model answering "why did GPU prices rise" needs paragraphs. Extraction is what turns search into grounding.
- **MCP rather than a private function.** The protocol costs a few lines and buys reuse: the benchmark, the Home Assistant agent, Claude Desktop, and Claude Code can all call the same server. It also matches the web-grounding MCP you use at work.
- **Streamable HTTP transport.** The current MCP transport. Home Assistant's built-in MCP client only speaks the older SSE transport, but our agent is the client, so that limitation does not apply.

## 5. Packages and what they do for us

| Package | Role in the business logic |
|---|---|
| SearXNG (Docker image `searxng/searxng`) | The search aggregator. Does the fan-out, merging, and ranking across engines. Configured with JSON output enabled and four engines. |
| `mcp` (FastMCP server) | Declares the three tools from typed Python functions, generates their JSON schemas, serves them over streamable HTTP. The schemas are what the model reads to decide how to call the tool. |
| `httpx` | Async HTTP client for the SearXNG request and the concurrent page fetches. Explicit connect and read timeouts keep one slow site from stalling the answer. |
| `trafilatura` | Main-content extraction from HTML. Turns a cluttered page into the article text. Chosen for extraction quality across news, docs, and forum pages and for having no browser dependency. |
| `pydantic` | Typed models for `SearchResult`, `PageExcerpt`, and the assembled `GroundedContext`, so the tool result has a fixed shape the agent and the benchmark can rely on. |
| `diskcache` | The per-run query cache used by the benchmark for fairness. Off in production. |
| `uvicorn` | ASGI server that FastMCP runs on. |

## 6. Configuration we control

- `docker/searxng/settings.yml`: engines (google, bing, brave, duckduckgo), `search.formats: [html, json]`, safe search, language `en`, request timeouts.
- `docker/searxng/docker-compose.yml`: image tag pinned, port bound to localhost only.
- Server settings: top N pages to fetch (default 4), words per page (600), total word budget (2,000), fetch timeout (6 s), blocked domains (paywalls, social networks), user agent.
- Cache on or off, and its directory.

## 7. Failure modes

- **An engine blocks SearXNG.** Google intermittently serves CAPTCHAs to aggregators. SearXNG marks the engine as suspended for a while and the other three carry the query. Persistent trouble across all engines is the trigger to add Brave's paid API as a fallback engine.
- **Top pages are paywalled, JavaScript-only, or huge.** Extraction returns little or nothing. The server skips empty extractions and moves to the next result, and reports how many sources it actually read so the model can say when evidence is thin.
- **A slow site.** Per-fetch timeout; the block is assembled from whatever returned in time.
- **Query too vague.** The model wrote a poor search string. Visible in the benchmark transcripts; addressed with tool-description wording in the shared system prompt, not with server logic.
- **Prompt bloat.** Word budgets cap the block. A larger context would help a strong model but slows time to first token on the Mac.

## 8. Concepts for newcomers

**MCP (Model Context Protocol).** A standard for exposing tools, data, and prompts to a language model application over a network. A server declares tools with a name, a description, and a JSON schema for their parameters. A client lists those tools, shows them to the model, and calls them when the model asks. FastMCP is the Python helper that turns a decorated function into such a tool.

**Tool schema.** The JSON description of a tool's parameters. The model reads the description text to decide when to call the tool and reads the schema to produce valid arguments. Tool descriptions are prompt engineering.

**Grounding.** Giving the model retrieved text to base its answer on, so that it summarizes evidence rather than recalling from training. Reduces fabrication for current facts.

**Metasearch.** A search engine that queries other search engines and merges their results rather than crawling the web itself. SearXNG is one.

**Main-content extraction.** Turning a web page into the text a human came for. Pages are mostly navigation, ads, scripts, and legal text by byte count.

**Streamable HTTP versus SSE.** Two transports in MCP's history. SSE (server-sent events) was the original remote transport; streamable HTTP replaced it in 2025 with a simpler, stateless design. Home Assistant's own MCP client is still on SSE, which is one reason our agent, not Home Assistant, is the MCP client.

## 9. Sources

- Brave Search API free tier removed, February 2026: [implicator.ai](https://www.implicator.ai/brave-drops-free-search-api-tier-puts-all-developers-on-metered-billing/), [agentdeals.dev](https://agentdeals.dev/vendor/brave-search-api)
- Home Assistant MCP client supports only SSE: [github.com/orgs/home-assistant/discussions/1383](https://github.com/orgs/home-assistant/discussions/1383)
- Home Assistant MCP integration docs: [home-assistant.io/integrations/mcp](https://www.home-assistant.io/integrations/mcp/)
- SearXNG documentation: [docs.searxng.org](https://docs.searxng.org/)
- MCP Python SDK: [github.com/modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk)
- trafilatura: [trafilatura.readthedocs.io](https://trafilatura.readthedocs.io/)

## 10. As built, 2026-09-05

- The `mcp` package is at major version 2 (2.1.1, on Python 3.12). The server is `mcp.server.mcpserver.MCPServer`, run with `server.run(transport="streamable-http", host=..., port=...)`, endpoint `/mcp`. The client is `mcp.client.client.Client`, which accepts either a URL or an in-process server object; tests use the latter.
- Modules: `settings.py` (defaults overridable by `WEB_SEARCH_*` environment variables), `searxng_client.py`, `page_extractor.py`, `query_cache.py` (diskcache, on only when a cache directory is given), `server.py`.
- Defaults: 6 pages read, 350 words per page (the passages that best match the query, §16; 4 pages of 600 words from the top until 2026-10-07), 2,000 words total, 6 s fetch timeout, social networks and hard paywalls skipped, tables kept during extraction because rate and price pages keep their numbers in tables.
- Measured on the prototype: a `search_and_read` call against live SearXNG took about 7 s and returned about 2,000 words from 4 of 28 results; a cached repeat returned instantly with identical text.
- SearXNG runs from `docker/searxng/docker-compose.yml` with `scripts/searxng.sh up|down|status|logs`; the secret is generated into `docker/searxng/.env`, which git ignores. Google, Brave, and DuckDuckGo all returned results on the first day; Bing is configured but was not observed in the first samples.

## 11. Calculator tools, added 2026-09-06

The same MCP server now also publishes eight calculator tools from the `calculator_mcp` package. The motivation is benchmark question A2 (a lease with a 5 percent rise versus two 3 percent rises): every local model set the problem up correctly and then got the digits wrong, because a language model predicts the next token and does not carry. A calculator turns the arithmetic into a lookup the model only has to describe.

```
  model (Ollama)                     MCP server, one process, one port 8765
  ┌─────────────────────┐  tools/list  ┌──────────────────────────────────────────┐
  │ sees 11 tool schemas│◀────────────│ web_search_mcp.server.build_server        │
  │ system prompt says: │             │   search_and_read / web_search / fetch_page│──▶ SearXNG
  │ "never do multi-step│  tools/call │   register_calculator_tools(server)        │
  │  arithmetic yourself│────────────▶│     calculate  percent  convert            │
  └─────────────────────┘             │     growth_schedule  energy_cost           │
        ▲  tool result:               │     loan_payment  break_even  date_math    │──▶ calculator_mcp.functions (pure Python)
        │  "result: 87,817.80         └──────────────────────────────────────────┘
        │   spoken: starting from 3,500 ... cumulative total is 87,817.80
        │   schedule: period 1: 3,605 each, 43,260 for the period ..."
```

**How the model decides to call one.** There is no router. The MCP server publishes each tool's name, description, and JSON argument schema; the agent loop copies that list into every chat request; the model reads it like any other text and, at each step, either writes prose or emits a structured tool call. The description is therefore the routing rule, so each one says when to use it ("for any calculation with more than one step and always for money"), and the system prompt repeats the rule in its own words. Ollama's chat API has no way to force a tool call, so the decision is always the model's.

**Design rules for the functions** (`calculator_mcp/functions.py`):

- `calculate(expression)` evaluates a whitelisted Python AST: numbers, `+ - * / // % **`, parentheses, percent literals like `15%`, thousands separators and `$` signs, and `round sqrt abs min max log exp floor ceil`. Anything else (names, attribute access, calls outside the list, huge exponents, division by zero) raises a `CalculatorError` whose message tells the model what is allowed. It is never `eval`.
- The other tools are shaped for spoken questions: `percent(kind, a, b)`, `convert(value, from_unit, to_unit)` over a fixed unit table (temperature handled as an affine conversion), `growth_schedule` (compounding laid out period by period), `energy_cost` (watts, hours a day, price per kilowatt hour, idle watts), `loan_payment`, `break_even`, and `date_math`.
- Every tool returns the exact number first and a spoken sentence second; rounding happens only in the sentence. Errors return as text starting with `Calculator error:` so a model can correct its arguments and try again instead of the loop failing.
- No currency conversion (needs live rates, so it belongs to search) and no statistics (no data source).

**Benchmark bookkeeping.** `QuestionResult.searched` in `benchmark/records.py` now counts only the three search tools, so a calculator call on a Category A question does not trip the "searched on a no-search question" gate. The system prompt is version 1.2 and `run_meta.json` records the prompt version, because results under 1.1 and 1.2 are not directly comparable.

## 12. Fetch safety, added 2026-09-06

The model picks the URLs that `fetch_page` reads, and a web page can tell the model which URL to pick. That is prompt injection, and it cannot be prevented at the model; what can be bounded is what an obeyed instruction reaches. Two limits were added to the fetch path in `web_search_mcp/page_extractor.py` and `web_search_mcp/url_guard.py`:

```
  fetch_page(url) / search results
        │
        ▼
  ensure_public_url(url)          scheme must be http or https
        │                         host must not be localhost, *.local, *.internal, *.lan, *.home, *.arpa
        │                         host is resolved; every address must be globally routable
        │                         (no 10/8, 172.16/12, 192.168/16, 127/8, 169.254/16, ::1, fe80::/10, IPv4-mapped IPv6, multicast)
        ▼
  GET without automatic redirects
        │  3xx ─▶ resolve the Location header ─▶ back to ensure_public_url (at most 5 hops)
        ▼
  stream the body; stop past max_page_bytes (2 MB) or a larger declared content-length
        ▼
  trafilatura.extract ─▶ text only; no JavaScript runs, nothing is written except the text cache
```

- A refused address raises `UnsafeUrl`. `fetch_page` returns a sentence saying the fetch was refused, so the model can tell the user rather than retry; `search_and_read` silently skips that result and reads the next one.
- The resolver and the HTTP transport are injectable, which is how the tests pretend a public-looking name resolves to the router and serve redirects without opening sockets.
- Closed on 2026-09-07 (was "residual risk, accepted"): a hostile DNS server could answer the check with a public address and the connection a moment later with a private one (DNS rebinding), because the HTTP client resolved the name a second time. Now `ensure_public_url` returns the addresses it approved and `_download` connects to the first of them: the URL sent to the client carries the address, the real name travels in the `Host` header and, for https, in the TLS handshake (`sni_hostname`), so certificate verification still checks the real name. After the connection is up, the peer address reported by the socket is checked once more, so a transport that resolved on its own is caught too.
- The server side of the same idea: when the tool server is bound to the LAN (`WEB_SEARCH_HOST=0.0.0.0`) it answers only requests whose `Host` header names this machine (`WEB_SEARCH_ALLOWED_HOSTS`, written by `services.sh`) and none that carry a browser `Origin`, on the MCP endpoint and on `/exchanges` and `/healthz` alike; anything else gets 421. A web page open in a browser on the LAN can therefore not be used to reach the server through DNS rebinding. The library already does this for localhost binds; the benchmark and the tests bind localhost and set no list.

The broader rule for the product stays: never give the model a tool that acts on the home without an intent or confirmation layer in front of it, and treat anything derived from a web page as data, never as an instruction.

## 13. As built, 2026-09-06: engine rate limits

A day of benchmark passes, each firing dozens of searches within an hour, got the Mac's address throttled by every engine behind SearXNG at the same time: Brave answered "too many requests", DuckDuckGo demanded a CAPTCHA, Bing refused the connection, and Google returned empty pages while still answering a plain browser request from the same machine. The search tool then returned "No search results" and told the model to say so, which the harness records; the affected candidates were set aside and rerun later. Two changes came out of it: `SearxngClient` now waits a minimum gap between live requests (default 3 s; cached queries never wait), and the benchmark's search cache is kept per pass so a rerun of the same pass does not re-hit the engines. If Google stays blocked, the design's fallback of a Brave Search API key still applies.

The block did not lift on its own. A day later, with the container restarted so that SearXNG's in-process engine suspensions were cleared, each engine was probed from inside the container: Google now returns a page that says JavaScript is required (SearXNG issues #5286 and #5827 track the broken Google engine), Brave still answers 429, DuckDuckGo answers a CAPTCHA challenge, and SearXNG 2026.9.5's Bing engine drops the connection even though bing.com itself answers from the same container. Community guidance (SearXNG issues #2498, #2287, #1628 and the "searxng engine selection" note at conselara.dev) is to space queries at least three seconds apart, keep a session under about twenty queries, and enable engines beyond the big four. So `docker/searxng/settings.yml` now also keeps Startpage, Yahoo, and Wikipedia. Startpage (which serves Google's index) and Yahoo (which serves Bing's) answered at once with ten and seven results. Mojeek and Qwant, two smaller independent engines, were tried the same day, returned nothing for the probe query, and were dropped: they are not engines the user knows or wants results from. Benchmark pass 4 onward therefore searches through Startpage and Yahoo, where passes 1 to 3 searched Google, Bing, Brave, and DuckDuckGo. Within one pass every candidate sees the same engines, which is the fairness rule that matters; across passes, search results were never identical anyway because the web moves.

## 14. Weather tool, added 2026-09-30

The same MCP server now also offers `weather_forecast`, from the `weather_mcp` package, which reads the forecast for home straight from Met.no, the Norwegian Meteorological Institute's free forecast service. Before it, "what's the weather" was answered by Home Assistant's built-in weather intent, which reads only the current state of the Met.no entity: it could say "18 degrees and cloudy", but "do I need an umbrella tomorrow afternoon" or "what's the weekend like" fell through to the agent, which searched the web for it (slow, noisy, and sometimes the wrong town) or guessed. Home Assistant now hands every weather question to the agent (doc 06 §12), and the agent answers from this tool (doc 04 §16).

```
  model (Ollama)                                  weather_mcp, on the same MCP server (port 8765)
  ┌────────────────────────────┐   tools/call     ┌──────────────────────────────────────────────────┐
  │ weather_forecast(          │─────────────────▶│ MetnoClient.forecast()                           │
  │   day="tomorrow",          │                  │   1. pinned in the benchmark run cache?  use it  │
  │   part_of_day="afternoon") │                  │   2. held, and before its Expires time?  use it  │
  └────────────────────────────┘                  │   3. otherwise GET with If-Modified-Since ───────┼──▶ api.met.no
                ▲                                 │      (if the GET fails, keep the held copy)      │    /locationforecast/2.0/complete
                │ tool result, text:              │                                                  │    ?lat=..&lon=.. (4 decimals)
                │ "Home weather forecast for      │ ForecastReader                                   │    User-Agent:
                │  tomorrow, Thursday October 1:  │   UTC time steps → local days, parts of day      │    studio-assistant-weather/1.0
                │  afternoon (noon to 6 pm):      │   symbol codes   → plain words ("light rain")    │    github.com/seanlin2000/home_assistant
                │  59 to 64°F, partly cloudy,     │   units          → °F, in, mph or °C, mm, km/h   │
                │  dry, wind up to 9 mph"         │                                                  │
                └─────────────────────────────────┤                                                  │
                                                  └──────────────────────────────────────────────────┘
```

**What the tool takes and returns.**

- Two arguments, both plain words. `day` is `today`, `tomorrow`, a weekday such as `saturday`, `weekend`, or `week` (the next seven days). `part_of_day` is `morning` (6 am to noon), `afternoon` (noon to 6 pm), `evening` (6 pm to midnight), `night` (midnight to 6 am after that day's evening), or `all`.
- There is no place argument. The tool only knows home, so the model cannot send it another town's name, and the coordinates never appear in the conversation. Weather anywhere else is still a web search.
- The result is a few lines of text: a heading naming the date, then one line per part of the day, or one line per day for `weekend` and `week`. Each line gives the temperature range, the usual sky with the wettest precipitation added ("cloudy with light rain at times"), the total precipitation, the chance of precipitation where Met.no provides one, and, for a part of the day, the strongest wind.
- `today` starts with a "now" line and leaves out the parts of the day that have passed. Asked after midnight, tonight is the night already in progress, labelled "overnight". A day past the end of the forecast gets a sentence saying how far the forecast reaches, never a guess.
- Mistakes come back as sentences the model can act on: an unknown `day` or `part_of_day` names the allowed values, and an unreachable Met.no, with no earlier copy held, returns "Weather error: the forecast service did not answer. Tell the user you could not get the forecast right now."

**How Met.no's document becomes those lines.** The document is a time series in UTC. Each row (a "time step") holds an instant reading (temperature, wind) and summaries of the next one and six hours (a weather symbol such as `lightrainshowers_day`, the precipitation amount, and the six-hour minimum and maximum temperature). Rows are hourly for about two and a half days and six-hourly after that, out to about ten days. `ForecastReader` works like a group-by on a local-time key:

1. Each row becomes a block: one hour long while the next row is an hour later, six hours long after that, so blocks never overlap. The last rows carry no summary and are dropped.
2. Each block goes to the local day and part of the day that contain its midpoint, in the home time zone. Grouping in local time, not UTC, is the point: a New York afternoon in summer is 16:00 to 22:00 UTC.
3. Each group is reduced: minimum and maximum temperature, total precipitation, highest chance of precipitation, strongest wind, and the most common symbol, turned into words from Met.no's symbol legend (`fair` reads as "mostly clear").
4. Numbers are converted to the units Home Assistant uses (°F, inches, mph, or °C, millimetres, km/h) and rounded for speech.

The time zone and units come from Home Assistant through `.env`, like the coordinates (doc 06 §12). The time zone is an IANA name such as `America/New_York`, not a fixed offset, so a daylight-saving change inside the forecast week lands on the right hour.

**Why the `complete` product and not `compact`.** Locationforecast offers both. `compact` has no minimum and maximum temperature per six-hour block and no chance of precipitation. `complete` has the six-hour minimum and maximum everywhere, and the chance of precipitation only in the Nordic area: present for Oslo, absent for London and Chicago when checked on 2026-09-30. So for a home in the United States the lines give the amount and leave the chance out, and the tool never makes one up.

**Met.no's terms of service, and how the client meets them** (`weather_mcp/metno_client.py`):

| Term | How it is met |
|---|---|
| Identify the application and a way to contact its owner in the User-Agent | `studio-assistant-weather/1.0 github.com/seanlin2000/home_assistant`: the repository is the contact, so no email address or other personal detail is sent |
| At most four decimals in the coordinates (five or more gets 403) | Coordinates are sent rounded to four decimals |
| Keep a response until its `Expires` time instead of asking again | The client holds the last forecast in memory and serves it until `Expires` |
| After that, ask with `If-Modified-Since` | The request carries the `Last-Modified` value from the held copy; an unchanged forecast comes back as an empty 304, which moves the held copy's expiry forward (checked live on 2026-09-30) |
| At most 20 requests a second; 429 means throttled, 203 means the product is deprecated | One request per expiry at most. A 203 body is still used; any other non-200 answer counts as a failure |
| Credit the data (CC BY 4.0) | The docs name Met.no as the source. Nothing is republished |

**Caching.** The product keeps one forecast in memory. When a refresh fails, the held copy is served even past its expiry, because a forecast issued an hour or two ago still describes the coming days well. Only a server that has never fetched a forecast answers with the error sentence. In the benchmark the forecast is also pinned in the per-run query cache: the first call of a run fetches it, and every later call in that run, for every candidate, reads the same document, which is the same fairness rule as for search.

**Privacy.** Met.no receives the home's latitude and longitude rounded to four decimals (about 11 metres), the apartment's IP address, and the User-Agent above. No account, no key, and nothing from the conversation: the question itself never leaves the Mac. Home Assistant's own Met.no integration already sends the home's coordinates for its weather entity, so this adds a second client, not a new kind of data leaving the home.

**Offered only when home is known.** The server reads `WEATHER_LATITUDE`, `WEATHER_LONGITUDE`, `WEATHER_TIMEZONE`, and `WEATHER_UNITS` from its environment (`weather_mcp/settings.py`). `scripts/ha_setup.py --only weather` copies them from Home Assistant into `.env`, and `scripts/services.sh install` passes them to the tool server's launchd job. Without coordinates the server starts without the weather tool and logs why, and the agent sends weather questions to search instead. The benchmark sets its own fixed coordinates in `benchmark/config.yaml`, so its results never depend on `.env`.

| Package | Role in the business logic |
|---|---|
| `httpx` | The Met.no request, with the timeout, the conditional header, and a replaceable transport that the tests use to play Met.no without the network |
| `zoneinfo` (standard library) | Turns UTC time steps into local days and parts of the day, daylight saving included |
| `pydantic` | `WeatherSettings`, the typed home location read from the environment |

No dependency was added; all three were already in the lock file.

## 15. Wikipedia tool, added 2026-10-07

The same MCP server now also offers `wikipedia_lookup`, from the `wikipedia_mcp` package, and `search_and_read` reads any English Wikipedia result through the same code. Before it, questions that need a list or a record ("how many quarterbacks have started for the 49ers since 2000") went wrong in two ways: search snippets are a sentence or two, and the page reader (trafilatura with `favor_precision=True`, §5) drops Wikipedia's tables. Reading *List of San Francisco 49ers starting quarterbacks* through `fetch_page` returned 925 words of prose and not one season row. The tables are the answer, so this reader keeps them.

```
  model (Ollama)                                   wikipedia_mcp, on the same MCP server (port 8765)
  ┌─────────────────────────────────┐ tools/call   ┌────────────────────────────────────────────────────┐
  │ wikipedia_lookup(               │─────────────▶│ WikipediaClient                                    │
  │   topic="49ers starting         │              │   search_titles(topic)  ───────────────────────────┼──▶ en.wikipedia.org
  │          quarterbacks",         │              │   article_html(best title) ────────────────────────┼──▶   /w/rest.php/v1/search/page?q=..&limit=5
  │   focus="2000")                 │              │   (both pinned in the run cache under wiki: keys)  │      /w/rest.php/v1/page/{title}/html
  └─────────────────────────────────┘              │                                                    │    User-Agent:
                ▲                                  │ render_article      Parsoid HTML → text            │    studio-assistant-wikipedia/1.0
                │ tool result, text:               │   headings as "## ...", prose as paragraphs,       │    github.com/seanlin2000/home_assistant
                │ "Wikipedia: List of San          │   every wikitable and infobox row on its own line  │
                │  Francisco 49ers starting ...    │ select_passages     the part the focus asks about  │
                │  ### Regular season              │   opening prose, then the best-matching lines,     │
                │  Season(s) | Quarterback(s)      │   up to 900 words                                  │
                │  2000 | Jeff Garcia (16) ...     │                                                    │
                │  Other articles: Brock Purdy ..."│                                                    │
                └──────────────────────────────────┤                                                    │
                                                   └────────────────────────────────────────────────────┘
  search_and_read: a result on en.wikipedia.org/wiki/... goes through WikipediaClient + render_article instead of the page download,
                   and select_passages uses the search query as the focus and words_per_page (600) as the budget.
```

**What the tool takes and returns.**

- Two arguments. `topic` is what the article is about, in plain words; Wikipedia's own search picks the article, so "49ers starting quarterbacks" finds the list. `focus` is optional words or a year naming the part wanted; without it the topic's words serve as the focus.
- The result is the article's title and URL, the selected text, and `Other articles:` with the next four search titles, so a model that got the wrong article can ask for one of those by name.
- Failures come back as sentences, never exceptions: no matching article ("Wikipedia has no article matching ..."), Wikipedia unreachable or answering with an error ("Wikipedia error: Wikipedia did not answer. Search the web with search_and_read instead."), or an empty topic.

**How the article becomes text** (`wikipedia_mcp/article.py`). The REST endpoint returns Parsoid HTML, in which every section is a `<section>` element holding its heading. The renderer walks those sections in order. Headings become `## Heading` lines, one `#` per level. Paragraphs and list items become lines. Every table with the class `wikitable` or `infobox` becomes one line per row, cells joined with ` | `, its caption first. Citations, styles, figures and image frames, navigation boxes, hatnotes, edit links, hidden sort keys, and the closing sections (References, See also, Notes, External links, and their usual variants) are dropped. Superscripts and line breaks get a space on each side, because a cell such as `San Francisco 49ers<sup>N</sup>(1, 1–0)` would otherwise read "49ersN(1," and no longer match the team's name. A merged cell appears once, in the first row it spans.

**How the part that answers is picked** (`wikipedia_mcp/passages.py` when this section was written; since §16 the ranker is `utils/passage_utils.py`, shared with every page `search_and_read` reads, and scores lines with BM25). An article within the budget comes back whole. A longer one keeps:

1. The opening paragraphs, up to a quarter of the budget.
2. Then the lines that share the most words with the focus, plural and singular alike. A line under a heading that names a focus word also counts as related, so "starting quarterbacks" keeps the rows of the *Starting quarterbacks* table although no row says so.
3. A year in the focus reads as "from then on", because list questions name a starting year ("since 2000") far more often than a single one. Lines naming only earlier years are left out, and lines naming that year or later rank first, so the year itself still leads.
4. A kept row brings its table's header row. When a row does not fit, the rest of its table is passed over with it: a list with a gap in the middle reads as complete and would be counted wrong. A table cut by the budget ends with "[N more matching lines here did not fit; to see them, ask again with a narrower focus, such as a year]".

The kept lines are printed in article order under their headings. Checked live on 2026-10-07: the 49ers list with focus "2000" returns every regular-season row from 2000 to 2026 and the postseason rows from 2001, in 606 words; *List of Super Bowl champions* with focus "49ers" returns the eight Super Bowl rows the 49ers played in and their franchise record.

**Inside `search_and_read`.** `PageExtractor` takes an optional `WikipediaClient`. For a result URL on the client's own host under `/wiki/`, `read_page` fetches the article through the API and renders it as above, and `read_pages` selects from it with the search query as the focus and `words_per_page` as the budget. If the API fails, the URL is read like any other page. When this section was written every other page was read from the top, with its text kept on one line; §16 gives every page its structure back and selects passages from all of them.

**Wikimedia's API etiquette, and how the client meets it** (`wikipedia_mcp/client.py`):

| Etiquette | How it is met |
|---|---|
| Identify the application and a way to contact its owner in the User-Agent | `studio-assistant-wikipedia/1.0 github.com/seanlin2000/home_assistant`: the repository is the contact, as for Met.no |
| Keep request rates modest; no crawling | Two requests per lookup (search, then the article), one at a time; a `search_and_read` question adds at most one article read per Wikipedia result |
| Follow redirects to the canonical title | Followed by hand, up to three hops, and only within `en.wikipedia.org`; a redirect anywhere else is an error |

The host is fixed by `WIKIPEDIA_BASE_URL` (default `https://en.wikipedia.org`), not chosen by the model, so these requests skip the public-address guard of §12, as the SearXNG and Met.no clients do. A model-chosen Wikipedia URL in `fetch_page` still goes through the guard: only `search_and_read` results use the API path.

**Caching.** The product caches nothing: a lookup costs two requests to Wikipedia, which answers in well under a second. In the benchmark the search titles and the article HTML are pinned in the per-run query cache (`wiki:search:` and `wiki:article:` keys), so every candidate reads the same revision.

**Privacy.** Wikimedia receives the topic the model wrote, the titles it reads, the apartment's IP address, and the User-Agent above. The topic is a few words the model chose from the question, not the transcript; this is the same kind of data a web search already sends to the search engines through SearXNG.

**Limits.** The tool answers what an encyclopedia records. Wikipedia lists the 49ers' starting quarterbacks and their first-round picks, but no article lists every player they drafted in every round, so "how many quarterbacks have the 49ers drafted since 2000" still has no table to read. Questions about anything that changes week to week stay with `search_and_read`.

| Package | Role in the business logic |
|---|---|
| `httpx` | The two REST requests, the redirect check, and a replaceable transport that the tests use to play Wikipedia without the network |
| `lxml` | Parses Parsoid HTML: sections, headings, table rows, and the clutter to drop. It was already installed through trafilatura and is now a declared dependency, because this package imports it directly |
| `pydantic` | `WikipediaSettings`, read from `WIKIPEDIA_*` environment variables, all with working defaults |

## 16. Passages for every page, added 2026-10-07

Asked "which Super Smash Bros. character uses the jab back air kill confirm" (exchange of 2026-10-07), the assistant answered that the sources did not say. The model was faithful to what it got; the tool lost the answer twice:

- **The page was read from the top.** SmashWiki's *Kill confirm* page was read, but the rows that answer ("Roy | Jab to sweetspotted back aerial", "Chrom | Jab to back aerial") sit about 3,600 words into its 5,340, in the *Super Smash Bros. Ultimate* table, and only the first 600 words reached the model.
- **Unread results were dropped.** Five of the ten results named Roy or Chrom in their title or snippet (YouTube, Reddit, GameFAQs, Smashboards), but none of those pages could be read (no extractable text, 403, a login wall), and `render_grounded_context` left out every result it had not read.

The ideas come from [skye-harris/llm_intents](https://github.com/skye-harris/llm_intents): its Brave "LLM context" mode returns the passages of each page that best match the query rather than the page head, its SearXNG tool always returns title and snippet, and its Brave tools take a freshness filter. They are taken here locally, with no new service and no API key.

**One ranker for every page** (`utils/passage_utils.py`). `select_passages(text, focus, max_words, page_title, left_out_note)` moved out of `wikipedia_mcp` and was rewritten; `wikipedia_mcp/passages.py` keeps the old name and calls it with §15's left-out note. Every guarantee of §15 stands: a short page comes back whole, the opening prose gets up to a quarter of the budget, kept lines are printed in page order under their headings, a table row brings its header row, a cut table or list is cut at the end and says how many matching lines it lost, a year means "from then on", and plurals match their singular. What changed:

| Rule | Why |
|---|---|
| Lines are scored with BM25 (k1 = 1.2, b = 0.75), with the page's own lines as the collection | A focus word counts for more the fewer lines it is on, so "jab" outweighs "character" on a page where every table has a Character column; a long row no longer wins only by having more words |
| Focus words in the page's title are set aside, unless that leaves none | The title names what every line is about: "Super Smash Bros" and "kill confirm" are on every row of *Kill confirm*. For `search_and_read` the title is the search result's, for `wikipedia_lookup` the article's. "49ers starting quarterbacks" against *List of San Francisco 49ers starting quarterbacks* keeps all its words through the fallback |
| A focus word in a heading counts, at half weight, for every line under it | Rows of the *Starting quarterbacks* table still match "starting quarterbacks" although no row says so |
| Two different focus words at most three words apart add the smaller of their two weights | "Jab to back aerial" outranks a row that says "jab" in one sentence and "back" in another |
| A line naming a year asked about ranks above every line that does not | The §15 year rule, kept exactly; BM25 orders the lines within each group |
| Headings, header rows, and left-out notes are paid for from the budget when a line is chosen | Unpaid, they pushed the last real rows past the final clip, which cut them mid-line |
| A cut table or list ends with "[N more matching lines left out]"; the caller can pass its own note template, and `wikipedia_lookup` passes §15's wording | §15's note tells the model to ask again with a narrower focus, which `search_and_read` has no argument for, and its 21 words were a large share of a 350-word budget |
| A level-1 heading above all the text is the page's own name, not a section | trafilatura starts a page with `# Title`; without the rule no line of an ordinary page would count as its opening prose |

**Ordinary pages keep their structure** (`web_search_mcp/page_markdown.py`). `trafilatura.extract` is asked for `output_format="markdown"`, which keeps `#` headings, `| a | b |` table rows, and `- ` list items. `to_passage_format` drops the `|---|` separator rows, the outer pipes, emphasis marks, simple inline tags such as `<sub>`, wiki `[edit]` links, and empty headings, and joins a paragraph's lines, so the page reaches `select_passages` in the same format as a Wikipedia article. `fetch_page` still returns the head of the page, now with its line breaks.

**Budgets** (`web_search_mcp/settings.py`). `pages_to_read` went from 4 to 6 and `words_per_page` from 600 to 350; `total_word_budget` stays 2,000, so the prompt does not grow. `fetch_page` has its own setting, `fetch_page_words` (1,200), so it keeps returning the 1,200 words it returned before `words_per_page` shrank. `wikipedia_lookup` keeps its own 900-word budget.

**One ranked list** (`render_grounded_context`, `web_search_mcp/server.py`). Every result up to `results_to_return` (8), and any page read below it, keeps its search rank as its number. A read page carries `URL:` and its passages; an unread one is marked `(not read)` and carries its snippet, with the engines' HTML tags stripped and entities unescaped. The header stays `Read N of M results for "<query>".` The block ends with: "If these sources do not answer the question, say plainly that you could not find it." The no-results and no-readable-page replies are unchanged. There is no automatic second search.

**`time_range`.** `search_and_read` and `web_search` take an optional `time_range` of `day`, `week`, `month`, or `year`, passed to SearXNG as its `time_range` parameter. The docstrings tell the model to use it for "latest" or "this week" questions. The argument is a plain string so that it never fails validation: `time_range_filter` in `searxng_client.py` lowercases it and keeps only those four values, and anything else, an empty string included, searches without a filter. A search with a time range is cached under its own key; one without keeps the key it always had.

**Checked.** The SmashWiki page, trimmed and saved as `tests/fixtures/smashwiki_kill_confirm.html`, is read through `PageExtractor` with the exchange's query, and the test asserts the Roy and Chrom rows are in the 350-word excerpt. Run live in process on 2026-10-07, the same query read 2 of 10 results, with the Roy and Chrom rows in the first, the five unread results listed by title and snippet, and the not-found line last.

**Side effects.**

- **The benchmark cache.** It holds page text, which the reader of §15 flattened to one line. A page cached before this change has no lines to choose between, so selection falls back to its head; a fresh cache directory gets the structure.
- **Comparability.** What `search_and_read` builds from the same pages changed, so search-category scores from later benchmark passes are not directly comparable with passes 1 to 5.

**Out of scope.** Reddit stays snippet-only (it requires a login and OAuth was declined), YouTube stays snippet-only (oEmbed returns only the title), and ranking stays lexical: no embedding model.

| Package | Role in the business logic |
|---|---|
| `trafilatura` | Now asked for Markdown, which keeps the headings, table rows, and lists that passage selection chooses between |

No dependency was added.
