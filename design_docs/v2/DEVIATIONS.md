# Deviations from v2

Every place the build departs from the v2 design, with the reason. Grouped by the design doc the deviation mainly changes, oldest first within each group. **Part of the system** names the concrete component that moved; **Also touches** lists other docs affected. To add an entry, put it under the doc it mainly changes, not at the bottom of the file.

## 02. Inference engine

| Date | Part of the system | Also touches | Deviation | Why |
|---|---|---|---|---|
| 2026-11-11 | `config/serving.toml` (`speculative`), `serving/command.py` | 10 | Qwen 3.8 27B is served with `--spec-type draft-mtp`, so its own multi-token-prediction layer drafts tokens, and with a 2,048 MiB prompt cache instead of 1,024. Thinking stays off on the server and the harness turns it on per request. | Decode measured 19 tok/s without drafting and 34 to 37 with it on the M5 Max, with the same model file. One slot's prompt state is about 1,091 MiB, so a 1,024 MiB cache skipped it. |
| 2026-11-13 | `config/serving.toml` (`speculative`, `[models."qwen3.8-flash-next".draft]`), `serving/settings.py` (`DraftModel`), `serving/command.py` | 10 | Qwen 3.8 Flash Next is served with `--spec-type draft-dflash` and a separate drafter, Inco AI's DFlash2 at Q8_0 (`-md`), proposing up to 3 tokens a step. The drafter is pinned by revision and SHA-256 like the model, and the launch refuses a drafter whose hash differs. It needs Homebrew llama.cpp 0.9.0 or newer. | The ISTA-DASLab file has no multi-token-prediction layer. With the drafter, decode measured 71.6 tok/s against 53.7 on the Studio, with unchanged benchmark quality (A+B, three passes each). Drafting 5 or 7 tokens was slower, because fewer drafts were accepted. |

## 03. Tool server

| Date | Part of the system | Also touches | Deviation | Why |
|---|---|---|---|---|
| 2026-10-08 | `weather_mcp/geocoding.py` (`Geocoder`) | — | Places are kept in the tool server's memory, not on disk, so a restart looks each spoken place up again. Only the benchmark, which runs its tool server with a cache folder, keeps them on disk. | The production tool server has no cache folder today, and a lookup is one small request to Open-Meteo. A permanent place store can come with the next change that needs one on disk. |
| 2026-11-11 | the nine `*_mcp/register.py` files | 04 | Every tool argument has its own description in the schema, fixed value sets are enums, and each tool's answer-shaping rules (read numbers as given, no showtimes, Michelin price words) live in its description instead of the system prompt. The harness sends schemas without pydantic's `title` keys. | The system prompt repeated most tool descriptions; one place per rule means a new tool needs no prompt change. Titles only repeated each argument's name, 13% of the definitions. |


## 04. Agent harness

| Date | Part of the system | Also touches | Deviation | Why |
|---|---|---|---|---|
| 2026-10-08 | `assistant_core/router.py` (`ROUTE_SCHEMA`) | 01 | The router plans tool families (`search`, `calculate`, `weather`) with `route`, `also` and `plan`, not a list of tool names. `route` stays the first family, so single-tool questions and the router-accuracy report are unchanged. | The directives already speak in families, and a small model picks one of three words more reliably than one of fourteen tool names. Category F's `required_tools` names families for the same reason. |
| 2026-10-08 | `assistant_core/router.py` (`decide_route`) | — | A question the rules route that also carries a second request ("…, and when is the last ferry?") asks the model layer too, and the model's extra routes and plan are added after the rules' routes. | The rules see one part of a compound question and would otherwise answer it alone; the extra router call (about 0.3 s, in the quiet slot) is paid only for compound questions. |
| 2026-10-08 | `assistant_core/router.py` (`tool_round_cap`) | — | The round cap is the planned tools plus one, but never below the configured cap (4), rather than at least two. | Lowering the cap for one-tool questions would change A to E, where a search is often followed by a page read; M5 measures the multi-tool change alone. |
| 2026-11-11 | `assistant_core/prompts.py` (prompt 3.0), `config/harness.toml` | 02 | For Qwen 3.8 27B the router is off (`route_questions = false`), so the note before each question carries only the date; six earlier exchanges are replayed instead of three; thinking is on at medium effort per request (`think = "medium"`); the system prompt drops from 8,909 to 2,470 characters. | The router, the per-tool prompt sections and the three-exchange window were added for Gemma 4 E4B's failures; the larger model chooses tools from their definitions. The benchmark measures the change. |


## 10. Operations

| Date | Part of the system | Also touches | Deviation | Why |
|---|---|---|---|---|
| 2026-11-11 | `scripts/export_to_new_mac.sh`, `scripts/bootstrap_mac.sh` (`--from`) | 08 | A move to a new Mac is an export folder carried to it and the bootstrap run at its own keyboard, not `mini.sh push-env`, `push-models` and `push-vm` over SSH (v2/08 section 3.4). The bootstrap writes the SSH drop-in, and limits Remote Login to the one account, only when it runs over SSH. | The laptop-to-Studio move over SSH needed many hand fixes, and the user did not want the laptop able to run commands on the serving Mac. Section 3.10 lists what the move now does. |
| 2026-11-11 | `scripts/deploy.sh`, `ops/deploy_here.py` | — | A deploy to the Studio is run at its keyboard and decides keep or roll back there, not driven from the laptop over SSH by `scripts/mini.sh deploy` (v1/10 section 3.8, section 3.3). It also waits for the harness to report the model ready, up to 15 minutes rather than two. | The serving Mac takes no commands over SSH (section 3.10), and the 27B model takes longer than two minutes to load. Section 3.11 lists the steps. |

| 2026-11-14 | `config/serving.toml` (`[engine]`), `serving/engine.py`, `serving/cli.py` (`launch`), `scripts/bootstrap_mac.sh` | 02 | Homebrew's `ggml` is pinned with llama.cpp, the release is recorded in `config/serving.toml` as well as `docs/VERSIONS.md`, and `serving launch` refuses to start llama-server when the installed llama.cpp version, build or ggml version differs from `[engine]`. The setup script pins both right after installing them. | The design pinned llama.cpp alone and only recorded the version, so the Studio, set up from an unversioned Brewfile, ran unpinned 0.9.0, and llama-server loads its compute libraries from the separate `ggml` package, which a pin on llama.cpp does not hold. |