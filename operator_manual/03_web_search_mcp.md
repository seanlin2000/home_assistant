# MCP Tool Server
<!-- complexity: packages=3 parts=3 concepts=3 tier=deep -->

This part covers our MCP tool server, the program that serves the tools the language model can call: web search through SearXNG, an exact calculator, and the weather forecast for home. When you ask something the model cannot know from training, such as today's interest rate or the price of a device, the model asks for a search. Our tool server sends the query to SearXNG, a search aggregator running in Docker on the Mac, fetches the top pages, pulls out the readable text, and hands the model a numbered block of excerpts to answer from. The same server also does arithmetic exactly, so the model describes a calculation and never carries the digits itself.

## Where this fits

```mermaid
flowchart TB
--8<-- "_includes/system_map.mmd"
class mcp,searxng,engines current
```

`web_search_mcp` receives tool calls over MCP from the conversation agent and, during a benchmark, from the laptop. It sends each search query to SearXNG, a container that listens only on the Mac itself; SearXNG forwards the query to the public search engines, the first traffic that leaves the apartment. The server then fetches the pages the engines named, extracts their readable text, and returns numbered excerpts to the agent, which is what the model reads before it answers. The calculator tools live in the same server and never leave the Mac.

## Key definitions

| Term | Meaning |
|---|---|
| MCP (Model Context Protocol) | A standard for exposing tools to a language model application over a network, in which a server declares each tool with a name, a description, and a JSON schema, and a client lists them, shows them to the model, and calls them when the model asks. |
| Tool schema | The JSON description of a tool's parameters, which the model reads to decide when to call the tool and how to form valid arguments. |
| JSON-RPC | A convention for calling named methods over any transport, in which the caller sends a JSON object with a method, its params, and an id, and the reply carries the same id. |
| Streamable HTTP | MCP's current remote transport, in which every message is a POST to one endpoint and the server answers with a JSON body or a server-sent-events stream of `data:` lines. |
| Metasearch | A search engine, such as SearXNG, that queries other search engines and merges their results rather than crawling the web itself. |
| Grounding | Giving the model retrieved text to base its answer on, so it summarises evidence instead of recalling from training. |
| Main-content extraction | Turning a web page into the text a person came for, stripping navigation, ads, scripts, and legal text. |
| Docker Desktop on macOS | An app that runs Linux containers inside a hidden Linux virtual machine, where they cannot see the GPU or receive the network's discovery packets. |
| Prompt injection | Text inside a tool result, here a web page, that is written like an instruction and that the model may follow because it cannot tell it apart from your question. |
| URL guard | The rule that the tool server connects only to public web addresses: an allowed scheme, no local names, every resolved address globally routable, and every redirect hop checked again. |
| Globally routable address | An IP address that belongs on the public internet, which rules out loopback, private-range, link-local, and multicast addresses. |
| DNS rebinding | A hostile name server answering a safety check with a public address and the connection a moment later with a private one, which the URL guard defeats by connecting to the address it checked. |
| Syntax tree | The structure Python builds from an expression before running anything, with each operator a node and the values it acts on as its children. |

## Packages and tools

| Tool | What it is | How this part uses it |
|---|---|---|
| SearXNG (`searxng/searxng:latest`) | An open-source metasearch engine, run here as one Docker container named `studio-searxng` | Fans each query out to seven engines, merges and ranks the results, and returns them as JSON on `127.0.0.1:8080`. No account and no API key |
| Docker Desktop 4.89.0 | Runs Linux containers on macOS inside a hidden Linux VM | Hosts the SearXNG container. `docker/searxng/docker-compose.yml` binds the port to the Mac only and mounts `settings.yml` read-only |
| `mcp` 2.1.1 | The official Python MCP SDK | `MCPServer` turns each decorated Python function into a tool with a generated schema and serves them over streamable HTTP at `/mcp` on port 8765. `uvicorn` 0.52.4 and `starlette` 1.6.0 are the HTTP layer underneath, and the same `starlette` request objects serve the two plain routes `/healthz` and `/exchanges` |
| `httpx` 0.28.1 | An async HTTP client | Makes the SearXNG request, fetches pages with a 6 s timeout, asks Met.no for the forecast, and, on the agent side, is the only dependency of the MCP client in `assistant_core/mcp_http.py` |
| `trafilatura` 2.2.0 | A main-content extraction library | Turns each fetched HTML page into article text, keeping tables and dropping comments |
| `pydantic` 2.13.5 | Typed data models | `SearchResult`, `PageExcerpt`, `SearchSettings`, and `WeatherSettings` give every tool result and every setting a fixed shape |
| `diskcache` 5.6.3 | An on-disk key-value cache | Stores search results by query, page text by URL, and the forecast by location when a cache directory is set. On during a benchmark so every candidate model sees the same pages and the same forecast, off in the product |
| Met.no Locationforecast 2.0 | The Norwegian Meteorological Institute's free forecast API, used through its `complete` product | `MetnoClient` in `weather_mcp/metno_client.py` asks it for the forecast at home's coordinates, rounded to four decimals, with a User-Agent naming the project, and keeps each answer until its `Expires` time |
| `curl` and a browser | Standard HTTP clients | Prove the server and the container are up, and let you use SearXNG at http://127.0.0.1:8080 like any search page |

## How it works

### One tool call, end to end

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: agent  mcp  searxng  engines
%% grid: .      .mac .        pages
%% peers: agent mcp searxng engines pages
subgraph mac["The Mac"]
  agent("conversation agent<br/>in Home Assistant")
  mcp("web_search_mcp<br/>port 8765")
  subgraph docker["Docker Desktop"]
    searxng("SearXNG<br/>127.0.0.1:8080")
  end
end
subgraph internet["The internet"]
  engines("search engines<br/>Google, Bing, ...")
  pages("the top web pages")
end
agent -- "1 search_and_read" --> mcp
mcp -- "6 excerpts from the pages" --> agent
mcp -- "2 query" --> searxng
searxng -- "4 results" --> mcp
searxng -- "3 same query" --> engines
mcp -- "5 fetch the top pages" --> pages
class agent,mcp ours
class searxng third
class engines,pages ext
```

The server is one process called `assistant-tools`, built by `build_server` in `web_search_mcp/server.py`. It publishes eleven tools: `search_and_read`, `web_search`, and `fetch_page` for the web, and eight calculator tools registered by `calculator_mcp/register.py`. A twelfth, `weather_forecast`, registered by `weather_mcp/register.py`, is offered only when `WEATHER_LATITUDE` and `WEATHER_LONGITUDE` give the home's coordinates. Each tool is a Python function with a docstring. The `mcp` package reads the function signature to produce the JSON schema and the docstring to produce the description, so the docstring is the text the model reads when it decides whether to call the tool. `search_and_read` is the tool the system prompt steers small models to, and it is the one the figure above traces.

*From `web_search_mcp/server.py`, `search_and_read`:*

```python
    @server.tool()
    async def search_and_read(query: str) -> str:
        """Search the web and read the top pages. Returns numbered sources with title, URL, and the main text of each page, ready to synthesize an answer from. Use short keyword queries, e.g. "federal funds rate september 2026"."""
        results = await searxng.search(query)
        excerpts = await extractor.read_pages(results)
        return render_grounded_context(query, results, excerpts)
```

On the client side, the agent speaks the protocol with `HttpMcpToolBox` in `assistant_core/mcp_http.py`. MCP messages are JSON-RPC 2.0. It is a plain JSON-RPC client over `httpx`, because Home Assistant pins its own older `mcp` release and the component cannot rely on that package's API. It sends, in order:

1. `initialize`, which opens the session.
2. The `notifications/initialized` notice.
3. `tools/list`, once; the answer is cached.
4. `tools/call`, once for each tool the model asks for.

The server may answer any POST as plain JSON or as a server-sent-events stream, and `parse_messages` reads both. The session id arrives in the `mcp-session-id` response header and goes back on every later request. The benchmark on the laptop uses the official `mcp` client instead; both talk to the same server, which is the point of using a protocol rather than a private function.

What the model reads back depends on the tool and on what the search found:

- **`search_and_read`, pages read:** `render_grounded_context` opens with `Read 4 of 28 results for "..."`, so the model can say when evidence is thin, then lists each source as `[1] title`, `URL: ...`, and the page's text.
- **`search_and_read`, no results:** the tool result tells the model to say it could not find anything and to answer from its own knowledge with that caveat.
- **`search_and_read`, results but no readable page:** the first five snippets instead.
- **`web_search`:** only the ranked list of the first 8 results.
- **`fetch_page`:** one page's text, up to 1,200 words.

A capable model can chain `web_search` and `fetch_page`.

Asked for the current federal funds rate in benchmark pass 5, the top-scoring model called `search_and_read` once and got back 1,888 words that began like this, with each page's text cut here after its first sentence:

```text
Read 4 of 10 results for "current federal funds rate September 2026 and historical rate changes last year".

[1] Current Federal Funds Rate 2026 — Fed Rate History, FOMC Decisions ...
URL: https://wealthvieu.com/banking/interest-rates/federal-funds-rate/
The current federal funds rate target range is 3.50%–3.75%, with an effective rate of 3.63% as of June 2026. ...

[2] Federal Funds Effective Rate (FF) - Chart & Historical Data
URL: https://marketxls.com/indicators/fed-funds-rate
Federal Funds Effective Rate 3.63 for Federal Funds Effective Rate came in at 3.63 (Percent) for Wk of Sep 2 2026, ...

[3] Federal Funds Rate (1954-2026) - Macrotrends
URL: https://www.macrotrends.net/3247/federal-funds-rate
Federal Funds Rate (1954-2026) Federal Funds Rate: 3.63% as of September 2, 2026. ...

[4] US Interest Rate Statistics 2026 | Federal Reserve Rates, History ...
URL: https://theworlddata.com/us-interest-rate-statistics/
The current US Interest Rate in 2026 sits at a target range of 3.50%–3.75%, set by the Federal Reserve after its December 2025 rate cut and held steady through ...
```

### SearXNG in Docker

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: client  searxng   engines
%% grid: cache   settings  .internet
%% peers: client searxng engines
%% peers: cache settings
subgraph mac["The Mac"]
  subgraph mcpserver["web_search_mcp"]
    client("SearxngClient<br/>3 s between live searches")
    cache[("query cache<br/>results by query<br/>benchmark runs only")]
  end
  subgraph docker["Docker Desktop"]
    searxng("SearXNG<br/>studio-searxng<br/>127.0.0.1:8080, Mac only")
    settings[("settings.yml<br/>seven engines<br/>JSON output on")]
  end
end
subgraph internet["The internet"]
  engines("seven search<br/>engines")
end
client -- "query, as JSON" --> searxng
searxng -- "same query, in parallel" --> engines
cache -- "results of a<br/>repeated query" --> client
settings -- "mounted read-only" --> searxng
class client,cache,settings ours
class searxng third
class engines ext
```

SearXNG is the search engine the model never sees. `docker/searxng/docker-compose.yml` runs it as one container:

- **Image:** `searxng/searxng:latest`.
- **Name:** `studio-searxng`.
- **Restart:** always, unless you stop it.
- **Port:** 8080, bound to `127.0.0.1` so nothing else on the Wi-Fi can reach it.
- **Capabilities:** every Linux capability dropped except `CHOWN`, `SETGID`, and `SETUID`, the three it needs to change file ownership at start.
- **Secret key:** `scripts/searxng.sh up` generates one into `docker/searxng/.env`, which git ignores.

The only file we control is `docker/searxng/settings.yml`, mounted read-only into the container. It lists only what differs from the image's defaults:

- **Engines:** seven are kept, `google`, `bing`, `brave`, `duckduckgo`, `startpage`, `yahoo`, and `wikipedia`.
- **Formats:** `json` is enabled next to `html`.
- **Search:** English, with safe search off.
- **Rate limiter:** off, because the instance is not public.
- **Timeouts:** 6 s for each engine, with a hard stop at 10 s.

`SearxngClient` in `web_search_mcp/searxng_client.py` makes one GET per query with `format=json`, `language=en`, and `safesearch=0`, and turns each item of the JSON answer into a `SearchResult` with title, URL, snippet, the engines that returned it, and a score. SearXNG scores a result higher when several engines return it. The client checks the query cache first and, with a cache directory set, stores every live result there. Live requests are at least 3 s apart, a gap held under a lock so concurrent callers queue. The gap exists because the four large engines rate-limit or CAPTCHA a single home address that queries in bursts, and the three smaller engines keep search alive when they do. A spoken question rarely makes two live searches, so the assistant does not feel the gap; a benchmark firing dozens of questions does.

### Reading the pages

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: results  download  extract  sources
%% peers: results download extract sources
results("ranked results<br/>from SearXNG<br/>best match first")
download("download<br/>first 8 web pages<br/>6 s, 2 MB each")
extract("trafilatura<br/>keeps the main text<br/>and the tables")
sources("numbered sources<br/>4 pages with text<br/>under 2,000 words")
results -- "28 URLs" --> download
download -- "HTML pages" --> extract
extract -- "page text" --> sources
class results third
class download,extract,sources ours
```

Snippets are 10 to 30 words, written for a person skimming a results page, and the model needs paragraphs. So `PageExtractor` in `web_search_mcp/page_extractor.py` reads the pages themselves. `read_pages` takes five steps:

1. **Filter.** It drops any result that is not `http` or `https`, that ends in a binary extension such as `.pdf` or `.jpg`, or that sits on a blocked domain. The blocked list in `web_search_mcp/settings.py` holds:
    - social networks: Facebook, Instagram, X and Twitter, TikTok, Pinterest, and LinkedIn;
    - hard paywalls: the Wall Street Journal, the Financial Times, Bloomberg, and the New York Times.
2. **Pick.** It takes the first 8 survivors, twice the 4 pages it wants.
3. **Download.** It fetches them concurrently with `asyncio.gather`, each through [the URL guard](#the-url-guard), so one slow site costs at most the 6 s timeout rather than 6 s per page. Results keep their order, so the engines' ranking survives extraction.
4. **Extract.** Each page goes through `trafilatura.extract` with comments dropped, tables kept, and precision favoured over recall.
5. **Budget.** Each page is clipped to its first 600 words as a `PageExcerpt`, the first four with text are kept, and `apply_total_budget` trims the last of them so the block stays under 2,000 words.

A page that yields no text, times out, is not HTML, runs past 2 MB, or is refused by the URL guard becomes an empty string and is skipped.

- **Why tables are kept:** rate and price pages carry their numbers in tables.
- **Why 2,000 words:** the model reads the whole block before it writes a word, and that reading time on the Mac grows with prompt length.
- **The cache:** with a cache directory set, page text is stored by URL, so a repeated fetch never opens a socket.

### The URL guard

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: url  check  connect  peer  read
%% grid: .    .      refused  .     redirect
%% peers: url check connect peer read refused redirect
url("a URL<br/>from the model or<br/>a search result")
check("check the URL<br/>http(s), not local<br/>every address public")
connect("connect<br/>to a checked address<br/>real name in TLS")
peer("check the peer<br/>the socket's address<br/>is public")
read("read the answer<br/>HTML only<br/>stop past 2 MB")
refused("refused<br/>UnsafeUrl<br/>nothing is read")
redirect("a redirect<br/>new URL goes back<br/>to check the URL")
url --> check
check --> connect
connect --> peer
peer --> read
check -- "no" --> refused
peer -- "no" --> refused
read -- "a 3xx answer" --> redirect
class url third
class check,connect,peer,read,refused,redirect ours
```

The model picks the URLs that `fetch_page` reads, and a web page can tell the model which URL to pick. That is prompt injection, and it cannot be prevented at the model. So the code bounds what an obeyed instruction can reach. Without a guard, that could be the router, the Home Assistant VM, Ollama's API on port 11434, or a cloud metadata address.

`_download` in `web_search_mcp/page_extractor.py` takes every URL through four steps:

1. **Check the URL.** `ensure_public_url` in `web_search_mcp/url_guard.py` runs before every connection:
    - the scheme is `http` or `https`;
    - the host is not `localhost`, `localhost.localdomain`, or `metadata.google.internal`;
    - the host does not end in `.local`, `.internal`, `.localhost`, `.lan`, `.home`, or `.arpa`;
    - the name is resolved once, and every address must be globally routable, which `is_public_address` decides with Python's `ipaddress` module after unwrapping IPv4-mapped IPv6 addresses and refusing multicast;
    - one private address among several refuses the whole name.
2. **Connect** to the first address the check approved, never to a second lookup of the name. A hostile name server can answer the check with a public address and the connection a moment later with a private one (DNS rebinding).
    - `pin_url_to_address` swaps the URL's host for that address;
    - the real name travels in the `Host` header through `host_header`;
    - for `https` it also travels in the TLS handshake as `sni_hostname`, so certificate verification still checks the real name.
3. **Check the peer.** `refuse_unless_public_peer` reads the peer address from the socket and refuses unless it is public. This also catches a transport that resolved the name on its own.
4. **Read the answer.**
    - A redirect is not followed automatically: its `Location` is resolved against the current URL and goes back to step 1, at most five hops.
    - Otherwise the body must be HTML.
    - It is streamed and abandoned past 2,000,000 bytes, or sooner if the declared `Content-Length` is larger, so a hostile page cannot flood the model.

*From `web_search_mcp/page_extractor.py`, `_download`:*

```python
        async with httpx.AsyncClient(timeout=self._settings.fetch_timeout_seconds, follow_redirects=False, headers=headers, transport=self._transport) as client:
            for _ in range(self._settings.max_redirects + 1):
                addresses = await ensure_public_url(url, self._resolver)
                hostname = urlparse(url).hostname or ""
                extensions = {"sni_hostname": hostname} if urlparse(url).scheme == "https" else {}
                async with client.stream("GET", pin_url_to_address(url, addresses[0]), headers={"Host": host_header(url)}, extensions=extensions) as response:
                    refuse_unless_public_peer(response)
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    response.raise_for_status()
                    if "html" not in response.headers.get("content-type", ""):
                        raise ValueError("not an HTML page")
                    return await self._read_capped(response)
        raise ValueError("too many redirects")
```

What happens after a refusal, and how it is tested:

- **`fetch_page`** turns `UnsafeUrl` into the sentence `Refused to fetch ...: ... Only public web addresses can be read.`, so the model can tell you instead of retrying.
- **`search_and_read`** silently skips that result and reads the next.
- **Tests:** the resolver and the HTTP transport are constructor arguments of `PageExtractor`, which is how `tests/test_url_guard.py` pretends a public-looking name resolves to the router and serves redirects without opening a socket.

The broader rule stands: nothing derived from a web page is an instruction, and no tool that acts on the home is given to the model without an intent or confirmation layer in front of it, as the page on the [conversation agent](04_conversation_agent.md) explains.

### The calculator tools

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: expression  normalize  parse  evaluate  answer
%% grid: .           .          error  .         .
%% peers: expression normalize parse evaluate answer error
expression("an expression<br/>from the model<br/>$3,500 * 1.05 * 12")
normalize("normalize<br/>drop $ and commas<br/>15% becomes 15/100")
parse("parse<br/>into a Python<br/>syntax tree")
evaluate("evaluate the tree<br/>allowed syntax only<br/>numbers in limits")
answer("the answer<br/>result: 44,100<br/>plus a spoken line")
error("Calculator error<br/>returned as text<br/>so the model retries")
expression --> normalize
normalize --> parse
parse --> evaluate
evaluate --> answer
parse -- "not valid" --> error
evaluate -- "not allowed" --> error
class expression third
class normalize,parse,evaluate,answer,error ours
```

The worked example, `3500 * 1.05 * 12` after normalizing, becomes this syntax tree, and the calculator computes each operator from its children, bottom up:

```text
        multiply
        /      \
   multiply     12
   /      \
3500      1.05
```

A language model predicts the next token and does not carry, so every local model sets up a rent calculation correctly and then gets the digits wrong. The eight calculator tools in `calculator_mcp/` turn the arithmetic into something the model only has to describe.

`calculate(expression)` works as follows:

- **Allowed:** numbers, the operators `+ - * / // % **`, parentheses, the names `pi` and `e`, and the ten functions `round`, `sqrt`, `abs`, `min`, `max`, `log`, `log10`, `exp`, `floor`, and `ceil`.
- **Normalized first:** `normalize_expression` drops thousands separators and `$`, turns `×`, `÷`, and `^` into Python operators, and rewrites a percent literal such as `15%` as `(15/100)`.
- **Refused with a `CalculatorError`:** attribute access, other names, keyword arguments, an exponent above 1,000, division by zero, a result beyond 1e30, and a parse failure. The message says what went wrong, and for syntax outside the list it says what is allowed.
- **Never `eval`:** the text is parsed with `ast`, and only the allowed parts of the tree are computed.

The other seven tools are shaped for spoken questions:

| Tool | The question it answers | Arguments |
|------|-------------------------|-----------|
| `percent` | "What is 18 percent of 245?" and its cousins: a is what percent of b, the percent change from a to b, b increased or decreased by a percent | `kind`, `a`, `b` |
| `convert` | A unit conversion over a fixed table of length, mass, volume, area, energy, power, speed, time, and data, with temperature handled as an affine conversion | `value`, `from_unit`, `to_unit` |
| `growth_schedule` | Compounding laid out period by period, such as rent rising 3 percent a year | `start`, `rate_percent`, `periods`, `per_period_multiplier` (default 1) |
| `energy_cost` | What a device costs to run, from watts, hours a day, and a price per kilowatt hour | `watts`, `hours_per_day`, `price_per_kwh`, `days` (default 30), `idle_watts` (default 0) |
| `loan_payment` | The monthly payment and total interest of a fixed-rate loan | `principal`, `annual_rate_percent`, `years` |
| `break_even` | How many months until an upfront cost is recovered by a monthly saving | `monthly_saving`, `upfront_cost` |
| `date_math` | Days between two dates, a date plus some days, the weekday of a date, or the weeks until one | `kind`, `date` (default today), `other_date` (default today), `days` (default 0) |

Every function returns a `Result` whose `render` prints the exact number first as `result: ...`, then a sentence as `spoken: ...`, then any details such as a schedule. Rounding happens only inside the sentence.

What is not included:

- **Currency conversion:** it needs live rates, so it belongs to search.
- **Statistics:** there is no data source.

*From `calculator_mcp/register.py`, `rendered`:*

```python
def rendered(function: Callable[..., Result], *args: object, **kwargs: object) -> str:
    try:
        result: Result = function(*args, **kwargs)
    except CalculatorError as error:
        return f"Calculator error: {error}"
    except (TypeError, ValueError, OverflowError) as error:
        return f"Calculator error: {error}"
    return result.render()
```

Errors come back as tool text starting with `Calculator error:` rather than as a protocol failure, so the model can correct its arguments and call again instead of the agent loop stopping. There is no router deciding when a calculator is used. The server publishes each tool's name, description, and argument schema, the agent copies that list into every chat request, and the model reads it like any other text. The description is therefore the routing rule, which is why `calculate`'s says "for any calculation with more than one step and always for money", and the [agent's](04_conversation_agent.md) system prompt repeats that rule in its own words.

### Plain routes and the Host check

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: agent    mcp
%% grid: .        exchanges
%% grid: health   healthz
%% grid: browser  refused
%% peers: agent health browser mcp exchanges healthz refused
agent("conversation agent<br/>in the Home<br/>Assistant VM")
health("health check<br/>launchd, every<br/>5 minutes")
browser("a web page<br/>in a browser<br/>on the Wi-Fi")
subgraph server["web_search_mcp, port 8765"]
  mcp("/mcp<br/>the eleven tools<br/>over MCP")
  exchanges("/exchanges<br/>one JSON Lines<br/>file per day")
  healthz("/healthz<br/>tool names, and<br/>ok or degraded")
  refused("421 Misdirected<br/>Host not this Mac,<br/>or a browser Origin")
end
agent -- "tool calls" --> mcp
agent -- "one record per exchange" --> exchanges
health -- "is it ours?" --> healthz
browser -- "any request" --> refused
class agent,health,mcp,exchanges,healthz,refused ours
class browser third
```

The server answers on three routes, all on port 8765. `register_operations_routes` adds the two plain HTTP ones, `/healthz` and `/exchanges`, beside `/mcp`:

| Route | Who calls it | What it does |
|-------|--------------|--------------|
| `/mcp` | The conversation agent, and the benchmark on the laptop | Serves the eleven tools, or twelve with `weather_forecast`, over MCP, as in [One tool call, end to end](#one-tool-call-end-to-end) |
| `GET /healthz` | The health check | Lists the tool names the server is serving and reports `ok`, or `degraded` with the missing names, against the six tools a live server must expose: `search_and_read`, `web_search`, `fetch_page`, `calculate`, `percent`, and `convert`. That is how the [health check](10_operations.md#the-health-check) proves the process on port 8765 is ours |
| `POST /exchanges` | The conversation agent, after each answer. A record that fails to post is dropped, and the answer is unaffected | Saves an *exchange record*, a one-line summary of the exchange (the question, the answer, the tool calls and their timings, and the failure flags), to that day's log file, which is deleted after 90 days. The laptop copies these files for the [operations report](10_operations.md#the-report) |
| Any route, with a wrong `Host` or a browser `Origin` | Whatever sends it, such as a web page in a browser on the Wi-Fi | Refuses it with 421 Misdirected Request |

The Host check applies only when the server is bound to the LAN so the VM can reach it, which is how `scripts/services.sh install` runs it (`WEB_SEARCH_HOST=0.0.0.0`):

- **The allow-list** is `WEB_SEARCH_ALLOWED_HOSTS`, which `services.sh` writes as the Mac's LAN address, `localhost`, and `127.0.0.1`, each with port 8765.
- **The rule:** a request is served only when its `Host` header is on the list and it carries no browser `Origin`.
- **Where it is enforced:** `transport_security_for` hands the list to the `mcp` library for `/mcp`, and `host_allowed` applies the same rule to `/healthz` and `/exchanges`.
- **What it stops:** a web page open in a browser on the same Wi-Fi cannot use DNS rebinding to reach the tool server.
- **Without a list**, which is how the benchmark and the tests run the server on localhost, the library's own default applies.

## Run it yourself

Everything here runs on the Mac, from the repository folder. Start with SearXNG, since the search tools are empty without it:

```bash
scripts/searxng.sh status
```

You see a `docker compose ps` table with `studio-searxng` in state `running` and the line `SearXNG JSON API: ok`. If the container is not running, `scripts/searxng.sh up` writes the secret into `docker/searxng/.env` the first time and starts it; give it a few seconds and run `status` again. Open http://127.0.0.1:8080 in a browser and you can use it like a search page, which is the quickest way to see what the model sees. `scripts/searxng.sh logs` tails the container's log; press Ctrl-C to stop tailing. `scripts/searxng.sh down` stops the container.

Next confirm the tool server is alive:

```bash
curl -s -o /dev/null -w "MCP server: %{http_code}\n" http://127.0.0.1:8765/mcp
curl -s http://127.0.0.1:8765/healthz
```

The first line prints `MCP server: 400`, and 400 is the healthy answer: the endpoint is up but wants an MCP client, not a browser. The second prints JSON with `"status": "ok"` and the tool names: eleven, or twelve when the home's coordinates are set. On the always-on Mac the server runs under launchd, and `scripts/services.sh status` shows port 8765 next to the other services, `scripts/services.sh logs mcp` tails `~/Library/Logs/studio-assistant/mcp.log` until you press Ctrl-C, and `scripts/services.sh restart mcp` restarts it. On a laptop without those agents, `uv run web-search-mcp` starts the same server in the foreground on `127.0.0.1:8765`; Ctrl-C stops it. Set `WEB_SEARCH_CACHE_DIR` to a folder before starting it if you want repeated queries served from disk.

Now call tools by hand with the same client the Home Assistant component uses:

```bash
uv run python - <<'EOF'
import asyncio
from assistant_core.mcp_http import HttpMcpToolBox
from assistant_core.models import ToolCall

async def main():
    async with HttpMcpToolBox("http://127.0.0.1:8765/mcp") as tools:
        for spec in await tools.list_tools():
            print(f"{spec.name:18} {spec.description[:80]}")
        print()
        print(await tools.call(ToolCall(id="1", name="percent", arguments={"kind": "of", "a": 18, "b": 245})))
        print()
        print((await tools.call(ToolCall(id="2", name="search_and_read", arguments={"query": "Home Assistant Voice Preview Edition price"})))[:1500])

asyncio.run(main())
EOF
```

You see eleven tools, or twelve with `weather_forecast`, with the first line of each description, then `result: 44.10` with a `spoken:` line the model can read aloud, then `Read 4 of ...` followed by numbered excerpts with URLs. Those excerpts are exactly what the model reads before it answers a searched question. The search takes several seconds on a live query and returns at once on a cached repeat. The script exits on its own.

Finally, test the URL guard. Change the last call in the snippet to `fetch_page` with `{"url": "http://192.168.1.156/"}`, or any address on your own network, and run it again. The tool answers `Refused to fetch http://192.168.1.156/: '192.168.1.156' resolves to non-public address 192.168.1.156. Only public web addresses can be read.` and nothing on the network is touched. `uv run pytest tests/test_url_guard.py` runs the same rules against fake resolvers and redirects without opening a socket.

## Where to look in the code

| Path | What you find there |
|---|---|
| `web_search_mcp/server.py` | `build_server`: the three search tools, the calculator and weather registrations, `/healthz` and `/exchanges`, the Host allow-list, and `main` |
| `web_search_mcp/searxng_client.py` | `SearxngClient`: the SearXNG request, the query cache in front, the 3 s gap behind |
| `web_search_mcp/page_extractor.py` | `PageExtractor`: filtering, concurrent download, redirect handling, the byte cap, `trafilatura` extraction, and the word budgets |
| `web_search_mcp/url_guard.py` | `ensure_public_url`, `is_public_address`, `pin_url_to_address`, `host_header`: the public-address rule |
| `web_search_mcp/query_cache.py` | `QueryCache`: `diskcache` keyed by query, by URL, and by forecast location, active only with a cache directory |
| `web_search_mcp/settings.py` | `SearchSettings`: every default and the `WEB_SEARCH_*` environment overrides |
| `web_search_mcp/exchange_log.py` | `ExchangeLog`: one JSON Lines file per day under the exchanges directory, pruned after 90 days |
| `calculator_mcp/functions.py` | The eight calculator functions and `Result`, pure Python with no MCP dependency |
| `calculator_mcp/register.py` | `register_calculator_tools`: the tool docstrings the model reads, and `rendered` |
| `weather_mcp/register.py`, `weather_mcp/metno_client.py`, `weather_mcp/forecast.py`, `weather_mcp/settings.py` | `register_weather_tools`, which offers `weather_forecast` only when home has coordinates; `MetnoClient`, the Met.no request; `ForecastReader`, which turns the forecast into local days and parts of the day; `WeatherSettings` and the `WEATHER_*` environment overrides |
| `docker/searxng/docker-compose.yml`, `docker/searxng/settings.yml` | The container definition and the seven engines, output formats, and timeouts |
| `scripts/searxng.sh` | `up`, `down`, `restart`, `status`, `logs` for the container, and the secret in `docker/searxng/.env` |
| `assistant_core/mcp_http.py` | `HttpMcpToolBox`: the client side of the protocol, `initialize`, `tools/list`, `tools/call`, and the SSE parser |
| `tests/test_url_guard.py`, `tests/test_web_search_mcp.py`, `tests/test_calculator.py`, `tests/test_weather_forecast.py`, `tests/test_mcp_http.py` | The guard against private addresses, redirects, rebinding, and oversized pages; the tools listed and called in process; the arithmetic; the forecast; the client against the real server |

## Further reading

- Design doc: https://github.com/seanlin2000/home_assistant/blob/main/design_docs/v1/03_web_search_mcp.md, with the as-built sections on the calculator tools, fetch safety, and engine rate limits
- SearXNG documentation, https://docs.searxng.org/, for every key `settings.yml` can hold and what each engine needs
- MCP Python SDK, https://github.com/modelcontextprotocol/python-sdk, for `MCPServer`, the `@server.tool()` decorator, and the transport settings the server passes on `run()`
- trafilatura, https://trafilatura.readthedocs.io/, for what `favor_precision` and `include_tables` change in extraction
- Home Assistant MCP integration, https://www.home-assistant.io/integrations/mcp/, and the discussion at https://github.com/orgs/home-assistant/discussions/1383 on its SSE-only client, which is why our agent is the MCP client rather than Home Assistant
