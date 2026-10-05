# The system map

`operator_manual/_includes/system_map.mmd` is the one drawing of the whole system. Every section includes it under "Where this fits" and highlights its own nodes, so a reader always sees the same picture with a different part lit up.

It is the ASCII diagram of `design_docs/v1/00_system_overview.md` §2, drawn with Mermaid's shapes and the palette's colours: the studio as the outer container, the Mac inside it, the Home Assistant virtual machine and Docker inside that, the Assist pipeline as one row of stages across the top of the virtual machine, what each stage calls directly below it, and everything whose traffic leaves the apartment outside the studio at the bottom. Placement that faithful is not something a layout engine will choose, so the map is a fixed-grid diagram: the `%% grid:` lines at the top of the file put every box in its cell, and `diagrams/grid.py` lays the rendered drawing out on them. The `draw-diagram` skill holds the spec.

A "Where this fits" block is exactly:

```
flowchart TB
--8<-- "_includes/system_map.mmd"
class <ids> current
style <container> stroke:#f59e0b,stroke-width:3px    (optional)
```

## The grid

```
%% grid: .      puck     .        .       laptop   .        .
%% grid: .      stt      intents  .       agent    .        tts
%% grid: sonos  .        ma       .       .        .        piper
%% grid: .      whisper  .        .       ollama   mcp      health
%% grid: .      .        .        .       .        searxng  .
%% grid: .      .        spotify  metno   .        engines  .
```

There are seven columns, one per job: the Sonos; speech to text and Whisper; the intent matcher, Music Assistant, and Spotify; the weather lane down to Met.no; the agent and Ollama; the tool server, SearXNG, and the search engines; text to speech, Piper, and the health check. The top row is the devices in the studio, the puck above speech to text and the laptop in the empty middle above the agent. The second row is the four stages of one spoken question, in order, across the top of the virtual machine. The third row is what runs inside Home Assistant under the stage that calls it, Music Assistant and Piper, with the Sonos outside the Mac at the left. The fourth row is the services native to the Mac, each under the stage that calls it, with the health check in the last column under Piper; SearXNG sits in Docker under the tool server. The bottom row is outside the studio: the only traffic that leaves the apartment is the three arrows that cross that edge.

## Containers

| Id | Title | What sits inside |
|---|---|---|
| `studio` | Your studio: everything inside stays local | the puck, the laptop, the Sonos, and the Mac |
| `mac` | Mac, always on | the virtual machine, Docker, and the services beside them: Whisper, Ollama, the tool server, the health check |
| `haos` | Home Assistant OS, a virtual machine | the four Assist pipeline stages, left to right, with Music Assistant and Piper below them |
| `docker` | Docker | SearXNG |

Containers are places, not steps: a box's column says which stage of a question it serves, its container says which machine runs it, and its colour says who owns it. Keep container titles to about eight words; each one is drawn in a strip at the top of its container, where no edge runs.

## Node ids

| Id | Node | Class |
|---|---|---|
| `puck` | Voice puck, the Voice PE that hears the wake word on its own chip | hw |
| `stt` | speech to text stage | third |
| `whisper` | Whisper, native on the Mac's GPU | third |
| `intents` | intent matcher, fixed sentences, no language model | third |
| `ma` | Music Assistant, the music library, an add-on inside Home Assistant | third |
| `metno` | Met.no weather | ext |
| `sonos` | Sonos speaker | hw |
| `spotify` | Spotify API | ext |
| `agent` | studio_assistant conversation agent | ours |
| `ollama` | Ollama, the language model | third |
| `mcp` | web_search_mcp, search and calculator tools | ours |
| `searxng` | SearXNG metasearch in Docker | third |
| `engines` | public search engines | ext |
| `tts` | text to speech stage | third |
| `piper` | Piper, the voice: the default text to speech engine, an add-on inside Home Assistant | third |
| `laptop` | Laptop: deploys, reads logs over SSH | hw |
| `health` | health check, probes every service | ours |

Piper, the default voice, is the one text to speech engine on the map, straight under the stage that calls it, joined to it by two arrows, "text" down and "speech" back up, the way Whisper hangs under speech to text with "audio" down and "words" back up. Kokoro, the alternative voice that runs natively on the Mac, is not on the map; the Voice Pipeline page (`05_voice_pipeline.md`) explains it and how to switch the pipeline to it. The puck's two arrows are drawn as one double-headed edge labelled "audio in, spoken reply back", because Mermaid has no arrow with a head only at the start and a second line back across the drawing would cross everything.

## Highlights per page, and the code each page reads

In nav order, each page by its title and file stem. The nav groups and design docs for these pages are in the table in `design_docs/README.md`; when a page is renamed, its title changes in both tables.

| Page | File stem | `class ... current` | `style` | Code to read |
|---|---|---|---|---|
| Home Assistant | `06_home_assistant_core` | `stt,intents,agent,tts,ma` | | `custom_components/studio_assistant/`, `scripts/haos_vm.sh`, `scripts/ha_setup.py`, `ops/ha_client.py`, `ops/deploy.py` |
| Voice Pipeline | `05_voice_pipeline` | `puck,stt,tts,piper,whisper` | | `voice/kokoro_server.py`, `scripts/voice_check.py`, `scripts/services.sh`, `pyproject.toml` (`voice` group) |
| Conversation Agent | `04_conversation_agent` | `agent,ollama,mcp` | | `assistant_core/` (`agent_loop.py`, `router.py`, `prompts.py`, `tools.py`, `memory.py`, `models.py`, `exchange_record.py`), `custom_components/studio_assistant/`, `tests/test_agent_loop.py`, `tests/test_router.py` |
| MCP Tool Server | `03_web_search_mcp` | `mcp,searxng,engines` | | `web_search_mcp/`, `calculator_mcp/`, `docker/searxng/`, `scripts/searxng.sh`, `assistant_core/mcp_http.py`, `tests/test_url_guard.py`, `tests/test_web_search_mcp.py`, `tests/test_calculator.py`, `tests/test_mcp_http.py` |
| Music | `07_music_spotify` | `ma,sonos,spotify` | | `scripts/ha_setup.py` (music parts), `docs/VERSIONS.md` (add-ons) |
| LLMs on Apple Silicon | `02_local_llm` | `ollama` | | `assistant_core/llm_client.py`, `benchmark/ollama_utils.py`, `scripts/benchmark_llm.py`, `scripts/services.sh`, `docs/VERSIONS.md` |
| Benchmarking and Model Selection | `01_llm_benchmark` | `ollama,mcp,laptop` | | `benchmark/` (`run.py`, `judge.py`, `report.py`, `gates.py`, `records.py`, `costs.py`, `questions.yaml`, `rubric.md`, `config.yaml`), `scripts/benchmark_llm.py`, `.claude/agents/benchmark-judge.md`, `tests/test_gates_and_records.py`, `tests/test_manual_run.py`, `tests/test_mcp_process.py` |
| Hardware | `08_hardware_and_deployment` | `stt,intents,agent,tts,ma,piper,whisper,ollama,mcp,searxng` | | `scripts/bootstrap_mac.sh`, `scripts/services.sh`, `Brewfile`, `scripts/haos_vm.sh`, `docs/VERSIONS.md` |
| Operations | `10_operations` | `laptop,health` | | `ops/` (`health.py`, `smoke.py`, `deploy.py`, `report.py`, `pipeline_runs.py`, `paths.py`), `scripts/mini.sh`, `scripts/health_check.py`, `scripts/ops_report.py`, `scripts/services.sh` |
| Development | `09_dev_environment` | `laptop` | | `pyproject.toml`, `uv.lock`, `scripts/dev_setup.sh`, `scripts/lint.sh`, `.githooks/pre-commit`, `deslop/`, `pr_references/`, `manual_checks/`, `.github/workflows/`, `.claude/skills/` |

## Path prefixes to highlights, for `pr-entry`

| Changed path starts with | Highlight |
|---|---|
| `assistant_core/`, `custom_components/` | `agent` |
| `web_search_mcp/`, `calculator_mcp/`, `docker/` | `mcp` (and `searxng` for `docker/`) |
| `benchmark/` | `laptop,ollama` |
| `ops/`, `scripts/` | `laptop,health` |
| `voice/` | `tts,whisper` |
| anything else (`.github/`, `deslop/`, `pr_references/`, `manual_checks/`, `.claude/`, `operator_manual/`, docs) | `laptop` |

Union the highlights of every prefix the PR touches.
