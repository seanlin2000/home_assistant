# Deviations from v0

One line per place the build departed from the frozen design in `design_docs/v0/`, with the reason. Newest at the bottom.

| Date | Doc | Deviation | Why |
|---|---|---|---|
| 2026-09-05 | 01 | The frontier baseline and judge cannot run at temperature 0: Claude Opus 5 rejects sampling parameters. The judge uses structured output (a JSON schema the response must validate against) at the API's default settings instead. | API constraint, not a design choice. |
| 2026-09-05 | 01 | The frontier baseline runs with adaptive thinking on rather than off. | Opus 5 has thinking on by default and disabling it causes tool calls to leak into visible text. The baseline is the quality ceiling, not a purchase candidate, so its latency is not compared. |
| 2026-09-05 | 03 | The benchmark harness starts the MCP server itself as a subprocess with a per-run cache directory, instead of relying on a separately started server. | One command per run; the cache is guaranteed to be per run. |
| 2026-09-05 | 01 | The question set is version 1.1 with 22 questions: A11 (settled history that sounds current) and B21 (false current premise) were added before the first run at the user's request. Maximum is 220 per model, 110 per category. | The v1.1 candidates were ready and the user chose to include them now. |
| 2026-09-05 | 01, 07 | Gemma 4 E4B runs from Ollama's `gemma4:e4b-it-qat` tag (6.1 GB, Google's quantization-aware int4), not a 4.5 GB Q4 file; Ollama's default `gemma4:e4b` is 9.6 GB. | The 4.5 GB figure in v0 was wrong for Ollama's builds; the QAT build is the best quality per gigabyte that fits. |
| 2026-09-05 | 03, 04 | The `mcp` Python package (the MCP SDK, running on Python 3.12) released its major version 2 between design and build: the server class is now `MCPServer` (was FastMCP) and the client is `mcp.client.client.Client`, which accepts a URL or an in-process server object. | Library moved between design and build; the in-process client made the tool server testable without sockets. |
| 2026-09-05 | 03 | Page extraction keeps HTML tables. | The first smoke test dropped the rate table from the Federal Reserve's H.15 page, which is exactly the fact the model searched for. |
| 2026-09-05 | 01 | Every paid API call records its token usage; the judge prints spend per candidate and the report prints the run total. | The user is paying from a small prepaid balance and asked for spend to be tracked. |
| 2026-09-05 | 09 | Docker's CLI is used from the Docker Desktop app bundle rather than /usr/local/bin. | Docker Desktop did not create the symlink; scripts add the bundle path to PATH. |
| 2026-09-05 | 09 | `scripts/dev_setup.sh` wraps `uv sync` and clears the macOS hidden flag on `.venv`. | The repo lives in an iCloud-synced Desktop folder; macOS flags dot-prefixed trees as hidden and Python 3.12.14 skips hidden `.pth` files, which made the project's packages vanish from the environment mid-session. |
