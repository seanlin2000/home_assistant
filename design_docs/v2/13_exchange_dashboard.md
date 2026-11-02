# 13. Exchange Dashboard

Status: building

## 1. Purpose

One web page that shows what happened in each exchange: the question as Whisper heard it, the route the router chose, every model call and tool call with what it returned, the spoken answer, and how long each step took. Before this page, the question lived in Home Assistant's pipeline debug view, the tool calls and timings in the harness's exchange log, and the answer in both, each read with a different script in a different terminal tab. The point of the page is intuition for improving the harness and the tools: whether a search found the answer, whether the model used what it found, and where the seconds before the first spoken word went.

The page answers the home network only. Each exchange appears about a second after it finishes. A chat box at the bottom sends a typed question to the harness, as Home Assistant would, and shows the filler, tool calls, and answer as they stream; the finished exchange then opens like any other. Benchmark and TriviaBench runs come in a later change, on the same page.

## 2. Diagram

```
 THE MAC                                                                                   YOUR LAPTOP
 ┌───────────────────────────────────────────────────────────────────────────────────┐
 │  harness (:8770)                                                                  │
 │    each exchange ──▶ exchanges/YYYY-MM-DD.jsonl   trimmed record, kept 90 days    │
 │                 └──▶ traces/YYYY-MM-DD.jsonl      full transcript, kept 14 days   │
 │                                                    (every page the tools read)    │
 │                                                                                   │
 │  dashboard (:8775, home network only) ◀─────────────────────────────────────────────── browser
 │    reads both logs; every 5 s asks Home Assistant ─────▶ Home Assistant VM         │   polls every 2 s
 │    for its recent pipeline runs and keeps them    ◀───── speech-to-text and        │
 │    in pipeline_runs/YYYY-MM-DD.jsonl (14 days)           text-to-speech timings    │
 └───────────────────────────────────────────────────────────────────────────────────┘

 ONE EXCHANGE ON THE PAGE
 ┌─ sidebar ────────────┬─ gemma-4-e4b ──────────────────────────────────────────────────┐
 │ ✎ New chat           │                        ┌───────────────────────────────────┐   │
 │ Day (UTC) 2026-10-11 │                        │ Who won the World Series in 1995? │   │
 │ ▸Who won the World…  │                        └───────────────────────────────────┘   │
 │  20:41 · 6.8s        │                                    🎤 spoken · 20:41:07        │
 │ What's 17 percent…   │ ↪ router chose search                                          │
 │  20:38 · 1.9s        │ 🔊 "Let me look that up."  spoken at 1.66s                     │
 │                      │ 🔧 search_and_read "1995 World Series winner" 2.4s full text › │
 │                      │     1 mlb.com  Braves win 1995 World Series          ★         │
 │                      │ The Atlanta Braves won the World Series in 1995, …             │
 │                      │ (★ mlb.com)  gemma-4-e4b · total 6.8s · first word 1.66s       │
 │                      │ Timing ›  router ▌  model #1 ▓▓░  search_and_read ██████ …     │
 │ ● open new exchanges │ ┌────────────────────────────────────────────────────────────┐ │
 │ ● live               │ │ Ask Jarvis anything                                    (↑) │ │
 │                      │ └────────────────────────────────────────────────────────────┘ │
 └──────────────────────┴────────────────────────────────────────────────────────────────┘
```

## 3. How it works, step by step

### 3.1 What the harness keeps

The exchange log (v1/10 §3.4) keeps a trimmed record for 90 days and drops the text tools returned, because a search returns thousands of words. The dashboard needs that text, so the harness now writes a second, fuller log beside it: one trace per exchange, holding the whole transcript, including every tool result and any thinking text. Traces are kept 14 days; the health check's housekeeping deletes older day files, as it already does for the exchange log. A trace and its record share an `exchange_id`, and both carry Home Assistant's `conversation_id`. The transcript now also keeps the filler phrase spoken while the first tools ran, which the conversation view shows, and the per-question block put before the question. The trace also keeps the tool definitions every model call was sent, which the prompt cache tab needs (3.10); they are left out of the transcript wherever else it is written, such as benchmark results, because they run to thousands of tokens and are the same for every exchange.

### 3.2 When each step started

A record holds how long each model call and tool call took, but not when it started, and calls in one round run together. The agent loop now stamps each model call, tool call, and the router's decision with `started_seconds`, its start measured from the start of the exchange, so the timing chart places every bar where it ran. Older records without the stamps are laid out one step after another and marked as approximate.

### 3.3 Speech timings from Home Assistant

Speech to text and text to speech run in Home Assistant, which keeps each Assist pipeline run's events in memory for only the last few runs. The dashboard asks for them every five seconds over Home Assistant's websocket (the same calls `ops/pipeline_runs.py` makes) and keeps each new run in its own day files. A run is kept only once its `run-end` event has arrived: Home Assistant lists a run as soon as it starts and adds its later stages under the same id, so a run kept on first sight would hold only its first event or two. A run kept that way by an earlier version is pulled again while Home Assistant still remembers it, and the whole copy replaces the partial one. Home Assistant keeps one conversation id across the turns of a conversation, so the id alone cannot pick out an exchange. A run is a candidate when its conversation id or the text Home Assistant handed the agent matches the exchange, and it started within two minutes of it; a candidate matching on both wins, then the closest in time. The chart's zero is the moment the agent got the question, so speech to text sits left of zero and text to speech to the right. A typed question has no pipeline run, and its chart starts at the agent.

### 3.4 Long text

A tool result shows as a card in the conversation: the call, its time, and a short summary. A search lists one line per source (rank, site, title, size). A calculator or weather result is short enough to show whole. Clicking a card opens a side panel with the full text, one source at a time, and the raw text the model read. Words that the answer shares with a source are highlighted there, and a source that holds most of the answer's distinctive words gets a ★, where distinctive means the answer's content words that are not already in the question. A ★ with a wrong answer means the model missed what the search found; no ★ means the search never found it, or the model answered from memory.

### 3.5 Reading and writing time

Each model call has prompt tokens, cached tokens, the seconds spent reading the prompt, and the seconds spent writing (`GenerationStats`). The chart splits each model bar into loading (Ollama only), reading, and writing, so it shows that every round rereads its context, not only the first.

### 3.6 Live updates

The page asks for the list of days every two seconds. When the newest day gains an exchange, the list refreshes and, while "Open new exchanges as they arrive" is ticked, the new exchange opens. Each exchange's address (`#/day/line`) can be bookmarked or shared on the home network.

The page, titled Assistant Dashboard, is laid out like a chat app: exchanges in a sidebar, the open exchange as a conversation in the middle, and the question box at the bottom. The header names the model that answered the newest exchange, which is the model the harness is serving now; each exchange names its own model under its answer, so a model swap shows up exchange by exchange.

Above the open exchange sit the earlier questions of its conversation, found by conversation id on that day and the day before. Each shows only its answer until it is clicked; it then opens its own steps and timing chart in place, so a follow-up can be compared with the question before it without leaving the conversation.

### 3.7 The chat box

Typing a question is the quickest way to test a change to the harness without speaking to the puck. The page posts the question and the conversation so far to the dashboard, which passes it to the harness with the harness's API key, read from disk on the Mac, so the browser never holds it. The harness's events come back line by line. A question typed while an exchange is open is a follow-up to it: it carries that exchange's conversation, as a follow-up spoken to the puck would. "New chat" starts an empty conversation. The answer streams into the conversation, and the recorded exchange replaces it when it reaches the log about a second later. They are logged with the source `dashboard`, so they can be told apart from spoken ones. A request carrying another site's `Origin` is refused, so a page elsewhere cannot ask questions through the dashboard.

### 3.8 Opening it

`scripts/services.sh install` adds the dashboard as a launchd agent beside the harness. `scripts/services.sh dashboard` starts that agent if it is not running and opens the page; before install has written the agent, it runs the dashboard in the terminal instead. From another computer at home, the page is at the Mac's address on port 8775, which the command prints.

The dashboard belongs on the Mac that serves the assistant, beside the harness and llama-server, and is opened from whichever computer is at hand. Once the assistant moves to the Mac Studio, the dashboard runs on the Studio and the laptop opens it at the Studio's address, while development carries on on the laptop. Everything the page shows is read on the Mac the dashboard runs on: the logs, llama-server's slots, and the memory of 3.11. So the Studio's dashboard shows the Studio, and a dashboard started on the laptop for development shows the laptop.

### 3.9 Prefill and decode per response, and today's average

Prefill is the time a model call spends reading its prompt, and decode is the time it spends writing. The timing chart (3.5) shows both for each model call. Two numbers answer whether a change made the assistant faster: what this response cost, and what a response costs on an ordinary day.

**This response.** A card under each answer adds up the response's model calls, since every tool round reads and writes again:

| Row | Time | Tokens | Speed |
|---|---|---|---|
| Prefill | the sum of the calls' prompt reading | read fresh, and how many came from the prompt cache | fresh tokens over prefill time |
| Decode | the sum of the calls' writing | written | written tokens over decode time |

The prefill speed leaves the cached tokens out, because reusing them costs almost nothing. A line under the table lists each call by the number the timing chart gives it, so "model #2" names the same call in both. A last column compares each time with today's average, as slower or faster by so many seconds. Model calls without timings (an engine that did not report them) are left out. A response with none shows no card.

**Today's average.** The header shows today's response count, the average prefill and decode time per response, and today's speeds. Today runs from midnight on the Mac's clock, not UTC as the day files do, so an evening in New York is not split at 8 pm across two days; the dashboard reads the one or two UTC day files that local day spans. The speeds divide all of today's tokens by all of today's seconds, so a long prompt counts for more than a short one. The page asks for these figures with the day list, every two seconds.

### 3.10 The prompt cache tab

The page has three tabs in its header: Exchanges, the conversation view above; Prompt cache; and Memory (3.11). The Prompt cache tab shows whether the prompt order of v2/02 section 3.3 is doing its job: whether each model call found the parts that never change already cached, and read only what was new. An exchange's address is `#/day/line`, or `#/cache/day/line` to open it in this tab.

**Live slots.** Every two seconds, while the tab is open, the dashboard asks llama-server for its slots, with llama-server's key read from disk on the Mac, so the browser never holds it. Each slot shows a meter of about how many tokens it holds (its last prompt and what it wrote after it) against the share of the pool the harness budgets for it: 16,384 tokens for slot 0, the conversation, and the rest of the 18,432-token pool for slot 1, the router and the quiet requests. A slot can borrow past its share, so its meter stops at full. Hovering a slot shows its last request: prompt tokens, how many came from the cache, and how many it wrote.

**Each call's prompt.** The trace keeps the conversation, the system rules, the per-question block, and the tool definitions every call was sent (3.1). From these the dashboard rebuilds the prompt of each model call, and llama-server renders it through the model's own chat template and counts its tokens, so the sizes are the ones the model read. The prompt's parts follow the harness's order:

| Part | Changes when |
|---|---|
| System rules | The prompt version changes |
| Tool definitions | A tool is added or its description changes |
| Earlier exchanges | Each exchange adds one |
| Per-question block | Every question |
| Question | Every question |
| Tool rounds | Each round adds the model's tool calls and their results |

A part ends where a render of the prompt up to it stops matching the whole prompt, so the template's markers are counted as the model reads them; a boundary can sit a token late. When the rebuilt size matches the size llama-server recorded for the call, the layout is exact. Otherwise a note says the parts are approximate, as when the template or a tool changed since the exchange.

Each call is one bar of coloured parts, with a thin track under it: grey for what came from the cache, dark for what was read fresh, and a dashed line where the cache stopped. Every part also has a tooltip, and a table lists the parts of the last call with their sizes, so the colours are not the only way to read it.

**Where the cache stopped, judged.** Under the bars, one line per call says where the cache stopped, in the words of the parts ("cache held through tool definitions, read from earlier exchanges"), with a mark:

| Mark | Meaning |
|---|---|
| ✓ as expected | The first call found at least the system rules and tool definitions cached; a later call found everything the call before it sent |
| ! early | The cache stopped before that point, so text that should have been reused was read again |
| ✕ full re-read | Nothing came from the cache |
| ? unknown | The model server did not report the cached count, or the trace is too old to know what should have been cached |

For a follow-up, the first call is expected to re-read from the previous question onward, because the previous per-question block is dropped from the history (v2/02 section 3.3). Under the bars sit the system prompt, the per-question block, and the tool definitions, each folded, with each tool's own size measured against the system rules alone.

**Older traces.** A trace written before traces kept the tool definitions and the block is rebuilt without them. The size the first call recorded says how many tokens are missing, and they are drawn as one part after the system rules, "tool definitions and per-question block (not recorded)". The first call is then marked unknown rather than judged.

### 3.11 The memory tab

The Memory tab shows how much of the serving Mac's memory the Home Assistant setup takes, and what else is competing for it. Every two seconds, while the tab is open, the page asks for a reading. The dashboard reads at most once every four seconds however many pages ask, because `top` alone takes about half a second. `#/memory/day/line` opens the page on this tab.

**The reading.** It comes from macOS's own tools, none of which needs root:

| Tool | What it gives |
|---|---|
| `top -l 1 -stats pid,mem` | Each process's physical footprint |
| `ps` | Each process's executable and command line |
| `vm_stat` | The Mac's memory pages by kind |
| `sysctl` | The Mac's RAM, its swap, and its chip |
| `ioreg` | How much memory the GPU holds |
| `scutil --get ComputerName` | The Mac's name, at the head of the tab |

**This Mac.** A headline gives the setup's total and its share of the Mac's RAM. Under it, one bar splits the RAM the way Activity Monitor does, with each part's size beside its legend entry:

| Part | What it is |
|---|---|
| App memory | Memory apps allocated for themselves |
| Wired | Kept in RAM for the system and the GPU; llama-server's model weights are here |
| Compressed | Squeezed by macOS to make room |
| Cached files | File contents and purgeable memory, which macOS frees first |
| Free | Not in use |

Notes under the bar say how much of the wired memory the GPU holds, and how much has been swapped to disk.

**By process.** A process's size is its physical footprint, the figure Activity Monitor shows. A footprint counts what the process has compressed or swapped out, so on a Mac short of memory the footprints add up to more than its RAM; a dashed line on the bar marks the RAM. The setup's components come first, highlighted, then everything else in grey:

| Component | Found by |
|---|---|
| llama-server | Its executable |
| Home Assistant VM (UTM) | UTM's `QEMULauncher` |
| Whisper, speech to text | `wyoming-mlx-whisper` |
| Kokoro, text to speech | `kokoro-server` |
| Harness | `assistant-service` |
| Tool server | `assistant-mcp` |
| Exchange dashboard | `exchange-dashboard` |
| Docker Desktop, which runs SearXNG | Docker's app and its Linux virtual machine |

A component is matched on the executable and the first two words of its command line, which name a script and the interpreter running it. A shell that started a service names the service further along its command line, so it is not counted as the service. A component that is not running is still listed, as not running, so a stopped service shows as stopped rather than vanishing.

**llama-server's model weights.** llama-server maps its model file and hands it to the GPU, so the weights sit in wired memory and appear in no process's footprint. Stopping llama-server on the laptop freed about 5.6 GB of wired memory, its 0.5 GB footprint plus the 5.15 GB model file. The tab therefore adds the size of the model file in `config/serving.toml` to llama-server's footprint, and draws it hatched beside it.

**Everything else** is grouped by app, so a browser's dozens of helper processes count as the browser. The seven largest apps are named, and the rest are one group. Two tables under the bar, the setup and everything else, give each group's processes and size, so colour is not the only way to read the bar. Sizes are binary gigabytes labelled GB, as Activity Monitor labels them, so the two read the same.

## 4. Packages and what they do for the business logic

| Package | What it does here |
|---|---|
| Starlette and uvicorn | Serve the page and its small JSON API, as they already serve the harness |
| llama-server's `/apply-template`, `/tokenize`, and `/slots` | Render a prompt through the model's chat template, count its tokens, and report each slot's state |
| macOS's `top`, `ps`, `vm_stat`, `sysctl`, `ioreg`, and `scutil` | Read the Mac's memory, and each process's, for the memory tab |
| websockets (through `ops/ha_client.py`) | Ask Home Assistant for its recent pipeline runs |
| Plain HTML, CSS, and JavaScript | The page itself; no build step and nothing fetched from the internet |

## 5. Configuration we control

| Setting | Where | Value |
|---|---|---|
| Port | `dashboard/settings.py` | 8775 on every address, answering only host names derived from the Mac's address (as the harness does) |
| Trace retention | `assistant_service/exchange_log.py` | 14 days |
| Home Assistant poll interval | `dashboard/settings.py` | 5 seconds; off when `HA_HOST` or `HA_TOKEN` is missing from `.env` |
| Page refresh interval | `dashboard/static/app.js` | 2 seconds |
| llama-server address and key | `config/serving.toml` | The prompt cache tab is off when the key file is missing |
| Memory reading interval | `dashboard/memory_reader.py` | At most one reading every 4 seconds, shared by every page |
| The setup's components | `dashboard/memory_views.py` | The eight in section 3.11, each a pattern matched against the program a process runs |

## 6. Failure modes

- **Home Assistant is down or unreachable.** The page still shows every exchange; the speech bars read "not available".
- **The dashboard crashes.** Nothing else notices: it only reads files the harness writes, and the harness answers Home Assistant directly.
- **The harness is down when a question is typed.** The chat box shows why the question went unanswered (connection refused, timeout) instead of waiting.
- **A trace is missing** (an exchange from before this change, or older than 14 days). The page shows the record's summary, with tool calls as names, arguments, sizes, and times, and says the full text is gone.
- **llama-server is down, still loading, or refuses the key.** The prompt cache tab says so in place of the slots and the bars; the conversation view is unaffected.
- **The memory tools fail, time out, or the dashboard runs on something other than macOS.** The memory tab says why in place of its bars; the other tabs are unaffected.
- **A component's program is renamed.** It drops out of the setup into everything else, and the setup lists it as not running; its pattern in `dashboard/memory_views.py` has to follow the rename.
- **Two pipeline runs could match one exchange** (the same question asked twice in two minutes). The run matching on both conversation id and question wins; between equals, the closer start time does.

## 7. Concepts for newcomers

- **Prompt cache.** The model server keeps the prompt it last read, so the next call reads only the new tokens. The chart's "cached" count is how much of a call's prompt it did not have to read again.
- **Prefill and decode.** Prefill is the model reading the prompt, many tokens at once; decode is the model writing the answer, one token at a time. On the laptop prefill runs at a few hundred tokens a second and decode at about forty (v2/02 section 7).
- **Physical footprint.** The memory a process is charged for: what it allocated for itself, including what macOS has compressed or swapped to disk. Memory mapped from files, like a model's weights, is not part of it.
- **Wired memory.** Memory macOS will never compress or swap out. The GPU's working memory is wired, so on Apple silicon the model's weights land here.
- **Pipeline run.** Home Assistant's record of one voice exchange: wake word, speech to text, the agent, text to speech, each with timestamps.

## 8. Sources

- Home Assistant Assist pipeline events: [developers.home-assistant.io](https://developers.home-assistant.io/docs/voice/pipelines/)
