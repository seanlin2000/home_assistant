# 13. Exchange Dashboard

Status: building

## 1. Purpose

One web page that shows what happened in each exchange: the question as Whisper heard it, the route the router chose, every model call and tool call with what it returned, the spoken answer, and how long each step took. Before this page, the question lived in Home Assistant's pipeline debug view, the tool calls and timings in the harness's exchange log, and the answer in both, each read with a different script in a different terminal tab. The point of the page is intuition for improving the harness and the tools: whether a search found the answer, whether the model used what it found, and where the seconds before the first spoken word went.

The page is read-only and answers the home network only. Each exchange appears about a second after it finishes; nothing streams token by token. Benchmark and TriviaBench runs come in a later change, on the same page.

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
 ┌─ list ──────────────┬─ 20:41:07  "Who won the World Series in 1995?" ───── 6.8s ─┐
 │ ▸20:41 Who won… 6.8s│  TIMING  speech→text ███                                   │
 │  20:38 What's 17…1.9s│          router         ▌                                  │
 │                     │          model #1        ▓▓░        ▓ reading the prompt    │
 │                     │          search_and_read    ██████   ░ writing              │
 │                     │          model #2                ▓▓▓░░░                     │
 │                     │  🎤 Who won the World Series in 1995?                       │
 │                     │                          🔊 Let me look that up.   filler    │
 │                     │  🔧 search_and_read "1995 World Series winner"  2.4s  [▸]   │
 │                     │      1 mlb.com  Braves win 1995 World Series  ★             │
 │                     │                          🔊 The Atlanta Braves, …          │
 └─────────────────────┴────────────────────────────────────────────────────────────┘
```

## 3. How it works, step by step

### 3.1 What the harness keeps

The exchange log (v1/10 §3.4) keeps a trimmed record for 90 days and drops the text tools returned, because a search returns thousands of words. The dashboard needs that text, so the harness now writes a second, fuller log beside it: one trace per exchange, holding the whole transcript, including every tool result and any thinking text. Traces are kept 14 days; the health check's housekeeping deletes older day files, as it already does for the exchange log. A trace and its record share an `exchange_id`, and both carry Home Assistant's `conversation_id`. The transcript now also keeps the filler phrase spoken while the first tools ran, which the conversation view shows.

### 3.2 When each step started

A record holds how long each model call and tool call took, but not when it started, and calls in one round run together. The agent loop now stamps each model call, tool call, and the router's decision with `started_seconds`, its start measured from the start of the exchange, so the timing chart places every bar where it ran. Older records without the stamps are laid out one step after another and marked as approximate.

### 3.3 Speech timings from Home Assistant

Speech to text and text to speech run in Home Assistant, which keeps each Assist pipeline run's events in memory for only the last few runs. The dashboard asks for them every five seconds over Home Assistant's websocket (the same calls `ops/pipeline_runs.py` makes) and keeps each new run in its own day files. Home Assistant keeps one conversation id across the turns of a conversation, so the id alone cannot pick out an exchange. A run is a candidate when its conversation id or the text Home Assistant handed the agent matches the exchange, and it started within two minutes of it; a candidate matching on both wins, then the closest in time. The chart's zero is the moment the agent got the question, so speech to text sits left of zero and text to speech to the right. A typed question has no pipeline run, and its chart starts at the agent.

### 3.4 Long text

A tool result shows as a card in the conversation: the call, its time, and a short summary. A search lists one line per source (rank, site, title, size). A calculator or weather result is short enough to show whole. Clicking a card opens a side panel with the full text, one source at a time, and the raw text the model read. Words that the answer shares with a source are highlighted there, and a source that holds most of the answer's distinctive words gets a ★, where distinctive means the answer's content words that are not already in the question. A ★ with a wrong answer means the model missed what the search found; no ★ means the search never found it, or the model answered from memory.

### 3.5 Reading and writing time

Each model call has prompt tokens, cached tokens, the seconds spent reading the prompt, and the seconds spent writing (`GenerationStats`). The chart splits each model bar into loading (Ollama only), reading, and writing, so it shows that every round rereads its context, not only the first.

### 3.6 Live updates

The page asks for the list of days every two seconds. When the newest day gains an exchange, the list refreshes and, while "Open new exchanges as they arrive" is ticked, the new exchange opens. Each exchange's address (`#/day/line`) can be bookmarked or shared on the home network.

## 4. Packages and what they do for the business logic

| Package | What it does here |
|---|---|
| Starlette and uvicorn | Serve the page and its small JSON API, as they already serve the harness |
| websockets (through `ops/ha_client.py`) | Ask Home Assistant for its recent pipeline runs |
| Plain HTML, CSS, and JavaScript | The page itself; no build step and nothing fetched from the internet |

## 5. Configuration we control

| Setting | Where | Value |
|---|---|---|
| Port | `dashboard/settings.py` | 8775 on every address, answering only host names derived from the Mac's address (as the harness does) |
| Trace retention | `assistant_service/exchange_log.py` | 14 days |
| Home Assistant poll interval | `dashboard/settings.py` | 5 seconds; off when `HA_HOST` or `HA_TOKEN` is missing from `.env` |
| Page refresh interval | `dashboard/static/app.js` | 2 seconds |

## 6. Failure modes

- **Home Assistant is down or unreachable.** The page still shows every exchange; the speech bars read "not available".
- **The dashboard crashes.** Nothing else notices: it only reads files the harness writes.
- **A trace is missing** (an exchange from before this change, or older than 14 days). The page shows the record's summary, with tool calls as names, arguments, sizes, and times, and says the full text is gone.
- **Two pipeline runs could match one exchange** (the same question asked twice in two minutes). The run matching on both conversation id and question wins; between equals, the closer start time does.

## 7. Concepts for newcomers

- **Prompt cache.** The model server keeps the prompt it last read, so the next call reads only the new tokens. The chart's "cached" count is how much of a call's prompt it did not have to read again.
- **Pipeline run.** Home Assistant's record of one voice exchange: wake word, speech to text, the agent, text to speech, each with timestamps.

## 8. Sources

- Home Assistant Assist pipeline events: [developers.home-assistant.io](https://developers.home-assistant.io/docs/voice/pipelines/)
