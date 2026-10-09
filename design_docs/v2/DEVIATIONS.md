# Deviations from v2

Every place the build departs from the v2 design, with the reason. Grouped by the design doc the deviation mainly changes, oldest first within each group. **Part of the system** names the concrete component that moved; **Also touches** lists other docs affected. To add an entry, put it under the doc it mainly changes, not at the bottom of the file.

## 03. Tool server

| Date | Part of the system | Also touches | Deviation | Why |
|---|---|---|---|---|
| 2026-10-08 | `weather_mcp/geocoding.py` (`Geocoder`) | — | Places are kept in the tool server's memory, not on disk, so a restart looks each spoken place up again. Only the benchmark, which runs its tool server with a cache folder, keeps them on disk. | The production tool server has no cache folder today, and a lookup is one small request to Open-Meteo. A permanent place store can come with the next change that needs one on disk. |
