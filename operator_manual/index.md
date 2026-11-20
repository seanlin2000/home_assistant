# Introduction

## Purpose

This is a voice assistant for a small apartment that keeps its data at home. You say "Hey Jarvis" and ask a question. It answers from a language model running on a Mac in the room, and when the question needs something current it searches the web, reads the pages, and answers from what it found. It also plays Spotify on a speaker and reports the weather. The wake word, the speech recognition, the language model, the speech synthesis, and the search aggregator all run inside the apartment. The only traffic that leaves is the search query itself, Spotify's API calls, and a pair of coordinates for the weather service.

The project is a proof of concept today.

**Works today:**

- Typed questions go through Home Assistant to the local model.
- The model calls the calculator, reads the forecast for home, and searches the web.
- The speech services run on the Mac and a "Jarvis" pipeline is wired end to end, so you can talk to it from a phone. The pipeline has no wake word yet, so you hold the Assist button in the Companion app instead.

**Configured, not yet connected:**

- The voice puck.
- The music path.

A benchmark has narrowed the model choice to a mixture-of-experts model on a 32 GB machine (see [Benchmarking and Model Selection](01_llm_benchmark.md)).

This manual explains how the system works and how to run each part of it. It is written for someone with a computer science degree who has not built products on top of language models and has not worked with hardware-facing software before. Nothing here assumes you know what an LLM API returns, what the Model Context Protocol is, how Home Assistant thinks, or why a virtual machine is involved. Each term is defined the first time it matters and again in the [glossary](glossary.md).

## How to read this manual

The pages are grouped by what they explain:

- **The Assistant** follows a question through the parts you talk to: [Home Assistant](06_home_assistant_core.md), [Voice Pipeline](05_voice_pipeline.md), [Conversation Agent](04_conversation_agent.md), [MCP Tool Server](03_web_search_mcp.md), and [Music](07_music_spotify.md).
- **The Model** is the language model: [LLMs on Apple Silicon](02_local_llm.md) and [Benchmarking and Model Selection](01_llm_benchmark.md).
- **The Machine** is the Mac everything runs on: [Hardware](08_hardware_and_deployment.md) and [Operations](10_operations.md).
- **[Development](09_dev_environment.md)** is how the code is built, checked, and merged.

Each page matches one design document in `design_docs/`, and the table in `design_docs/README.md` pairs them. The design documents record why each decision was made and how the build departed from the plan. This manual describes only what exists now.

Every page in those groups has the same shape:

1. **Where this fits.** The system map with that page's parts highlighted, and a paragraph reading the highlighted path.
2. **Key definitions.** The terms you need for this page.
3. **Packages and tools.** What each piece of software or hardware is and what the project uses it for.
4. **How it works.** One subsection per modular part, each opening with a diagram.
5. **Run it yourself.** The commands to exercise the part from a terminal, what you should see, and how to stop.
6. **Where to look in the code** and **Further reading.**

Start here:

1. This Introduction.
2. The Assistant pages, top to bottom. The [conversation agent](04_conversation_agent.md) is the heart of the system.

Then read whichever group you need:

- The Model explains how the language model runs and how it was chosen.
- The Machine explains the platform it runs on and how the Mac is operated.
- Development explains how the code is developed and reviewed.

The [Current Working Changes](current_changes.md) page lists what is in open pull requests and not yet on `main`.

## Key definitions

| Term | Meaning |
|---|---|
| Large language model (LLM) | A neural network that predicts the next token from everything before it, writes answers when run in a loop, and knows nothing after its training date. |
| Token | The unit a language model reads and writes, roughly a word fragment. |
| Tool calling | The model replying with a structured request to run a tool, such as `web_search(query="current federal funds rate")`, instead of with an answer. |
| MCP (Model Context Protocol) | A standard for exposing tools to a language model application over a network, in which a server declares each tool with a name, a description, and a JSON schema, and a client lists them, shows them to the model, and calls them when the model asks. |
| Home Assistant | An open-source home automation platform, which here is the plumbing that talks to the voice devices, runs the speech pipeline, controls music, and hosts our agent. |
| Wyoming | A small line-based protocol that Home Assistant uses to talk to speech services over TCP, so a speech model can run on any machine it can reach by host and port. |
| Wake word | A short phrase, such as "Hey Jarvis", that a tiny always-on model listens for before a device sends any audio anywhere. |
| Unified memory | One pool of memory shared by the CPU and GPU on Apple Silicon, whose size decides which models fit. |

## Software and hardware

| Name | What it is | How the project uses it | Page |
|---|---|---|---|
| Home Assistant OS | An open-source home automation platform, shipped as a whole operating system image | The orchestrator. It adopts the puck, runs the speech pipeline, matches simple commands, controls music, and hosts our agent as a custom component | [Home Assistant](06_home_assistant_core.md) |
| Whisper on MLX | OpenAI's open speech-to-text model, run through Apple's MLX framework | Turns your speech into text on the Mac's GPU, reached over Wyoming | [Voice Pipeline](05_voice_pipeline.md) |
| Kokoro and Piper | Two open text-to-speech models | Turn the answer into audio; Kokoro runs on the Mac, Piper as an add-on inside the VM | [Voice Pipeline](05_voice_pipeline.md) |
| Home Assistant Voice Preview Edition | A small puck with two far-field microphones and a speaker | The thing you talk to. It hears the wake word on its own chip and streams audio to Home Assistant | [Voice Pipeline](05_voice_pipeline.md) |
| `assistant_core` and `studio_assistant` | Our Python package and the Home Assistant custom component built on it | The conversation agent: persona, brevity rules, tool use, the filler sentence, deciding when the puck listens for a follow-up | [Conversation Agent](04_conversation_agent.md) |
| `web_search_mcp`, `calculator_mcp`, and `weather_mcp` | Our Python MCP server | Turns a question into grounded excerpts from real pages, does arithmetic exactly, and reads the forecast for home from Met.no | [MCP Tool Server](03_web_search_mcp.md) |
| SearXNG | A self-hosted metasearch engine | Queries several search engines at once with no account and no API key, inside Docker | [MCP Tool Server](03_web_search_mcp.md) |
| Music Assistant, Spotify, Sonos | A music library add-on, the catalogue, and the speaker | "Play Radiohead" starts music with no language model involved | [Music](07_music_spotify.md) |
| Ollama | A program that downloads language models and serves them over HTTP | Runs the chosen model on the Mac's GPU; the agent and the benchmark both talk to it | [LLMs on Apple Silicon](02_local_llm.md) |
| Gemma 4, Qwen 3.5 and 3.6 | Open-weight language model families | The candidates the benchmark compared; the model the assistant answers with | [LLMs on Apple Silicon](02_local_llm.md), [Benchmarking and Model Selection](01_llm_benchmark.md) |
| Mac mini | An always-on Apple Silicon computer, not yet bought | The planned home for everything above. At the planned 32 GB, the services and Gemma 4 26B-A4B take about 28 to 30 GB. Until it is bought, a 16 GB M1 Pro MacBook runs everything | [Hardware](08_hardware_and_deployment.md#the-memory-budget) |
| UTM | A free virtualisation app for macOS | Runs Home Assistant OS as a virtual machine with its own address on the Wi-Fi | [Hardware](08_hardware_and_deployment.md) |
| launchd, SSH, rsync | macOS's service manager and the standard remote tools | Keep the services alive, deploy from the laptop, and pull logs back | [Operations](10_operations.md) |
| uv | A Python package and environment manager | Builds the project's virtual environment from a lock file so every machine runs the same code | [Development](09_dev_environment.md) |

## The system map

```mermaid
flowchart TB
--8<-- "_includes/system_map.mmd"
```

One spoken question, end to end:

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: .        you      .
%% grid: .        puck     .
%% grid: whisper  stt      .
%% grid: .        intents  fixed
%% grid: mcp      agent    ollama
%% grid: piper    tts      .
%% grid: .        hear     .
%% peers: puck stt intents agent tts whisper fixed ollama piper mcp
you(["You: “Hey Jarvis, who won<br/>the Ballon d’Or?”"])
puck("voice puck<br/>wakes on “Hey Jarvis”")
stt("speech to text<br/>in Home Assistant")
intents("intent matcher<br/>fixed sentence patterns")
agent("our agent<br/>studio_assistant")
tts("text to speech<br/>in Home Assistant")
whisper("Whisper<br/>on the Mac’s GPU")
fixed("music or weather<br/>handled with no model")
ollama("Ollama<br/>the language model")
piper("Piper<br/>the voice")
mcp("our MCP server<br/>searches, reads pages")
hear(["You hear the answer;<br/>the puck keeps listening"])
you --> puck
puck -- "audio, over Wi-Fi" --> stt
stt -- "audio" --> whisper
whisper -- "text" --> stt
stt -- "“who won the Ballon d’Or?”" --> intents
intents -- "matches “play X”" --> fixed
intents -- "no match" --> agent
agent -- "“Ballon d’Or winner”" --> mcp
mcp -- "excerpts of the pages" --> agent
agent -- "the chat, tool list" --> ollama
ollama -- "tool call, then answer" --> agent
agent -- "the answer, streamed" --> tts
tts -- "text" --> piper
piper -- "audio" --> tts
tts -- "spoken, on the puck" --> hear
class puck hw
class agent,mcp ours
class stt,intents,tts,whisper,fixed,ollama,piper third
```

- When the model first asks for a tool, the agent streams a short filler sentence such as "Let me pull some sources on that", so the puck starts speaking while the search runs.
- The answer streams to text to speech and is spoken sentence by sentence.
- After an ordinary answer the conversation stays open for a few seconds, so a follow-up needs no wake word, at most twice in a row.

## Where the code lives

| Folder | What is in it | Page |
|---|---|---|
| `custom_components/studio_assistant/` | The thin Home Assistant component that wraps `assistant_core` as a conversation agent | [Home Assistant](06_home_assistant_core.md#the-custom-component), [Conversation Agent](04_conversation_agent.md) |
| `voice/` | The Kokoro text-to-speech server that speaks Wyoming | [Voice Pipeline](05_voice_pipeline.md) |
| `assistant_core/` | The agent loop, the question router, the prompts, the tool client, and the conversation memory. Plain Python with no Home Assistant dependency, so the benchmark runs the same loop the product runs | [Conversation Agent](04_conversation_agent.md) |
| `web_search_mcp/`, `calculator_mcp/`, and `weather_mcp/` | The MCP server: search tools, page fetching with a URL guard, calculator tools, and the forecast tool for home | [MCP Tool Server](03_web_search_mcp.md) |
| `docker/searxng/` | The SearXNG container definition and its settings | [MCP Tool Server](03_web_search_mcp.md#searxng-in-docker) |
| `benchmark/` | The harness that runs a question set through the agent loop against each candidate model, judges the answers, and writes the report. `results/` holds every pass | [Benchmarking and Model Selection](01_llm_benchmark.md) |
| `ops/` and `scripts/` | Installing services, deploying the component into the VM, the health check, the smoke test, and the operations report. Shell scripts for the Mac, the VM, SearXNG, and the services | [Hardware](08_hardware_and_deployment.md), [Operations](10_operations.md) |
| `deslop/`, `pr_references/`, `manual_checks/` | Small checkers that run in the pre-commit hook and CI: coding conventions, PR line references, and this manual's diagrams and structure | [Development](09_dev_environment.md#the-checkers) |
| `tests/` | The test suite, run by the pre-commit hook and by CI | [Development](09_dev_environment.md) |
| `operator_manual/` | This manual | [Development](09_dev_environment.md#the-manual) |
| `design_docs/` | The design, frozen as `v0/` before any code and maintained as `v1/` as built | Every page links its own under Further reading |

## Before you run anything

Every command in this manual is run from the repository folder, through the project's own Python environment: `uv run ...` for Python, and the scripts in `scripts/` for the rest. Never use the machine's own `python`. `scripts/dev_setup.sh` builds the environment from the lock file the first time.

Addresses and secrets live in `.env`, which is never committed. Load it once per terminal:

```bash
cd ~/code/home_assistant
set -a; source .env; set +a
```

The prototype Mac has 16 GB of memory. The Home Assistant VM with the speech services takes about 11 GB, and a benchmark run takes most of the machine on its own, so they must not run together. Before starting the VM or the speech services, check that no benchmark is running:

```bash
pgrep -fl benchmark-run || echo "no benchmark running"
```

Each page's "Run it yourself" says how to start and stop its services:

- **Always up:** Ollama and the tool server, which are small.
- **Started when you want to talk, stopped when you are done:** Whisper, Kokoro, which speaks the answers in its Fable voice, and the Home Assistant VM. `scripts/services.sh start` starts Kokoro beside Whisper; the VM's Piper add-on speaks instead after `scripts/ha_setup.py --tts piper`.

`scripts/services.sh status` shows what is listening on each port right now.
