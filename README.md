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

All Python runs from a `uv`-managed virtual environment in this folder. See `design_docs/v0/09_dev_environment.md`. Once code exists:

```
brew install uv
uv python install 3.12
uv sync
uv run pytest
```

## License

See `LICENSE`.
