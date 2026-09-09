# The system map

`operator_manual/_includes/system_map.mmd` is the one drawing of the whole system. Every section includes it under "Where this fits" and highlights its own nodes, so a reader always sees the same picture with a different part lit up. The map itself is the as-built version of `design_docs/v1/00_system_overview.md` §2 plus the calculator tools, the health check, and the laptop, drawn as the layered top-down flowchart that `diagram_style.md` prescribes: six sibling rows, every edge pointing down.

A "Where this fits" block is exactly:

```
flowchart TB
--8<-- "_includes/system_map.mmd"
class <ids> current
style <row> stroke:#f59e0b,stroke-width:4px    (optional)
```

## Rows, top to bottom

| Row id | Title | What sits there |
|---|---|---|
| `people` | You and your devices | the things that start a request: the puck and the laptop |
| `haos` | Home Assistant OS, a virtual machine on the Mac | the four numbered stages of the Assist pipeline and the Music Assistant add-on |
| `native` | Native macOS services on the Mac, kept alive by launchd, with the GPU | what Home Assistant calls: Whisper, Ollama, the tool server, Kokoro, plus the health check |
| `speakers` | Speaker on the apartment Wi-Fi | the Sonos, which Music Assistant calls |
| `docker` | Docker Desktop on the Mac | SearXNG, which the tool server calls |
| `internet` | Leaves the apartment | the only traffic that crosses the router |

The Sonos sits in the row of things Home Assistant calls, beside the Mac's services, rather than with the puck: rows mean "who calls whom", and a box goes in the row below whatever calls it. There is no outer "Mac" container; the row titles say which rows run on the Mac.

## Node ids

| Id | Node | Class |
|---|---|---|
| `puck` | Voice PE puck | hw |
| `laptop` | laptop: benchmark, deploy, logs | hw |
| `stt` | 1. speech to text stage of the Assist pipeline | third |
| `intents` | 2. intent matcher | third |
| `agent` | 3. studio_assistant conversation agent | ours |
| `tts` | 4. text to speech stage, Piper add-on or Kokoro | third |
| `ma` | Music Assistant add-on | third |
| `whisper` | Whisper on MLX | third |
| `ollama` | Ollama and the chosen model | third |
| `mcp` | web_search_mcp, search and calculator tools | ours |
| `kokoro` | Kokoro text to speech | third |
| `health` | health check | ours |
| `sonos` | Sonos speaker | hw |
| `searxng` | SearXNG in Docker | third |
| `metno` | Met.no weather | ext |
| `engines` | search engines | ext |
| `spotify` | Spotify API | ext |

Piper has no node of its own: it is named inside the `tts` label because it runs inside Home Assistant as an add-on and an edge from `tts` to it would sit inside the row.

## Highlights per section, and the code each section reads

| Section | `class ... current` | `style` | Code to read |
|---|---|---|---|
| 01 LLM benchmark | `ollama,mcp,laptop` | | `benchmark/` (`run.py`, `judge.py`, `report.py`, `gates.py`, `records.py`, `costs.py`, `questions.yaml`, `rubric.md`, `config.yaml`), `scripts/benchmark_llm.py`, `.claude/agents/benchmark-judge.md`, `tests/test_gates_and_records.py`, `tests/test_manual_run.py`, `tests/test_mcp_process.py` |
| 02 Local LLM | `ollama` | | `assistant_core/llm_client.py`, `benchmark/ollama_utils.py`, `scripts/benchmark_llm.py`, `scripts/services.sh`, `docs/VERSIONS.md` |
| 03 Web search MCP | `mcp,searxng,engines` | `docker` | `web_search_mcp/`, `calculator_mcp/`, `docker/searxng/`, `scripts/searxng.sh`, `assistant_core/mcp_http.py`, `tests/test_url_guard.py`, `tests/test_web_search_mcp.py`, `tests/test_calculator.py`, `tests/test_mcp_http.py` |
| 04 Conversation agent | `agent,ollama,mcp` | | `assistant_core/` (`agent_loop.py`, `router.py`, `prompts.py`, `tools.py`, `memory.py`, `models.py`, `turn_record.py`), `custom_components/studio_assistant/`, `tests/test_agent_loop.py`, `tests/test_router.py` |
| 05 Voice pipeline | `puck,stt,tts,whisper,kokoro` | | `voice/kokoro_server.py`, `scripts/voice_check.py`, `scripts/services.sh`, `pyproject.toml` (`voice` group) |
| 06 Home Assistant core | `stt,intents,agent,tts,ma` | `haos` | `custom_components/studio_assistant/`, `scripts/haos_vm.sh`, `scripts/ha_setup.py`, `ops/ha_client.py`, `ops/deploy.py` |
| 07 Music and Spotify | `ma,sonos,spotify` | | `scripts/ha_setup.py` (music parts), `docs/VERSIONS.md` (add-ons) |
| 08 Hardware and deployment | | `haos`, `native`, `docker` | `scripts/bootstrap_mac.sh`, `scripts/services.sh`, `Brewfile`, `scripts/haos_vm.sh`, `docs/VERSIONS.md` |
| 09 Dev environment | `laptop` | | `pyproject.toml`, `uv.lock`, `scripts/dev_setup.sh`, `scripts/lint.sh`, `.githooks/pre-commit`, `deslop/`, `pr_references/`, `manual_checks/`, `.github/workflows/`, `.claude/skills/` |
| 10 Operations | `laptop,health` | `native` | `ops/` (`health.py`, `smoke.py`, `deploy.py`, `report.py`, `pipeline_runs.py`, `paths.py`), `scripts/mini.sh`, `scripts/health_check.py`, `scripts/ops_report.py`, `scripts/services.sh` |

## Path prefixes to highlights, for `pr-entry`

| Changed path starts with | Highlight |
|---|---|
| `assistant_core/`, `custom_components/` | `agent` |
| `web_search_mcp/`, `calculator_mcp/`, `docker/` | `mcp` (and `searxng` for `docker/`) |
| `benchmark/` | `laptop,ollama` |
| `ops/`, `scripts/` | `laptop,health` |
| `voice/` | `kokoro,whisper` |
| anything else (`.github/`, `deslop/`, `pr_references/`, `manual_checks/`, `.claude/`, `operator_manual/`, docs) | `laptop` |

Union the highlights of every prefix the PR touches.
