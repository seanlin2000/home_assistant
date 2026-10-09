# 02. Inference engine

Status: building

## 1. Purpose

Run the model on the Mac with every serving setting in our hands. v1 served Gemma 4 through Ollama, which was quick to start with but hid the settings that decide latency on this hardware: how much of each prompt is reused from the last one, how the context is shared, and how much memory the cache may take. v2 serves the model with llama.cpp's `llama-server` instead, keeps every one of its settings in one checked-in file, and fixes the order of the prompt so that the part the model has already read is never read again. On this laptop, reading the prompt costs about six seconds and writing the answer one or two, so the order of the prompt matters more than the choice of engine. v1/02 still explains how a model occupies memory and why mixture-of-experts models suit the Mac; this doc covers what changes.

## 2. Diagram

```
 ONE REQUEST TO LLAMA-SERVER, in the order the model reads it

 ╭──────────────────────╮            ╭───────────────────────╮           ╭──────────────────────╮            ╭──────────────────────╮
 │     system rules     │            │    tool definitions   │           │  earlier exchanges   │            │    this question     │
 │     never change     │────────────│ change with the tools │───────────│  questions, answers  │────────────│  date, plan, notes   │
 │     ~900 tokens      │            │     ~1,400 tokens     │           │  grow by ~100 each   │            │  ~50 to 450 tokens   │
 ╰──────────────────────╯            ╰───────────────────────╯           ╰──────────────────────╯            ╰──────────────────────╯
 └──────────────────────────────────────────────────────────────────────────────────────────────┘            └──────────────────────┘
                     already in the cache from the last request: about 0.1 s                                read fresh: 0.2 to 1.3 s


 TWO SLOTS SHARING ONE KV POOL: the router and the summaries never push the conversation out

                                                                        ╭──────────────────────╮
                                            quiet requests              │        slot 1        │
                                         ┌─────────────────────────────▶│  router, summaries   │
 ╭──────────────────────╮                │                              │   ~400 tokens each   │
 │     the harness      │                │                              ╰──────────────────────╯
 │  pins every request  │────────────────┤
 │     to its slot      │                │                              ╭──────────────────────╮
 ╰──────────────────────╯                │                              │        slot 0        │
                                         └─────────────────────────────▶│   the conversation   │
                                            response requests           │ ~2,400 tokens and up │
                                                                        ╰──────────────────────╯
```

## 3. How it works, step by step

### 3.1 One request

1. A launchd agent starts `llama-server` with the flags built from `config/serving.toml` (3.5). The server loads the GGUF file once, listens on `127.0.0.1` only, and refuses any request without the API key.
2. The harness sends a chat request to `/v1/chat/completions`: the messages, the tool definitions, and the sampling settings, with streaming on.
3. llama-server applies Gemma 4's own chat template (`--jinja`). The template writes the system text first and the tool definitions after it, in the same opening turn, then each message in order.
4. Before reading anything, the server compares the new prompt with the prompts it has cached, token by token, and keeps the longest identical beginning. Only the tokens after that point are read. This is the prefix cache.
5. It reads the new tokens (the prefill), then writes the answer one token at a time (the decode). A tool call comes back as a structured `tool_calls` field, parsed from Gemma's tool-call tokens.
6. The last streamed chunk carries `timings`: how many prompt tokens were read fresh (`prompt_n`), how many came from the cache (`cache_n`), and how long each phase took. The harness records them for every llama.cpp request (doc 04).

### 3.2 What the trial measured

Before writing this doc, a one-hour trial on the laptop (an M1 Pro with 16 GB) ran llama-server 0.6.0 from homebrew-core with Gemma 4 E4B, using the real system prompt and the live tools from `assistant-tools`, against Ollama 0.33.3 with the same model. Every tool call came back well formed, including a second tool call in the same conversation, with no tool-call tokens leaking into the text.

The speeds were close:

| Measure | llama-server | Ollama |
|---|---|---|
| Reading a 2,344-token prompt from nothing | 6.35 s (about 370 tokens a second) | 5.85 s |
| Reading the same prompt plus a new question | 0.07 to 0.23 s (5 to 39 new tokens) | 0.15 to 0.19 s |
| Reading a 654-token tool result | 1.82 s | not measured |
| Writing the answer | about 41 tokens a second | about 43 tokens a second |

So the engine itself buys little speed. What costs time is how often the prompt has to be read from nothing. A run of the real v1 loop on Ollama, router included, found that the first llama.cpp request of most questions re-read about 2,400 tokens, and the first spoken word came 7.9 to 12.4 seconds after the question. Two things in v1 throw the cache away on every question:

- **The router's own request.** It sends a different, shorter prompt, and Ollama keeps only the last prompt, so the chat prompt is gone by the time the response request arrives.
- **The route directive.** `apply_route` (`assistant_core/router.py`) appends "Routing for this question: …" to the system text. The tool definitions come after the system text, so everything from the directive on, tools and history included, has to be read again.

Both are fixed by the order of the prompt (3.3) and by giving the router its own slot (3.4), not by a faster engine. That is why M1's exit criterion is the time to the first spoken word and how many tokens the first llama.cpp request of each question reads fresh, not raw speed (v2/00 §9).

### 3.3 The order of the prompt

The cache keeps only the identical beginning of a prompt, so the prompt is laid out from what never changes to what changes on every question:

| Order | Part | Size today | Changes when |
|---|---|---|---|
| 1 | System rules: persona, brevity, when to search, unclear input | 883 tokens | The prompt version changes |
| 2 | Tool definitions, in a fixed order | 1,431 tokens for 12 tools | A tool is added or its description changes |
| 3 | Earlier exchanges of this conversation, your words and the answers exactly as before | about 100 tokens each | Each exchange adds one; compaction rewrites them (doc 04) |
| 4 | The per-question block: today's date, the router's plan, and the matching summaries from memory | 50 to 450 tokens | Every question |
| 5 | Your question | a few tokens | Every question |

What this changes from v1:

- **The date moves out of the system rules.** In v1 it is on the second line of the system prompt (`prompts.system_prompt`), so the whole prompt is read from nothing once a day. In the per-question block it costs about 25 tokens a question, and the first 2,300 tokens never change, so the harness can read them once at startup.
- **The route directive becomes part of the per-question block.** It no longer touches the system text.
- **Earlier per-question blocks are dropped.** They are not replayed, so the prompt of the next question departs from the previous one where the old block was, and the last exchange is read again. Replaying old blocks would avoid that but would fill the window with stale plans and notes. In a test of six follow-up questions with a 170-token block, each question read about 200 tokens fresh, and the first token came 0.72 s after the request. The block itself is most of that cost, so it is kept short: summaries only when they match well, and a one-line plan.
- **Tool rounds only ever add to the end.** Within one question, the tool call and its result are appended, so each round reads only the result.

How far back the cache can step is limited by Gemma 4's design. Most of its layers attend only to the last 512 tokens (a sliding window), and the server keeps only that window's cache for those layers. So the cache cannot simply step back to any earlier point: it needs a saved checkpoint at or before the point where the new prompt departs from the old one. llama-server creates checkpoints at the start of each user message and near the end of every prompt (`--ctx-checkpoints`, 32 per slot), which covers both cases this design produces:

- A dropped per-question block departs at the start of the previous user message, where a checkpoint is. In the test above, none of the follow-ups fell back to a full re-read.
- Compaction rewrites the history from the first exchange, at a user message too, so only the history after it is read again.

When the server does have to read everything again, it logs "forcing full prompt re-processing", and the health check counts those lines (doc 10). `--swa-full` keeps the full cache for every layer instead, so no checkpoint is needed. It saved 90 ms per follow-up in the test and cost about 200 to 350 MB of memory, so it stays off on the laptop and is measured again on the new Mac.

### 3.4 Two slots in one shared pool

A slot is one lane for a request: its own place in the KV cache and its own sampling state. The model's weights are loaded once and shared by every slot. Several llama.cpp requests send prompts that look nothing like the conversation: the router (357 tokens), and later the conversation summaries, compaction, and the quarantined reader (doc 12 §3.6). In a single slot, each of them pushes the conversation out, and it has to come back from somewhere.

Five setups were timed on the laptop, alternating the real router prompt with a growing conversation. The times are from sending the request to receiving the first token, the median over five follow-up questions:

| Setup | Router | Conversation | Process memory |
|---|---|---|---|
| One slot; the prompt cache in RAM swaps the two prompts in and out | 0.23 s | 0.27 s | 6.0 GB |
| Two slots with separate KV caches, each request pinned to its slot | 0.22 s | 0.20 s | 6.1 GB |
| Two slots with separate KV caches, not pinned | 0.18 s | 0.19 s | 6.5 GB |
| Two slots sharing one KV pool, pinned, with the default `--cache-idle-slots` | 1.06 s, a full re-read | 6.2 s, a full re-read | 5.7 GB |
| Two slots sharing one KV pool, pinned, with `--no-cache-idle-slots` | 0.13 s | 0.17 s | 5.8 GB |

The fourth row is a known llama.cpp bug, met through two default behaviours:

1. With a shared pool and `--cache-idle-slots` (the default), whenever a request starts, every idle slot is copied to the prompt cache in RAM and then emptied.
2. A request pinned to a slot with `id_slot` skips the step that restores the best match from the RAM cache when that slot is empty. The code divides the slot's cached tokens by its length, 0 by 0, and the result fails the "should I restore?" test. This is llama.cpp issue 28139, with a fix (PR 28992) still open.

So every pinned request found its slot emptied by the previous request and read everything again.

v2 uses the last row:
- **Slots and pool.** Two slots share one pool of 18,432 tokens (`-c`): 16,384 for the conversation and 2,048 for the quiet requests.
- **Idle slots stay put.** With `--no-cache-idle-slots`, an idle slot keeps its cache where it is instead of being copied out and emptied.
- **Pinning.** The harness pins the conversation to slot 0 and every quiet request to slot 1, so a summary never pushes the conversation out.
- **The RAM cache stays on, at 1 GiB.** It holds the router's prompt while slot 1 writes a summary, and brings it back afterwards.
- **Warm-up.** After a restart, both slots and the RAM cache are empty. The harness therefore sends one warm-up request per slot at startup: the system rules and tools to slot 0, the router prompt to slot 1. The empty-slot bug never costs a question, and the first question of the day reads about 200 tokens instead of 2,500.

The two slots share the GPU. A summary running in slot 1 while a question runs in slot 0 slows both, so the harness still pauses background requests while a question is in progress (doc 04 §3.7).

### 3.5 Serving settings in one file

Every llama-server setting lives in `config/serving.toml`, checked into the repository, with one table per model. Nothing is set through environment variables or by hand on the command line. This is what the file looks like for the model running today:

```toml
[server]
host = "127.0.0.1"
port = 8090
api_key_file = "~/Library/Application Support/studio-assistant/llama-server.key"
model = "gemma-4-e4b"                       # which table below is served

[models.gemma-4-e4b]
gguf = "~/models/gguf/gemma-4-E4B_q4_0-it.gguf"
source = "google/gemma-4-E4B-it-qat-q4_0-gguf"
revision = "4b4a2c1d584be7264f87aac328a1bc739ce81b6c"
sha256 = "676c35070db6dbe52f93e9c864ee0fba4eddea94b9c875d9cb10daff453fbaee"
context_tokens = 18432                      # -c, the pool both slots share
conversation_tokens = 16384                 # slot 0's share; the harness budgets against it
slots = 2                                   # -np
kv_unified = true                           # --kv-unified
cache_idle_slots = false                    # --no-cache-idle-slots
gpu_layers = "all"                          # -ngl
flash_attention = "on"                      # -fa
prompt_cache_mib = 1024                     # -cram
reasoning = "off"                           # --reasoning
swa_full = false                            # --swa-full

[models.gemma-4-e4b.sampling]               # defaults; the harness may override per request
temperature = 0.7
max_output_tokens = 600
```

A small launcher, `uv run serving launch`, reads the file, checks that the GGUF file's SHA-256 matches, and replaces itself with `llama-server` and the flags below, so launchd supervises the server directly (doc 10). The file accepts only the keys it knows: a misspelt key, or a flag that is not in the table below, stops the launch rather than being passed through. `uv run serving show` prints the exact command the launcher would run, with the key file's path but never the key, and the model's hash check.

The flags, with the value for Gemma 4 E4B on the laptop and the reason:

| Flag | Value | Why |
|---|---|---|
| `-m` | the GGUF path | From the model's table; launch stops if its SHA-256 does not match |
| `--host`, `--port` | `127.0.0.1`, `8090` | Only the harness, on the same Mac, talks to the model (doc 12 §3.9). 8090 avoids Ollama's 11434 while both exist during M1 |
| `--api-key-file` | a file outside the repository, readable only by you | Keeps the key off the command line, out of `ps`, and out of the launchd file; the harness reads the same file |
| `-c` | `18432` | The KV pool in tokens, shared by both slots: 16,384 for the conversation, v1's own window and not the model's 128K limit, plus 2,048 for the quiet requests. M1 sets it per machine from memory and from where the benchmark's answers stay good (doc 04) |
| `-np` | `2` | Slot 0 for the conversation, slot 1 for the router and the quiet requests (3.4). The default, "auto", would choose for us |
| `--kv-unified` | on | One pool for both slots, so the quiet slot uses only what its short prompts need |
| `--no-cache-idle-slots` | set | Keeps an idle slot's cache in place. The default copies idle slots to RAM and empties them whenever a request starts, which with pinned slots throws the cache away (3.4) |
| `-ngl` | `all` | Every layer on the GPU |
| `-fa` | `on` | Flash attention: 2% faster prefill and 3 to 4% faster decode on the laptop (3.9) |
| `-cram` | `1024` | The prompt cache in RAM, capped in MiB. It holds the router's prompt while slot 1 writes a summary. The default is 8 GiB, more than half the laptop's free memory |
| `-b`, `-ub` | defaults, `2048` and `512` | Larger batches did not speed up prefill on the laptop (3.9) |
| `-ctk`, `-ctv` | default, `f16` | An 8-bit KV cache saved memory but slowed decode by 19 to 27% (3.9) |
| `--jinja` | on (the default) | Uses the chat template inside the GGUF file, which carries Gemma 4's tool-call format |
| `--reasoning` | `off` | No hidden thinking before answering; it multiplies latency (v1/02 §7) |
| `--no-ui` | set | Turns off the built-in web chat page and the MCP proxy that comes with it; the harness is the only client |
| `--metrics` | set | A Prometheus endpoint, behind the API key, for the health check (doc 10) |
| `--cache-reuse` | not set | Reuses cached chunks that moved within the prompt. Gemma 4's sliding-window layers do not support it, and the server switches it off with a warning |
| `--swa-full` | not set | Keeps the full cache for the sliding-window layers, so no checkpoint is needed to step back. 90 ms faster per follow-up for about 300 MB; measured again on the new Mac (3.3) |
| `--ctx-checkpoints`, `--checkpoint-min-step` | defaults, `32` and `8192` | Checkpoints are made at user messages regardless of the minimum step; setting it to 0 changed nothing in the test |
| `--tools`, `--mcp-servers-config`, `--media-path`, `--slot-save-path`, `--props` | never set | These let the server run shell commands, read files, call MCP servers, or change its own settings. The launcher refuses them |

The file also has tables for two larger models that only the benchmark uses: Gemma 4 26B-A4B and Qwen 3.6 35B-A3B, both unsloth's UD-IQ4_XS (13.6 and 17.7 GB). Neither fits in the laptop's 16 GB, so they run with `gpu_layers = 0`, every layer on the CPU. Measured on 2026-10-09:

| Layout | What happened |
|---|---|
| Any layer on the GPU, even with only the experts on the CPU (`--cpu-moe`) | Metal maps the whole memory-mapped file into its working set, past the recommended limit, and the load hangs inside Metal's residency sets |
| GPU without residency sets (`GGML_METAL_NO_RESIDENCY=1`) | Loads, but every request fails with a compute error |
| GPU with no memory map (`--load-mode none`) | The experts' weights go to swap, and prompts are read at 6 tokens a second |
| CPU, file memory-mapped | macOS drops the experts' pages and reads them again from the SSD as needed. Prompts are read at about 25 tokens a second (Gemma) and 18 (Qwen), and answers written at 2 to 9 |

These speeds say nothing about the new Mac, where the whole model fits on the GPU; only the answers' quality carries over.

### 3.6 Gemma 4's tool calls

Gemma 4 writes a tool call as special tokens, and every engine has had bugs parsing them. The trial found none in llama-server 0.6.0; M5 found one (below). The load log warns that two of the model's tokens (`<|tool_response>` and `</s>`) are mislabelled in the file and corrects them. The harness keeps its v1 protections whatever the engine:

- A tool call that cannot be parsed is not added to the history, so a broken turn never teaches the model a broken format (doc 04).
- A completion with neither text nor a tool call is retried once, as in v1 (v1/04 §14).
- The chat template is the one inside the GGUF file. When a llama.cpp or model upgrade is considered, `/apply-template` shows the rendered prompt so the change is visible before the benchmark runs.

**Text arguments cut short.** Gemma 4 E4B sometimes writes a text argument without its `<|"|>` string delimiters, and llama-server's parser then keeps only the leading number: `"64.50 * 0.18"` arrives as `64.5`. llama.cpp's newest build at the time (b11515) does the same. The tool guard refuses such a call and tells the model to quote the whole expression (doc 04). The fix at the source would be our own parser for Gemma's tool-call text over `/completion`.

**Result, 2026-10-09** (run `large_models_run1`; every candidate read the same cached search results and forecasts): the fault belongs to the small model, and it costs E4B about 16 of 600 points.

| Candidate | Calculator calls | Cut short | Category C | Total |
|---|---|---|---|---|
| Gemma 4 E4B | 11 | 5, in C23 (4) and C26 (1) | 36 of 60 | 417 of 600 |
| Gemma 4 26B-A4B, CPU only (3.5) | 18 | 0 | 44 of 60 | 443 of 600 |
| Qwen 3.6 35B-A3B, CPU only (3.5) | 20 | 0 | 60 of 60 | 473 of 600 |
| Claude Opus 5.5, hand-written ceiling | 15 | 0 | 60 of 60 | 568 of 600 |

On E4B the cut-short calls zeroed C23 (four refusals in a row, then too many tool calls) and cost C26 six points. The 26B model's two weak C answers were an empty reply after a correct calculation (C23) and a wrong use of the growth tool (C24), not lost arguments.

### 3.7 The bake-off (M1)

M1 replaces Ollama only after measuring both engines on the same questions:

1. Run question set 1.4 on Ollama with v1's prompt order, as the baseline, three times to measure the run-to-run noise.
2. Run it on llama-server with the v2 prompt order, three times.
3. Compare, per question and overall:
   - the benchmark score and the gate failures;
   - malformed tool calls and empty completions;
   - the time to the first spoken word, median and slowest tenth;
   - the tokens each llama.cpp request reads fresh and those served from the cache, from `timings.prompt_n` and `timings.cache_n`;
   - the decode speed.

M1 is done when the score is at least Ollama's minus the noise, tool calls are malformed no more often, empty completions stay below one in seven, the median time to the first spoken word is at most half of Ollama's, and in at least nine questions out of ten the first llama.cpp request reads no more than 600 prompt tokens fresh (v2/00 §9). The last measure is per first request rather than a share of all prompt tokens, because a search result is always new text: a question that reads a 2,700-token result cannot be mostly cached however well the prompt is ordered. Ollama stays installed until M1 closes, and is removed afterwards.

**Result, 2026-10-08** (`benchmark/results/m1_bake_off.md`, runs `m1_run1` to `m1_run3`): four of the five criteria are met.

| Criterion | Ollama | llama-server | Met |
|---|---|---|---|
| Score, mean of three runs | 221.0, noise band 11 | 228.0 | Yes |
| Exchanges with a malformed tool call | 0 of 117 | 1 of 117 | No |
| Exchanges with an empty completion | 2 of 117 | 0 of 117 | Yes |
| Median first spoken word | 3.66 s | 1.04 s | Yes |
| First requests reading at most 600 tokens fresh | not reported by Ollama | 117 of 117 | Yes |

The one malformed call is a repetition loop: the model repeated one sum inside a calculator call until the 600-token output cap cut it off. Two other findings come from the judge:
- **The date is spoken.** In 12 of 117 exchanges on llama-server, against 2 on Ollama, the answer reads the date from the per-question note aloud.
- **Arithmetic is weaker.** Category C fell from 46 to 36 on average, still inside its noise band of 14, through wrong calculator arguments (an annual rate used as monthly, arguments swapped).

### 3.8 Why llama-server, and what waits for the new Mac

| Engine | What it does well | Why not now |
|---|---|---|
| Ollama | Simple, and v1 runs on it | Hides the cache, the slots, and the context sharing; keeps only the last prompt, so the router evicts the chat prompt; listens on the network in v1 |
| llama-server | Prompt cache in RAM, every setting exposed, JSON-schema output for the router and the summariser, API key, homebrew-core build | Chosen |
| mlx-lm's server | About 1.4 times faster decode on Apple Silicon | Its own docs call the server unsuited to production; its prompt cache is in memory only and simpler |
| oMLX | A cache kept on SSD, so long conversations stay warm even across restarts; OpenAI-compatible | A young project with weekly releases; re-measured on the new Mac in M9, built from source at a pinned commit |

Deferred to the new Mac (M9): multi-token prediction and other speculative decoding (3.9), and serving Gemma 4 26B-A4B for real. The laptop can only run it, and Qwen 3.6 35B-A3B, on the CPU for the benchmark (3.5, 3.6).

### 3.9 What else changes the speed on this Mac

Every setting below was measured on the laptop with `llama-bench` or the slot test, except speculative decoding:

| Setting | Measured | Decision |
|---|---|---|
| Batch size (`-ub` 256 to 2048) | Prefill 401 to 410 tokens a second, with no trend | Keep the default, 512 |
| Flash attention | Prefill 409 against 402 tokens a second, decode 44.4 against 42.9 | On |
| 8-bit KV cache (`-ctk`, `-ctv q8_0`) | Prefill unchanged; decode 36 against 44 tokens a second, and 29 against 40 with 8,192 tokens already in context | Keep f16 |
| A context already holding 8,192 tokens | Prefill falls from 420 to 321 tokens a second, decode from 44 to 40 | The budget keeps prompts short (doc 04 §3.4) |
| `--swa-full` | 90 ms less per follow-up, 200 to 350 MB more memory | Off on the laptop |
| Warm-up at startup | The first question reads about 200 tokens instead of 2,500, saving about 6 s | The harness does it (3.4) |
| Speculative decoding with Gemma 4's own drafter (`--spec-type draft-mtp`) | Not measured. llama.cpp supports the E4B drafter since June 2026, but reports only a 1 to 2 tokens-a-second gain for it, and large gains only for the dense 31B model; tool-call parsing has broken with it | Measured with the bigger model in M9 |

The prefill rate is fixed by the chip, at about 400 tokens a second on the laptop. That is why the design spends its effort on reading fewer tokens rather than reading them faster. The GPU neural accelerators in the M5 and M6 chips raise prefill three to four times (v1/02 §6), a larger change than any setting here.

## 4. Packages and tools, and what each does for the business logic

| Package or tool | Role |
|---|---|
| llama.cpp (`llama-server`), homebrew-core, pinned | Serves the model: reads the prompt, keeps the prompt cache, parses tool calls, forces JSON output when asked |
| Gemma 4 E4B, QAT 4-bit GGUF from `google/` | The model, 5.2 GB on disk, pinned by revision and SHA-256 |
| `httpx` (already a dependency) | The harness's client for llama-server's HTTP API (doc 04); no `openai` or `litellm` package |
| `tomllib` (standard library) | Reads `config/serving.toml` |
| `hashlib` (standard library) | Checks the GGUF file's SHA-256 before launch |

## 5. Configuration we control

- `config/serving.toml`: the server's address and key file, and one table per model with its file, source, revision, hash, the flags in 3.5, and sampling defaults. A change to it restarts llama-server (doc 10).
- The API key file, generated once at install and kept outside the repository.
- The order of the prompt (3.3), which lives in the harness's prompt builder (doc 04), not in the server.

## 6. Failure modes

| Failure | What happens | What to do |
|---|---|---|
| The GGUF file's hash does not match | The launcher refuses to start llama-server and says why | Download the file again from the pinned revision |
| A key in `serving.toml` is unknown | The launcher stops with the key's name | Fix the spelling, or add the flag to the launcher deliberately |
| The prompt cache is too small | `cache_n` falls, and the first spoken word is late after a router request | Raise `prompt_cache_mib`, within the memory budget in doc 08 |
| Compaction or a dropped block forces a full re-read | One slow answer after compaction | Turn on `swa_full` if M1 shows it often |
| The model or llama.cpp is upgraded and tool calls break | Malformed calls rise in the benchmark | Pin back the previous version; upgrades go through the benchmark first |
| Not enough memory for the window | llama-server fails to load or the Mac swaps | Lower `context_tokens`; doc 08 has the budget |
| llama-server is down | The harness answers "I can't reach the model right now" and the health check reports it | `scripts/services.sh restart llama` (doc 10) |

## 7. Concepts for newcomers

**llama.cpp request.** One round trip from the harness to llama-server: one prompt sent, one reply back. A question makes several: the plan, one response request per tool round, and later the summary. Not to be confused with a tool call, which is the model's reply asking the harness to run a tool; the tool runs on the tool server, not in llama-server.

**Prefill and decode.** The model first reads the whole prompt (prefill), which is limited by the GPU's arithmetic, then writes the answer one token at a time (decode), which is limited by memory speed. On this laptop prefill runs at about 370 tokens a second and decode at about 41, so a long prompt costs more than a long answer.

**KV cache.** While reading a prompt, every attention layer computes a key and a value for each token. Writing the next token needs all of them, so they are kept in memory for the request. It grows with the length of the context, which is why the window size costs memory.

**Prefix cache, or prompt cache.** Keeping the KV cache after a request ends, so a later prompt that starts with the same tokens skips reading them. It is not separate data, just reuse of the KV cache. It only works for the identical beginning: change one token and everything after it is read again.

**Slot.** One lane for a request in llama-server, with its own place in the KV cache. The model's weights are loaded once and shared by every slot. With a shared pool (`--kv-unified`), the slots draw their KV cache from one block of memory sized by `-c`.

**Checkpoint.** A saved copy of the sliding-window layers' cache at one point in the prompt, so the server can step back to that point without reading the prompt again.

**Speculative decoding.** A small, fast model guesses the next few tokens and the main model checks them all in one pass. When the guesses are right, several tokens come for the price of one.

**Sliding-window attention.** Most of Gemma 4's layers look only at the most recent tokens instead of the whole context. It saves memory and time, but the server keeps less of the cache for those layers, which limits how far back a prompt can be changed without a re-read.

**Chat template.** The rules, shipped inside the model file, that turn a list of messages and tools into the exact text and special tokens the model was trained on.

## 8. Sources

- llama.cpp server: its endpoints, `timings`, `cache_prompt`, `/apply-template`, and `/tokenize`: [llama.cpp server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- The prompt cache in RAM (`--cache-ram`): [llama.cpp PR 16391](https://github.com/ggml-org/llama.cpp/pull/16391)
- Context checkpoints for sliding-window models: [llama.cpp PR 15293](https://github.com/ggml-org/llama.cpp/pull/15293); checkpoints before the latest user message: [PR 22929](https://github.com/ggml-org/llama.cpp/pull/22929)
- A request pinned to an empty slot skips the prompt cache: [llama.cpp issue 28139](https://github.com/ggml-org/llama.cpp/issues/28139), fix in [PR 28992](https://github.com/ggml-org/llama.cpp/pull/28992); the slot selection code: [server-context.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/server-context.cpp)
- Gemma 4's sliding windows, 512 tokens for E2B and E4B: [huggingface.co/blog/gemma4](https://huggingface.co/blog/gemma4)
- Gemma 4 multi-token prediction drafters in llama.cpp: [PR 23398](https://github.com/ggml-org/llama.cpp/pull/23398) (31B and 26B-A4B), [PR 24282](https://github.com/ggml-org/llama.cpp/pull/24282) (E2B and E4B); tool-call parse failures with it: [issue 25072](https://github.com/ggml-org/llama.cpp/issues/25072)
- The full-size sliding-window cache (`--swa-full`): [llama.cpp PR 13194](https://github.com/ggml-org/llama.cpp/pull/13194)
- Gemma 4 prompt and tool-call format: [ai.google.dev](https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4)
- The model file: [google/gemma-4-E4B-it-qat-q4_0-gguf](https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf)
- oMLX: [github.com/jundot/omlx](https://github.com/jundot/omlx)
- The flag list is `llama-server --help` for version 0.6.0 (build 11429); the speed figures are from `llama-bench` on the laptop, 2026-10-08.
