# home_assistant

A voice assistant for a small studio apartment that keeps its data at home. Say "Hey Jarvis", ask a question, and it answers from a language model running on a Mac in the room, searching the web through a self-hosted aggregator when the question needs current information. It also plays Spotify and reports the weather. Audio, transcripts, and the model never leave the local network.

## Status

Phase 0. The design is written and frozen in `design_docs/v0/`. No code yet. The next step is a benchmark that runs twenty real-world questions through candidate open-weight models on a 16 GB MacBook to choose the model and, from that, the hardware.

## How it fits together

```
  Voice PE puck ──▶ Home Assistant (Assist pipeline) ──▶ intents (music, weather)
                                   │
                                   └──▶ our conversation agent ──▶ Ollama + local model
                                                 │                       │ tool call
                                                 │                 web_search_mcp ──▶ SearXNG ──▶ the web
                                                 └──▶ Kokoro / Piper ──▶ puck speaker
  Music Assistant + Spotify ──▶ Sonos
```

## Documents

- `design_docs/README.md`: how the docs are versioned and the reading order.
- `design_docs/v0/00_system_overview.md`: start here.
- `CLAUDE.md` and `claude_docs/CLEAN_CODE.md`: coding conventions.

## Development

All Python runs from a `uv`-managed virtual environment in this folder. See `design_docs/v1/09_dev_environment.md`.

```
brew install uv shfmt shellcheck
uv python install 3.12
scripts/dev_setup.sh          # uv sync --frozen, then clears the macOS hidden flag on .venv
uv run pytest
scripts/lint.sh               # black, isort, shfmt, shellcheck
```

Upgrade dependencies deliberately with `scripts/dev_setup.sh --upgrade`, review the `uv.lock` diff, run the tests, commit.

## Benchmark

```
scripts/searxng.sh up                                  # local search aggregator (Docker)
uv run benchmark-run --candidate qwen3.5-9b            # or omit --candidate for every model in benchmark/config.yaml
uv run benchmark-judge 2026-09-05                      # needs ANTHROPIC_API_KEY in .env
uv run benchmark-report 2026-09-05                     # writes report.md and the review sheet
uv run benchmark-manual claude-fable-5-1-manual       # replay hand-written reference answers through the same loop
uv run python scripts/benchmark_llm.py                 # raw tokens per second per model
```

## License

See `LICENSE`.
