# Versions in the running system

What the proof of concept was built and measured with, so a future upgrade can be compared against a known state (design doc 09 §4 promised this file; doc 08 §6 says updates are applied deliberately, not automatically). Recorded from the laptop on 2026-09-07; the mini's column is filled in when the mini exists.

| Part | Laptop (M1 Pro, 16 GB) | Mac mini | How to check |
|---|---|---|---|
| macOS | 15.7.3 (24G419) | | `sw_vers` |
| Homebrew uv | 0.12.10 | | `uv --version` |
| Python in `.venv` | 3.12.14 | | `.venv/bin/python --version` |
| Ollama | 0.33.3 | | `ollama --version` |
| Default model | `gemma4:e4b-it-qat` id `ee6656371218` (6.1 GB) | | `ollama list` |
| Other models pulled | `gemma4:12b` `4eb23ef187e2` (Home Assistant's current agent), `qwen3.5:9b` `6488c96fa5fa`, `qwen3.5:4b` `2a654d98e6fb` | | `ollama list` |
| Docker Desktop / engine | 4.89.0 / 29.7.2 | | `docker version` |
| SearXNG image | `searxng/searxng:latest` (unpinned; see DEVIATIONS 09) | | `docker image inspect searxng/searxng:latest --format '{{index .RepoDigests 0}}'` |
| UTM | 4.7.5 | | `defaults read /Applications/UTM.app/Contents/Info CFBundleShortVersionString` |
| Home Assistant OS / Core | 18.2 / 2026.9.1 | | Settings → About, or `GET /api/config` (`version`) |
| Add-ons | Samba 12.10.0, Piper 2.3.4, openWakeWord 2.1.1, Music Assistant 2.10.2, ESPHome 2026.8.2 | | Settings → Add-ons |
| `studio_assistant` component | 0.2.0 (posts turn records) | | `custom_components/studio_assistant/manifest.json` |
| Key wheels (from `uv.lock`) | mcp 2.1.1, httpx 0.28.1, pydantic 2.13.5, ollama 0.6.2, trafilatura 2.2.0, wyoming-mlx-whisper 1.5.0, mlx-whisper 0.4.3, wyoming-kokoro-torch 3.2.0 | same lock | `grep -A1 '^name = "mcp"' uv.lock` |

## How to refresh this file

1. Python packages: `scripts/dev_setup.sh --upgrade`, review the `uv.lock` diff, `uv run pytest`, then update the wheels row. The component's `manifest.json` pins must move with the lock (`python -m ops.deploy status` reports a mismatch).
2. Homebrew software: `brew upgrade uv ollama` (and `brew upgrade --cask docker-desktop utm` when wanted), then rerun the checks in the last column. A new Ollama can change model quantization defaults; rerun `scripts/benchmark_llm.py` for the resident model before trusting old latency numbers.
3. Models: never re-pull a tag casually. `ollama pull` under the same tag can fetch a different build; note the new id here and rerun the benchmark pass that chose the model.
4. Home Assistant: monthly, from Settings → System → Updates, after reading the release notes; then `scripts/mini.sh deploy` is not needed, but `python -m ops.smoke` is.
5. Commit the updated table with the change that caused it.
