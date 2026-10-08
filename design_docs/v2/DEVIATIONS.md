# Deviations from v2

Every place the build departs from the v2 design, with the reason. Grouped by the design doc the deviation mainly changes, oldest first within each group. **Part of the system** names the concrete component that moved; **Also touches** lists other docs affected. To add an entry, put it under the doc it mainly changes, not at the bottom of the file.

## 03. Tool server

| Date | Part of the system | Also touches | Deviation | Why |
|---|---|---|---|---|
| 2026-10-08 | `weather_mcp/geocoding.py` (`Geocoder`) | — | Places are kept in the tool server's memory, not on disk, so a restart looks each spoken place up again. Only the benchmark, which runs its tool server with a cache folder, keeps them on disk. | The production tool server has no cache folder today, and a lookup is one small request to Open-Meteo. A permanent place store can come with the next change that needs one on disk. |

## 04. Agent harness

| Date | Part of the system | Also touches | Deviation | Why |
|---|---|---|---|---|
| 2026-10-08 | `assistant_core/router.py` (`ROUTE_SCHEMA`) | 01 | The router plans tool families (`search`, `calculate`, `weather`) with `route`, `also` and `plan`, not a list of tool names. `route` stays the first family, so single-tool questions and the router-accuracy report are unchanged. | The directives already speak in families, and a small model picks one of three words more reliably than one of fourteen tool names. Category F's `required_tools` names families for the same reason. |
| 2026-10-08 | `assistant_core/router.py` (`decide_route`) | — | A question the rules route that also carries a second request ("…, and when is the last ferry?") asks the model layer too, and the model's extra routes and plan are added after the rules' routes. | The rules see one part of a compound question and would otherwise answer it alone; the extra router call (about 0.3 s, in the quiet slot) is paid only for compound questions. |
| 2026-10-08 | `assistant_core/router.py` (`tool_round_cap`) | — | The round cap is the planned tools plus one, but never below the configured cap (4), rather than at least two. | Lowering the cap for one-tool questions would change A to E, where a search is often followed by a page read; M5 measures the multi-tool change alone. |
