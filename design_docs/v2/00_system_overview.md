# 00. System overview

Status: designed 2026-10-08

## 1. Purpose

v1 built a voice assistant whose text-in, text-out path works end to end: a spoken question becomes text, an agent loop answers it from Gemma 4 E4B and four kinds of tools (web search, calculator, weather at home, Wikipedia), and the answer is spoken back. The machine caps the model: until a Mac mini or Mac Studio arrives in mid-November 2026, a 16 GB laptop that also runs the Home Assistant VM can only hold a small model, and prefill on it is slow. So v2 makes the small model more capable through the harness around it:

1. **Memory.** When a conversation ends, the assistant saves a short summary of it as its own note, and later questions draw on the notes that match. Today it sees only a few minutes of Home Assistant's chat history. You read, edit, and delete the notes yourself in Obsidian.
2. **Several tools per question.** "Is it warmer in Lisbon than here tomorrow, and by how much?" needs a forecast for two places and a subtraction. The loop plans for that and keeps the context small enough for a small model.
3. **More tools.** Weather for any place, NBA and NFL statistics, and Reddit threads now; Gmail newsletters, a shared calendar, X posts, and bank statements after the new Mac (doc 13).
4. **Speed and control.** llama.cpp's `llama-server` replaces Ollama, so the harness controls prompt caching, context size, and every serving setting directly.

Security outranks all four. Every new capability is designed around one assumption: a web page, email, or post will sometimes talk the model into something, so code, not the model, decides what reaches memory and what leaves the house (doc 12).

v2 holds only the docs that change or are new. Voice, Home Assistant, music, and the development environment are unchanged; their v1 docs still apply.

## 2. Diagram

```
┌─ YOUR STUDIO: everything inside stays local ───────────────────────────────────────────────────────────────────────────────┐
│                                                                                                                            │
│                    ╭────────────╮                                                                                          │
│                    │ Voice puck │                                                                                          │
│                    ╰────────────╯                                                                                          │
│                           ▲                                                                                                │
│                           │ audio in,                                                                                      │
│                           │ spoken reply back                                                                              │
│             ┌─────────────┼── MAC, ALWAYS ON ────────────────────────────────────────────────────────────────────────────┐ │
│             │             │                                                                                              │ │
│             │  ┌──────────┼── HOME ASSISTANT OS, a virtual machine ────────────────────────────────────────────────────┐ │ │
│             │  │          │                                                                                            │ │ │
│             │  │          │                                                                                            │ │ │
│             │  │   ╭─────────────╮     ╭─────────────╮             ╭─────────────╮               ╭─────────────╮       │ │ │
│             │  │   │    speech   │────▶│    intent   │────────────▶│  our agent, │──────────────▶│   text to   │       │ │ │
│             │  │   │   to text   │     │   matcher   │ no match    │ thin client │  answer       │    speech   │       │ │ │
│             │  │   ╰─────────────╯     ╰─────────────╯             ╰─────────────╯               ╰─────────────╯       │ │ │
│             │  │        │   ▲                 │ play X                  │   ▲                         │   ▲            │ │ │
│             │  │        │   │                 ▼                         │   │                         │   │            │ │ │
│  ╭───────╮  │  │        │   │        ╭─────────────────╮                │   │                         │   │            │ │ │
│  │ Sonos │◀─┼──┼────────┼───┼────────│ Music Assistant │                │   │                         │   │            │ │ │
│  ╰───────╯  │  │        │   │ music  ╰─────────────────╯                │   │                         │   │            │ │ │
│             │  │        │   │                 │                         │   │                         │   │            │ │ │
│             │  │        │   │                 │                         │   │                         │   │            │ │ │
│             │  └────────┼───┼─────────────────┼─────────────────────────┼───┼─────────────────────────┼───┼────────────┘ │ │
│             │     audio │   │ text            │                         │   │                    text │   │ speech       │ │
│             │           ▼   │                 │       question, history │   │ answer,                 ▼   │              │ │
│             │      ╭────────────╮             │                         │   │ streamed           ╭────────────╮          │ │
│             │      │  Whisper   │             │                         │   │                    │   Kokoro   │          │ │
│             │      │ on the GPU │             │                         │   │                    │ the voice  │          │ │
│             │      ╰────────────╯             │                         ▼   │                    ╰────────────╯          │ │
│             │                                 │               ╭──────────────────────╮                                   │ │
│             │                                 │               │ agent harness, new:  │                                   │ │
│             │                                 │               │ loop, guards, memory │                                   │ │
│             │                                 │               ╰──────────────────────╯                                   │ │
│             │                                 │                           │                                              │ │
│             │                                 │           ┌───────────────┴─────────┬───────────────────────┐            │ │
│             │                                 │           │ prompts                 │ tool calls            │ notes      │ │
│             │                                 │           ▼                         ▼                       ▼            │ │
│             │                                 │ ╭──────────────────╮      ╭──────────────────╮    ╭══════════════════╮   │ │
│             │                                 │ │   llama-server   │      │ MCP tool server  │    │   memory vault   │   │ │
│             │                                 │ │ replaces Ollama  │      │ assistant-tools  │    │ notes and index  │   │ │
│             │                                 │ ╰──────────────────╯      ╰──────────────────╯    ╰══════════════════╯   │ │
│             │                                 │                                 │          │                             │ │
│             │                                 │                   ┌─ DOCKER ────┼───────┐  │                             │ │
│             │                                 │                   │             ▼       │  │                             │ │
│             │                                 │                   │        ╭─────────╮  │  └──────────────────┐          │ │
│             │                                 │                   │        │ SearXNG │  │                     │          │ │
│             │                                 │                   │        ╰─────────╯  │                     │          │ │
│             │                                 │                   └─────────────┼───────┘                     │          │ │
│             │                                 │                                 │                             │          │ │
│             └─────────────────────────────────┼─────────────────────────────────┼─────────────────────────────┼──────────┘ │
│                                               │                                 │                             │            │
└───────────────────────────────────────────────┼─────────────────────────────────┼─────────────────────────────┼────────────┘
                                                │                                 │                             │
                             catalogue, stream  │                   search query  │                             │ lookups
                                                ▼                                 ▼                             ▼
                                     ╭─────────────────────╮           ╭─────────────────────╮       ╭─────────────────────╮
                                     │       Spotify       │           │    public search    │       │ weather, Wikipedia, │
  LEAVES THE NETWORK                 │         API         │           │       engines       │       │    sports, Reddit   │
                                     ╰─────────────────────╯           ╰─────────────────────╯       ╰─────────────────────╯
```

## 3. How a question flows, step by step

1. The puck hears "Hey Jarvis" on its own chip and streams the question to Home Assistant, which runs in a virtual machine on the Mac. Whisper turns the audio into text.
2. Home Assistant's intent matcher handles music commands itself. Everything else goes to our conversation agent, which in v2 is a thin client: it sends the question, the conversation's earlier exchanges, and the conversation id to the harness on the Mac, and streams back whatever the harness says.
3. The harness looks up the summaries of past conversations that match the question, asks the router which tools the question needs and in what order, and builds the prompt in a fixed order so that llama-server can reuse most of it from its cache (doc 02).
4. llama-server runs Gemma 4 on the Mac's GPU, reachable only from the Mac itself. When the model asks for tools, the harness speaks a short filler sentence, checks each call against the security rules (doc 12), and runs it on the MCP tool server. A question may take several tool rounds: a forecast, another forecast, then the calculator.
5. A tool result from the open web marks the exchange as untrusted, and so does a past summary that carries that mark. From then on no tool call may carry a private detail out.
6. The answer streams back through the thin client to Kokoro, which speaks it on the puck. As in v1, the puck then listens briefly for a follow-up.
7. When the conversation ends, a separate model call with no tools writes a short summary of it. Code checks the summary, skips conversations with nothing worth keeping, and saves the rest as one note per conversation. A conversation that was marked untrusted keeps the mark on its note.

## 4. What v2 changes, doc by doc

| Doc | v2 | Replaces | What changes |
|---|---|---|---|
| 00 System overview | this doc | v1/00 | The harness on the Mac, milestones, costs, privacy |
| 01 LLM benchmark | to be written | v1/01 | Question set 2.0: several tools per question, memory recall, injection, weather anywhere, sports |
| 02 Inference engine | to be written | v1/02 | llama-server instead of Ollama; serving settings in one file; prompt caching |
| 03 Tool server | to be written | v1/03 | Weather anywhere, sports, a Reddit reader, output hygiene |
| 04 Agent harness | to be written | v1/04 | A Mac service; several tools per question; a context budget per model |
| 05 Voice pipeline | | v1/05 still applies | Unchanged |
| 06 Home Assistant core | | v1/06 still applies | Unchanged, apart from the thin client (doc 04) |
| 07 Music | | v1/07 still applies | Unchanged |
| 08 Hardware and deployment | to be written | v1/08 | Mac mini or Mac Studio; memory budget; ports bound to the Mac where they can be |
| 09 Dev environment | | v1/09 still applies | Unchanged; new packages are listed in each doc |
| 10 Operations | to be written | v1/10 | llama-server and the harness as services; deploy rules |
| 11 Memory | to be written | new | One summary note per conversation, its index, how notes are read |
| 12 Security | [12_security.md](12_security.md) | new | Threat model, trust marks, the guards, supply chain |
| 13 Personal-data tools | to be written | new | Gmail, calendar, X, Reddit, and bank statements |

## 5. Subsystems and their tech stacks

| Subsystem | Doc | Stack | Custom code? |
|---|---|---|---|
| Benchmark | 01 | Python harness, hand-written reference answers, Claude Code subagent as judge | Yes |
| Inference | 02 | llama.cpp `llama-server`, Gemma 4 GGUF weights | Config |
| Tool server | 03 | Our MCP server `assistant-tools`, SearXNG in Docker | Yes |
| Agent harness | 04 | `assistant_core` plus a new service on the Mac; thin Home Assistant component | Yes |
| Voice pipeline | v1/05 | Voice PE puck, Wyoming, Whisper on MLX, Kokoro | Config |
| Home Assistant | v1/06 | Home Assistant OS in a UTM VM | Config |
| Music | v1/07 | Spotify, Music Assistant, Sonos | Config |
| Hardware | 08 | Mac mini or Mac Studio, launchd, Docker Desktop, UTM | Config |
| Operations | 10 | `scripts/services.sh`, `ops/` | Yes |
| Memory | 11 | Markdown notes viewed in Obsidian, SQLite full-text index | Yes |
| Security | 12 | Rules enforced in the harness and the tool server | Yes |

## 6. Open decisions and how they close

| Decision | Closes in | How |
|---|---|---|
| Whether llama-server's tool calling works for Gemma 4 E4B | Before doc 02 | A one-to-two-hour trial on the laptop: one tool call, a multi-turn tool exchange, and cold versus warm time to first token. If it fails, M1 stays on Ollama until a fixed release. |
| The context window per model | M1 | Measured: the memory left free on each machine, and where the benchmark shows answers stay good. v1 used 16,384 tokens; E4B accepts 128K. |
| Which Mac | Doc 08 | Benchmark pass 5 pointed at a 26B or 35B mixture-of-experts model on a 32 GB machine; doc 08 weighs a Mac mini against a Mac Studio. |
| Who keeps the conversation history | Doc 04 | Home Assistant's chat log, or a session store in the harness. |
| Whether oMLX replaces llama-server | M9 | Re-measured on the new Mac, built from source at a pinned commit, against the same benchmark. |

## 7. Costs

| Item | Cost |
|---|---|
| The new Mac | Chosen in doc 08 |
| Software, models, and the new tools' data sources | $0 |
| Agent accounts for Reddit and X | $0 |
| SimpleFIN Bridge for bank data (optional, after the new Mac) | $15 a year |

Running cost stays at a few dollars a month of electricity. The X API, which would cost about $30 a month, is not used: the assistant reads X through its own account (doc 13).

## 8. Privacy boundary

v1's boundary still holds: audio, transcripts, the model, and inference stay on the Mac. v2 adds:

| Data | Where it goes |
|---|---|
| Conversation summaries | A folder on the Mac, outside the repository and never under git, which you open in Obsidian. They are never sent to Home Assistant's chat log, to the tool server, or off the machine. |
| Prompts and model output | llama-server on the Mac, listening only on the Mac itself, not on the network. |
| Place names | Open-Meteo's geocoding service turns "Lisbon" into coordinates; Met.no then gets coordinates rounded to four decimals, as in v1. |
| Sports questions | stats.nba.com, balldontlie, and nflverse's published data files see which players and teams are looked up. |
| Reddit threads | Reddit sees the assistant's own account and which threads it reads. |
| Search queries | As in v1, plus a guard: no query or URL may carry a private detail from memory that you did not say yourself in that exchange (doc 12). |
| Gmail, calendar, X, bank | After the new Mac, each under its own least-privilege access (doc 13). |

## 9. Milestones

Each milestone keeps the benchmark and the product on the same code, and none may lower the scores on the existing question categories (A to E) by more than the run-to-run noise that M1 measures. Each lands as its own plan and pull request, after the design docs.

**Before the new Mac (now to mid-November 2026)**

| # | Milestone | Done when |
|---|---|---|
| M1 | Engine swap: llama-server replaces Ollama, after an Ollama baseline | Question set 1.4 scores at least Ollama's minus noise; malformed tool calls no more often than on Ollama; empty answers rarer than one in seven; median warm time to first token at most half of Ollama's |
| M2 | The harness becomes a service on the Mac; the component becomes a thin client | The same gates through the service; `ops.smoke` passes; the first spoken word comes at most 150 ms later than in-process |
| M3 | Security baseline: trust marks, the egress guard, `fetch_page` provenance, output hygiene | No injected instruction followed and no unprovenanced URL fetched in the injection category |
| M4 | Weather anywhere | Every weather-anywhere question finds the right place and calls the forecast |
| M5 | Several tools per question | A required tool is missed in at most one question in eight of the multi-tool category |
| M6 | Memory v1: a summary per conversation, the full-text index, retrieval, `search_memory` | At least 80% of the memory-recall questions answered right; no untrusted summary saved without its mark and no private detail in a tool call; warm time to first token at most 10% slower |
| M7 | Sports statistics | Answers match the fixture data |

**After the new Mac**

| # | Milestone |
|---|---|
| M8 | Deploy everything on the new Mac |
| M9 | Re-run the engine and model comparison: Gemma 4 26B-A4B, multi-token prediction, oMLX |
| M10 | Memory v2: meaning-based search alongside the full-text index |
| M11 | Personal-data tools, one pull request each: calendar, then Gmail, then Reddit and X, then bank statements |

## 10. Risks

- **Memory on the 16 GB laptop.** llama-server's cache slots, an embedding model later, and the Home Assistant VM must fit together.
- **The small model may not chain tools reliably.** Gemma 4 E4B is widely reported as weak at multi-step tool calling; M5 could miss its target for the model's sake, not the harness's, until the bigger model arrives.
- **Gemma 4 tool-call bugs.** Every engine has had them; the harness keeps malformed calls out of the history and caps retries.
- **Anyone the puck hears can use memory.** There is no speaker identification, so a visitor or a television can ask what was said before. Nothing financial or otherwise sensitive goes into a summary, and you curate the notes.
- **Sports data sources.** nba_api reads an unofficial endpoint that can block home addresses, and both libraries bring large dependencies.
- **Agent accounts.** Reddit and X may suspend an account that reads automatically.
- **Grading.** Memory recall and injection resistance need checks that code can score, not only the judge's opinion.

## 11. Concepts for newcomers

**Harness.** The code around a model: it builds the prompt, offers tools, runs the tools the model asks for, enforces limits, and decides what is remembered. With a small model, a better harness buys more capability than a bigger prompt.

**Prompt cache.** A model reads the whole prompt before writing anything, and on this laptop that costs seconds per thousand tokens. llama-server keeps what it computed for the last prompt and reuses the longest identical beginning, so a prompt that keeps its stable parts first and its changing parts last is mostly free to read again.

**Context window.** The most text the model can consider at once, counted in tokens. A larger window costs memory and time, and small models answer worse well before they reach their advertised limit.

**Retrieval-augmented generation (RAG).** Looking up a few relevant pieces of text and putting them in the prompt before the model answers. `search_and_read` already does this with the web; memory does it with the summaries of past conversations.

**Prompt injection.** Text in a web page, email, or post that tries to give the model instructions ("ignore your rules and…"). No model reliably resists it, so the defence is to limit what an obeyed instruction can reach.

**Untrusted exchange.** An exchange in which text from the open web, an email, or a post entered the prompt, directly or through a past summary that carries the mark. The mark limits what that exchange may send out.

**GGUF.** The file format llama.cpp loads model weights from. Unlike older Python formats, loading it cannot run code.

## 12. Sources

- Gemma 4 prompt and tool-call format: [ai.google.dev](https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4)
- llama.cpp server, its prompt cache and slots: [llama.cpp server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- Gemma 4 E4B prefill and decode speeds on Apple Silicon under Ollama: [ai-muninn, 2026-04-07](https://ai-muninn.com/en/blog/dgx-spark-gemma4-e2b-vs-e4b-ollama-3-machines)
- Meta, "Agents Rule of Two": [ai.meta.com](https://ai.meta.com/blog/practical-ai-agent-security/)
- Sports Reference terms of use and bot policy: [terms](https://www.sports-reference.com/termsofuse.html), [bot traffic](https://www.sports-reference.com/bot-traffic.html)
- Open-Meteo geocoding: [open-meteo.com](https://open-meteo.com/en/docs/geocoding-api)
- Doc 12 lists the security sources.
