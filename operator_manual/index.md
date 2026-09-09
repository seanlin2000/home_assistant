# Introduction

## Purpose

This is a voice assistant for a small apartment that keeps its data at home. You say "Hey Jarvis" and ask a question. It answers from a language model running on a Mac in the room, and when the question needs something current it searches the web, reads the pages, and answers from what it found. It also plays Spotify on a speaker and reports the weather. The wake word, the speech recognition, the language model, the speech synthesis, and the search aggregator all run inside the apartment. The only traffic that leaves is the search query itself, Spotify's API calls, and a pair of coordinates for the weather service.

The project is a proof of concept today. Typed questions go through Home Assistant to the local model, call the calculator, and search the web. The speech services run on the Mac and a "Jarvis" pipeline is wired end to end, so you can talk to it from a phone. The voice puck and the music path are configured but not yet connected, and a benchmark has narrowed the model choice to a mixture-of-experts model on a 32 GB machine.

This manual explains how the system works and how to run each part of it. It is written for someone with a computer science degree who has not built products on top of language models and has not worked with hardware-facing software before. Nothing here assumes you know what an LLM API returns, what the Model Context Protocol is, how Home Assistant thinks, or why a virtual machine is involved. Each term is defined the first time it matters and again in the [glossary](glossary.md).

## How to read this manual

The manual has one section per part of the system, numbered the same way as the design documents in `design_docs/`, so section 4 and design doc 04 describe the same thing. The design documents record why each decision was made and how the build departed from the plan. This manual describes only what exists now.

Every section has the same shape:

1. **Where this fits.** The system map with that section's parts highlighted, and a paragraph reading the highlighted path.
2. **Key definitions.** The terms you need for this section.
3. **Packages and tools.** What each piece of software or hardware is and what the project uses it for.
4. **How it works.** One subsection per modular part, each opening with a diagram.
5. **Run it yourself.** The commands to exercise the part from a terminal, what you should see, and how to stop.
6. **Where to look in the code** and **Further reading.**

Read the Introduction, then section 4 (the conversation agent) for the heart of the system, then whichever section you need. Sections 2, 3, and 5 explain the three services the agent depends on. Sections 6 to 8 explain the platform it runs on. Sections 1, 9, and 10 explain how the model was chosen, how the code is developed, and how the machine is operated. The [Current working changes](current_changes.md) page lists what is in open pull requests and not yet on `main`.

A short line under each section's title records a complexity score. It is the length budget the section was written to: light sections take three to five minutes to read, standard ones five to eight, deep ones ten to fifteen.

## Key definitions

- **Large language model (LLM).** A neural network that predicts the next token given everything before it. Run in a loop, it writes answers. Its knowledge stops at its training date, which is why current facts need a search tool.
- **Token.** The unit a language model reads and writes, roughly a word fragment.
- **Tool calling.** Instead of answering, the model emits a structured request such as `web_search(query="current federal funds rate")`. Our code runs the tool, appends the result, and calls the model again.
- **MCP (Model Context Protocol).** A standard for exposing tools to a language model application over a network. A server declares tools with a name, a description, and a JSON schema; a client lists them, shows them to the model, and calls them when the model asks.
- **Home Assistant.** An open-source home automation platform. Here it is the plumbing that already knows how to talk to the puck, run a speech pipeline, control music, and host our agent.
- **Wyoming.** A small line-based protocol Home Assistant uses to talk to speech services over the network. It lets a speech model run anywhere Home Assistant can reach by host and port.
- **Wake word.** A tiny always-on model that listens for one phrase and nothing else. It runs on the puck, so no audio leaves the device until you address it.
- **Unified memory.** One pool of memory shared by the CPU and GPU on Apple Silicon. Its size decides which models fit.

## Software and hardware

| Name | What it is | How the project uses it | Section |
|---|---|---|---|
| Home Assistant OS | An open-source home automation platform, shipped as a whole operating system image | The orchestrator. It adopts the puck, runs the speech pipeline, matches simple commands, controls music, and hosts our agent as a custom component | [6](06_home_assistant_core.md) |
| UTM | A free virtualisation app for macOS | Runs Home Assistant OS as a virtual machine with its own address on the Wi-Fi | [8](08_hardware_and_deployment.md) |
| Ollama | A program that downloads language models and serves them over HTTP | Runs the chosen model on the Mac's GPU; the agent and the benchmark both talk to it | [2](02_local_llm.md) |
| Gemma 4, Qwen 3.5 and 3.6 | Open-weight language model families | The candidates the benchmark compared; the model the assistant answers with | [1](01_llm_benchmark.md), [2](02_local_llm.md) |
| `assistant_core` and `studio_assistant` | Our Python package and the Home Assistant custom component built on it | The conversation agent: persona, brevity rules, tool use, the filler sentence, keeping the microphone open | [4](04_conversation_agent.md) |
| `web_search_mcp` and `calculator_mcp` | Our Python MCP server | Turns a question into grounded excerpts from real pages, and does arithmetic exactly | [3](03_web_search_mcp.md) |
| SearXNG | A self-hosted metasearch engine | Queries several search engines at once with no account and no API key, inside Docker | [3](03_web_search_mcp.md) |
| Whisper on MLX | OpenAI's open speech-to-text model, run through Apple's MLX framework | Turns your speech into text on the Mac's GPU, reached over Wyoming | [5](05_voice_pipeline.md) |
| Kokoro and Piper | Two open text-to-speech models | Turn the answer into audio; Kokoro runs on the Mac, Piper as an add-on inside the VM | [5](05_voice_pipeline.md) |
| Home Assistant Voice Preview Edition | A small puck with two far-field microphones and a speaker | The thing you talk to. It hears the wake word on its own chip and streams audio to Home Assistant | [5](05_voice_pipeline.md) |
| Music Assistant, Spotify, Sonos | A music library add-on, the catalogue, and the speaker | "Play Radiohead" starts music with no language model involved | [7](07_music_spotify.md) |
| Mac mini | An always-on Apple Silicon computer | Runs everything above; the laptop is only for development and operations | [8](08_hardware_and_deployment.md) |
| uv | A Python package and environment manager | Builds the project's virtual environment from a lock file so every machine runs the same code | [9](09_dev_environment.md) |
| launchd, SSH, rsync | macOS's service manager and the standard remote tools | Keep the services alive, deploy from the laptop, and pull logs back | [10](10_operations.md) |

## The system map

```mermaid
flowchart TB
--8<-- "_includes/system_map.mmd"
```

Read it top to bottom. Each row is one layer of the system, and a box sits in the row below whatever calls it: the devices that start a request are on top, then Home Assistant, then the services on the Mac that Home Assistant calls, with the Sonos beside them because Home Assistant calls it too, then Docker, and at the bottom the only traffic that leaves the apartment. Colour says who is responsible for a box: blue is code in this repository, grey is third-party software the project runs and configures, green is a physical device, and red is a service whose traffic leaves the apartment (the [diagram legend](diagram_legend.md) has the full key). The four numbered stages in the Home Assistant row run in that order for every spoken question. Every section repeats this map with its own parts drawn with a thick orange border.

Follow a question through it. You say "Hey Jarvis, who won the Ballon d'Or?" The puck's own chip recognises the wake word and only then starts streaming audio over Wi-Fi to Home Assistant, which runs in a virtual machine on the Mac. Home Assistant's speech-to-text stage forwards the audio to Whisper, a model running natively on the Mac's GPU, and gets text back. The intent matcher looks at the text first: "play Radiohead" and "what's the weather" match fixed sentence patterns and are handled without a language model. Anything else goes to our conversation agent, the `studio_assistant` component.

The agent sends the conversation and a list of available tools to Ollama, which runs the language model. If the model decides it needs current information, it asks for the search tool. The agent immediately streams a short filler sentence, "Let me pull some sources on that", so the puck starts speaking while the search runs. The tool call goes over MCP to our search server, which asks SearXNG in Docker to query the public search engines, fetches the top pages, extracts the readable text, and returns numbered excerpts. The model reads them and writes the answer. The answer streams sentence by sentence to the text-to-speech stage, which hands it to Kokoro or Piper, and the audio plays on the puck. The agent marks the conversation as continuing, so the puck listens for a follow-up for a few seconds without needing the wake word again.

## Where the code lives

| Folder | What is in it |
|---|---|
| `assistant_core/` | The agent loop, the question router, the prompts, the tool client, and the conversation memory. Plain Python with no Home Assistant dependency, so the benchmark runs the same loop the product runs |
| `custom_components/studio_assistant/` | The thin Home Assistant component that wraps `assistant_core` as a conversation agent |
| `web_search_mcp/` and `calculator_mcp/` | The MCP server: search tools, page fetching with a URL guard, and calculator tools |
| `voice/` | The Kokoro text-to-speech server that speaks Wyoming |
| `benchmark/` | The harness that runs a question set through the agent loop against each candidate model, judges the answers, and writes the report. `results/` holds every pass |
| `ops/` and `scripts/` | Installing services, deploying the component into the VM, the health check, the smoke test, and the operations report. Shell scripts for the Mac, the VM, SearXNG, and the services |
| `docker/searxng/` | The SearXNG container definition and its settings |
| `design_docs/` | The design, frozen as `v0/` before any code and maintained as `v1/` as built |
| `operator_manual/` | This manual |
| `deslop/`, `pr_references/`, `manual_checks/` | Small checkers that run in the pre-commit hook and CI: coding conventions, PR line references, and this manual's diagrams and structure |
| `tests/` | The test suite, run by the pre-commit hook and by CI |

## Before you run anything

Every command in this manual is run from the repository folder, through the project's own Python environment: `uv run ...` for Python, and the scripts in `scripts/` for the rest. Never use the machine's own `python`. `scripts/dev_setup.sh` builds the environment from the lock file the first time.

Addresses and secrets live in `.env`, which is never committed. Load it once per terminal:

```bash
cd ~/code/home_assistant
set -a; source .env; set +a
```

The prototype Mac has 16 GB of memory. The Home Assistant VM with the speech services takes about 12 GB, and a benchmark run takes most of the machine on its own, so they must not run together. Before starting the VM or the speech services, check that no benchmark is running:

```bash
pgrep -fl benchmark-run || echo "no benchmark running"
```

Ollama and the tool server are small and stay up all the time. Whisper, Kokoro, and the VM are started when you want to talk to the assistant and stopped when you are done; each section's "Run it yourself" says how. `scripts/services.sh status` shows what is listening on each port right now.
