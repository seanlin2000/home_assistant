#!/bin/bash
# Build the speech server's environment and run it by hand: Qwen3-ASR over Wyoming, on MLX. Arguments go to speech-server.
# Usage: scripts/speech_server.sh [--asr-port 10301]
#
# In production the speech launchd agent runs it (scripts/services.sh), which also downloads the model first. By hand, the first run builds
# .venv-speech (a few minutes) and downloads the model at the revision config/speech.toml pins (about 2.5 GiB).

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

"$PROJECT_DIR/scripts/speech_env.sh"
# MLX reads this only at startup, so it must be in the environment before the server starts; see install_agents in scripts/services.sh.
export MLX_METAL_RESIDENCY_REFRESH_INTERVAL_MS="${MLX_METAL_RESIDENCY_REFRESH_INTERVAL_MS:-1000}"
exec "$PROJECT_DIR/.venv-speech/bin/speech-server" "$@"
