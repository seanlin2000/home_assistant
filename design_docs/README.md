# Design docs

Design documentation for the local-first voice assistant. The docs are versioned by folder so that the original intent can be compared against what was actually built.

| Folder | Status | Rule |
|---|---|---|
| `v0/` | Frozen. Written before any code. | Never edited after the initial commit, not even to fix a number that later proves wrong. |
| `v1/` | Created when the build starts, by copying `v0/`. Living, as-built. | Updated as each component lands. `v1/DEVIATIONS.md` logs each departure from v0 with one line of reasoning. |

These docs record intent and how the build departed from it. For the built system explained as prose for a newcomer, with diagrams and the commands to run each part, read the Home Assistant Handbook in `operator_manual/` (`uv run mkdocs serve`).

Each design doc has one handbook page, listed here in the handbook's navigation order:

| Design doc | Handbook page | Nav group | Page title |
|---|---|---|---|
| `design_docs/v1/00_system_overview.md` | `operator_manual/index.md` | Introduction | Introduction |
| `design_docs/v1/06_home_assistant_core.md` | `operator_manual/06_home_assistant_core.md` | The Assistant | Home Assistant |
| `design_docs/v1/05_voice_pipeline.md` | `operator_manual/05_voice_pipeline.md` | The Assistant | Voice Pipeline |
| `design_docs/v1/04_conversation_agent.md` | `operator_manual/04_conversation_agent.md` | The Assistant | Conversation Agent |
| `design_docs/v1/03_web_search_mcp.md` | `operator_manual/03_web_search_mcp.md` | The Assistant | MCP Tool Server |
| `design_docs/v1/07_music_spotify.md` | `operator_manual/07_music_spotify.md` | The Assistant | Music |
| `design_docs/v1/02_local_llm.md` | `operator_manual/02_local_llm.md` | The Model | LLMs on Apple Silicon |
| `design_docs/v1/01_llm_benchmark.md` | `operator_manual/01_llm_benchmark.md` | The Model | Benchmarking and Model Selection |
| `design_docs/v1/08_hardware_and_deployment.md` | `operator_manual/08_hardware_and_deployment.md` | The Machine | Hardware |
| `design_docs/v1/10_operations.md` | `operator_manual/10_operations.md` | The Machine | Operations |
| `design_docs/v1/09_dev_environment.md` | `operator_manual/09_dev_environment.md` | Development | Development |

The point of keeping both is a retrospective at the end of the build: did the engineering choices hold up, and where did the build stray from the initial path into unnecessary complexity?

## Reading order

Start with `00_system_overview.md`. Every other doc covers one subsystem that has its own tech stack and follows the same skeleton:

1. Purpose in one paragraph
2. ASCII diagram
3. How it works, step by step
4. Packages, and what each one does for the business logic
5. Configuration we control
6. Failure modes
7. Concepts for newcomers, for readers who have not built LLM products or worked with hardware-facing packages
8. Sources

| Doc | Subsystem |
|---|---|
| `00_system_overview.md` | The whole system, phase plan, open decisions, costs |
| `01_llm_benchmark.md` | How we choose the model and the hardware |
| `02_local_llm.md` | Running a language model on a Mac |
| `03_web_search_mcp.md` | Self-hosted web search exposed as an MCP tool |
| `04_conversation_agent.md` | The loop that turns a question into a spoken answer |
| `05_voice_pipeline.md` | Wake word, microphone, speech to text, text to speech |
| `06_home_assistant_core.md` | The orchestrator everything plugs into |
| `07_music_spotify.md` | Voice-controlled Spotify playback |
| `08_hardware_and_deployment.md` | The always-on Mac and where each service runs |
| `09_dev_environment.md` | Virtual environment, pinned dependencies, how to run things |
| `10_operations.md` | Running, updating, watching, and debugging the headless Mac mini from the laptop (v1 only; added after the design was frozen) |
