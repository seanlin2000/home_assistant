# home_assistant

A voice assistant for a small studio apartment that keeps its data at home. Say "Hey Jarvis", ask a question, and it answers from a language model running on a Mac in the room, searching the web through a self-hosted aggregator when the question needs current information. It also plays Spotify and reports the weather. Audio, transcripts, and the model never leave the local network.

## Status

Phase 2 (proof of concept) is running. Benchmark passes 1 to 5 are complete (`benchmark/results/version_N/report.md`). Pass 5 ran every runnable model under the same prompt: the Gemma 4 26B-A4B preview scored 232 of 280 and the Qwen 3.6 35B-A3B preview 208, against 186 for the dense Gemma 4 12B and 157 to 176 for the small models, which points at a 26B or 35B mixture-of-experts model on a 32 GB machine. Home Assistant OS runs in a VM on the Mac with our `studio_assistant` conversation agent deployed, Whisper and Kokoro served from the Mac, Piper and openWakeWord as add-ons, and a "Jarvis" Assist pipeline wired end to end. Typed questions through Home Assistant's conversation API answer from the local model, call the calculator, and search the web; the voice puck and music are not connected yet. The as-built state of each part is in `design_docs/v1/`, with departures from the original design in `design_docs/v1/DEVIATIONS.md`.

## How it fits together

```
  Voice PE puck ──▶ Home Assistant (Assist pipeline) ──▶ intents (music, weather)
                                   │
                                   └──▶ our conversation agent ──▶ Ollama + local model
                                                 │                       │ tool call
                                                 │                 web_search_mcp ──▶ SearXNG ──▶ the web
                                                 │                 (+ calculator_mcp tools, same server)
                                                 └──▶ Kokoro / Piper ──▶ puck speaker
  Music Assistant + Spotify ──▶ Sonos
```

## Documents

- `docs/phase2_walkthrough.md`: a hands-on tour of the running proof of concept, component by component.
- `docs/VERSIONS.md`: what the running system was built and measured with, and how to refresh it.
- `design_docs/v1/10_operations.md`: running, updating, and debugging the headless Mac mini from the laptop.
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

## Operating the Mac that runs it

Services on the Mac are launchd agents; the health check is a fifth agent that runs every five minutes and records what it sees (design doc 10).

```
scripts/services.sh install                    # write and load the agents (HEALTH_CHECK_FLAGS=--no-remediate on the laptop)
scripts/services.sh status                     # ports plus the last health snapshot
uv run python scripts/health_check.py --dry-run   # probe everything and say what the policy would do
uv run python scripts/ops_report.py --days 1 ~/Library/Logs/studio-assistant   # this machine's turns, health, Ollama speeds
```

The Mac mini is driven from the laptop over SSH once `MINI_HOST` is in `.env`:

```
scripts/mini.sh bootstrap        # once: Homebrew, clone, venv, agents, SearXNG, power, firewall, SSH keys-only
scripts/mini.sh push-env; scripts/mini.sh push-models; scripts/mini.sh push-vm
scripts/mini.sh deploy           # pinned commit -> tests on the mini -> restart what changed -> smoke test -> mark good or roll back
scripts/mini.sh logs; scripts/mini.sh report --days 7   # mirror the mini's logs into logs/mini/ and summarise them
```

## Benchmark

```
scripts/searxng.sh up                                  # local search aggregator (Docker)
uv run benchmark-run --run version_5 --candidate qwen3.5-9b   # one folder per pass of the agent; omit --candidate for every model
uv run benchmark-judge version_5 --export              # write judge cases for the Opus subagent; --import reads its verdicts back
uv run benchmark-report version_5                      # writes report.md and the review sheet
uv run benchmark-report version_5 --compare version_4  # with a table against the previous pass
uv run benchmark-manual claude-fable-5-1-manual-2 --run version_5 # replay the closed-book reference answers through the same loop
uv run python scripts/benchmark_llm.py --run version_5 # raw tokens per second per model
```

## License

See `LICENSE`.
