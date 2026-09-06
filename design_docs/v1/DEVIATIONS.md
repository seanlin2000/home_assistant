# Deviations from v0

Every place the build departed from the frozen design in `design_docs/v0/`, with the reason. Grouped by the design doc the deviation mainly changes, oldest first within each group. **Part of the system** names the concrete component that moved; **Also touches** lists other docs affected. To add an entry, put it under the doc it mainly changes, not at the bottom of the file.

| Section | Entries |
|---|---|
| [01 LLM benchmark](#01-llm-benchmark) | 9 |
| [02 Local LLM](#02-local-llm) | 1 |
| [03 Web search MCP](#03-web-search-mcp) | 4 |
| [04 Conversation agent](#04-conversation-agent) | 5 |
| [05 Voice pipeline](#05-voice-pipeline) | 1 |
| [06 Home Assistant core](#06-home-assistant-core) | 2 |
| [08 Hardware and deployment](#08-hardware-and-deployment) | 1 |
| [09 Dev environment](#09-dev-environment) | 3 |

## 01 LLM benchmark

| Date | Part of the system | Also touches | Deviation | Why |
|---|---|---|---|---|
| 2026-09-05 | Judge (Anthropic API) | | The frontier baseline and judge cannot run at temperature 0: Claude Opus 5 rejects sampling parameters. The judge uses structured output (a JSON schema the response must validate against) at the API's default settings instead. | API constraint, not a design choice. |
| 2026-09-05 | Frontier baseline | | The frontier baseline runs with adaptive thinking on rather than off. | Opus 5 has thinking on by default and disabling it causes tool calls to leak into visible text. The baseline is the quality ceiling, not a purchase candidate, so its latency is not compared. |
| 2026-09-05 | Question set | | The question set is version 1.1 with 22 questions: A11 (settled history that sounds current) and B21 (false current premise) were added before the first run at the user's request. Maximum is 220 per model, 110 per category. | The v1.1 candidates were ready and the user chose to include them now. |
| 2026-09-05 | Candidate models | 07 | Gemma 4 E4B runs from Ollama's `gemma4:e4b-it-qat` tag (6.1 GB, Google's quantization-aware int4), not a 4.5 GB Q4 file; Ollama's default `gemma4:e4b` is 9.6 GB. | The 4.5 GB figure in v0 was wrong for Ollama's builds; the QAT build is the best quality per gigabyte that fits. |
| 2026-09-05 | Cost tracking | | Every paid API call records its token usage; the judge prints spend per candidate and the report prints the run total. | The user is paying from a small prepaid balance and asked for spend to be tracked. |
| 2026-09-06 | Manual reference candidate | | A `manual` candidate type and `benchmark-manual` command: answers written by hand (by Claude Fable 5.1 in the coding session) are replayed through the real agent loop and search tool, then judged like any model. | The user asked for a sense of the maximum achievable score on the question set; replaying through the loop keeps the gates, word cap, and judge identical, and the transcripts carry the genuine search excerpts. It is labelled a reference, not a purchase candidate. |
| 2026-09-06 | Candidate models | | Qwen 3.6-27B dense joins the candidate list as a Q3_K_S preview (12.4 GB; Unsloth publishes no IQ3_XXS for this model). Gemma 4 31B and NVIDIA Nemotron 3 Nano were researched and not added. | User decision: only the 27B was worth the run time; the dense model will spill past the default GPU ceiling, so its latency is flagged and only its quality counts. |
| 2026-09-06 | Question set | | Question set 1.2 adds category C, six explicit arithmetic questions, and an expected route per question. | To measure the calculator and the router directly, not only through A2 and A7. |
| 2026-09-06 | Report | | Pass 2 writes to its own dated folder; `benchmark-report --compare` adds a table against an earlier pass restricted to shared questions, and the report scores the router separately. | The user asked that the first report never be overwritten and that the router's classification accuracy be measured on its own. |

## 02 Local LLM

| Date | Part of the system | Also touches | Deviation | Why |
|---|---|---|---|---|
| 2026-09-05 | Ollama thinking mode | 01 | Ollama runs Gemma 4 with thinking on by default and gpt-oss ignores `think: false`; every local candidate now sets `think` explicitly (`false` for Gemma 4 and Qwen, `low` for gpt-oss), and the client records the thinking text. | The first Gemma 4 E4B run spent its whole 600-token output budget thinking and returned empty answers. |

## 03 Web search MCP

| Date | Part of the system | Also touches | Deviation | Why |
|---|---|---|---|---|
| 2026-09-05 | MCP server lifecycle | 01 | The benchmark harness starts the MCP server itself as a subprocess with a per-run cache directory, instead of relying on a separately started server. | One command per run; the cache is guaranteed to be per run. |
| 2026-09-05 | MCP SDK | 04 | The `mcp` Python package (the MCP SDK, running on Python 3.12) released its major version 2 between design and build: the server class is now `MCPServer` (was FastMCP) and the client is `mcp.client.client.Client`, which accepts a URL or an in-process server object. | Library moved between design and build; the in-process client made the tool server testable without sockets. |
| 2026-09-05 | Page extraction | | Page extraction keeps HTML tables. | The first smoke test dropped the rate table from the Federal Reserve's H.15 page, which is exactly the fact the model searched for. |
| 2026-09-06 | Calculator tools | 01, 04 | The MCP server also serves eight deterministic calculator tools (`calculator_mcp`), and the system prompt (version 1.2) tells the model never to do multi-step arithmetic itself. | Every local model set up A2 correctly and then miscomputed the digits. A whitelisted expression evaluator plus a few spoken-question-shaped helpers (percent, convert, growth schedule, energy cost, loan, break-even, dates) moves the digits out of the model. One server and one port keep the component's configuration unchanged. |

## 04 Conversation agent

| Date | Part of the system | Also touches | Deviation | Why |
|---|---|---|---|---|
| 2026-09-06 | HA component, MCP client | 03 | The Home Assistant component talks to `web_search_mcp` through `assistant_core/mcp_http.py`, a small httpx-only client for the MCP streamable-HTTP transport, instead of the `mcp` package. | Home Assistant pins its own `mcp` release for its built-in MCP integration, and its API differs from the 2.x client the benchmark uses; the protocol subset we need (initialize, tools/list, tools/call) is under 100 lines and avoids a dependency conflict inside Home Assistant's Python environment. |
| 2026-09-06 | Model clients | 01 | The frontier-model client moved to `assistant_core/anthropic_client.py`; `assistant_core/llm_client.py` imports only `ollama`. | The component vendors `assistant_core` into Home Assistant, where the `anthropic` package is neither installed nor wanted. |
| 2026-09-06 | HA component, conversation history | 06 | In Home Assistant, earlier turns are replayed to the model as spoken text only (user and assistant messages); tool calls and retrieved excerpts from earlier turns are not carried into the next turn. The benchmark's two-turn question keeps the full transcript. | Home Assistant's chat log stores the streamed assistant text; re-sending kilobytes of old search excerpts on every follow-up would cost prompt-processing time on every turn for little benefit. Noted as a difference between benchmark and product. |
| 2026-09-06 | HA component, testing | 09 | The component is not tested with `pytest-homeassistant-custom-component`. Its Home-Assistant-free logic lives in `adapter.py` and is unit-tested by loading that file directly; the Home-Assistant-bound entity and config flow are verified by loading them in the real Home Assistant OS VM. | Home Assistant 2026 requires Python 3.13 and pins hundreds of packages (including an `httpx` major version that conflicts with the `anthropic` SDK), so it cannot share the project's 3.12 lock file. A second environment just for that test harness was judged not worth it for a two-file adapter. |
| 2026-09-06 | Agent loop, question router | 01 | A router decides search / calculate / answer before the model's first call (rules first, then one structured-output call to the same model) and appends a bracketed directive to the user message. Applies to every candidate, the baseline included, and is scored separately in the report. | Pass 1 showed local models answering implicit current-fact questions from memory and miscomputing arithmetic they had set up correctly; tool descriptions alone did not move them, and Ollama cannot force a tool call. |

## 05 Voice pipeline

| Date | Part of the system | Also touches | Deviation | Why |
|---|---|---|---|---|
| 2026-09-06 | Kokoro TTS | 08 | Kokoro runs through the `wyoming-kokoro-torch` package (PyPI, `--streaming` flag, CPU or Metal via `--device`) rather than the `kokoro-wyoming` Docker wrapper named in v0. | It installs from PyPI into the project venv, streams on sentence boundaries, and runs natively (no Docker). It needs `espeak-ng` from Homebrew and the model weights linked into its data directory, which `scripts/services.sh install` does. |

## 06 Home Assistant core

| Date | Part of the system | Also touches | Deviation | Why |
|---|---|---|---|---|
| 2026-09-06 | HAOS VM (UTM) | 08 | The Home Assistant OS VM is created from the command line (`scripts/haos_vm.sh create`, UTM's AppleScript interface) instead of by hand in the UTM window. | Reproducible, and it records the exact settings (4 GB, 2 cores, UEFI, VirtIO disk, bridged on the Mac's default interface). |
| 2026-09-06 | HA configuration | | Home Assistant is configured by `scripts/ha_setup.py` through its REST and websocket APIs (onboarding, add-ons, integrations, pipeline) rather than through the UI steps in section 3. | Lets the proof of concept be rebuilt from scratch without clicking, and documents every setting in code. The UI path still works. |

## 08 Hardware and deployment

| Date | Part of the system | Also touches | Deviation | Why |
|---|---|---|---|---|
| 2026-09-06 | Ollama service (launchd), MCP server binding | 03 | Ollama runs under our own launchd agent (`OLLAMA_HOST=0.0.0.0`, keep-alive forever) instead of Homebrew's service, and the MCP server binds `0.0.0.0`. | Homebrew's Ollama service binds localhost only, so the VM could not reach it. Both are LAN-only, unauthenticated services on a home network; the design accepts that. |

## 09 Dev environment

| Date | Part of the system | Also touches | Deviation | Why |
|---|---|---|---|---|
| 2026-09-05 | Docker CLI | 03 | Docker's CLI is used from the Docker Desktop app bundle rather than /usr/local/bin. | Docker Desktop did not create the symlink; scripts add the bundle path to PATH. |
| 2026-09-05 | uv environment | | `scripts/dev_setup.sh` wraps `uv sync` and clears the macOS hidden flag on `.venv`. | The repo lives in an iCloud-synced Desktop folder; macOS flags dot-prefixed trees as hidden and Python 3.12.14 skips hidden `.pth` files, which made the project's packages vanish from the environment mid-session. |
| 2026-09-05 | Repository location | | The repository moved from the iCloud-synced Desktop to `~/code/home_assistant`. | Beyond the hidden-flag problem, git inside the iCloud folder returned empty or missing objects for files it contained, and file reads were slow and inconsistent. The GitHub remote was verified intact and the working tree re-created from it. |
