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
4. The server assembles a compact block: numbered sources with title, URL, and up to about 600 words of extracted text each, capped at a total word budget so the prompt does not balloon. This block is the tool result.
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
- Defaults: 4 pages read, 600 words per page, 2,000 words total, 6 s fetch timeout, social networks and hard paywalls skipped, tables kept during extraction because rate and price pages keep their numbers in tables.
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
- The server side of the same idea: when the tool server is bound to the LAN (`WEB_SEARCH_HOST=0.0.0.0`) it answers only requests whose `Host` header names this machine (`WEB_SEARCH_ALLOWED_HOSTS`, written by `services.sh`) and none that carry a browser `Origin`, on the MCP endpoint and on `/turns` and `/healthz` alike; anything else gets 421. A web page open in a browser on the LAN can therefore not be used to reach the server through DNS rebinding. The library already does this for localhost binds; the benchmark and the tests bind localhost and set no list.

The broader rule for the product stays: never give the model a tool that acts on the home without an intent or confirmation layer in front of it, and treat anything derived from a web page as data, never as an instruction.

## 13. As built, 2026-09-06: engine rate limits

A day of benchmark passes, each firing dozens of searches within an hour, got the Mac's address throttled by every engine behind SearXNG at the same time: Brave answered "too many requests", DuckDuckGo demanded a CAPTCHA, Bing refused the connection, and Google returned empty pages while still answering a plain browser request from the same machine. The search tool then returned "No search results" and told the model to say so, which the harness records; the affected candidates were set aside and rerun later. Two changes came out of it: `SearxngClient` now waits a minimum gap between live requests (default 3 s; cached queries never wait), and the benchmark's search cache is kept per pass so a rerun of the same pass does not re-hit the engines. If Google stays blocked, the design's fallback of a Brave Search API key still applies.

The block did not lift on its own. A day later, with the container restarted so that SearXNG's in-process engine suspensions were cleared, each engine was probed from inside the container: Google now returns a page that says JavaScript is required (SearXNG issues #5286 and #5827 track the broken Google engine), Brave still answers 429, DuckDuckGo answers a CAPTCHA challenge, and SearXNG 2026.9.5's Bing engine drops the connection even though bing.com itself answers from the same container. Community guidance (SearXNG issues #2498, #2287, #1628 and the "searxng engine selection" note at conselara.dev) is to space queries at least three seconds apart, keep a session under about twenty queries, and enable engines beyond the big four. So `docker/searxng/settings.yml` now also keeps Startpage, Yahoo, and Wikipedia. Startpage (which serves Google's index) and Yahoo (which serves Bing's) answered at once with ten and seven results. Mojeek and Qwant, two smaller independent engines, were tried the same day, returned nothing for the probe query, and were dropped: they are not engines the user knows or wants results from. Benchmark pass 4 onward therefore searches through Startpage and Yahoo, where passes 1 to 3 searched Google, Bing, Brave, and DuckDuckGo. Within one pass every candidate sees the same engines, which is the fairness rule that matters; across passes, search results were never identical anyway because the web moves.
