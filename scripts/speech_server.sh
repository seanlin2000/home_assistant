#!/bin/bash
# Build the speech server's environment and run it by hand: Qwen3-ASR over Wyoming, on MLX. Arguments go to speech-server.
# Usage: scripts/speech_server.sh [--asr-port 10301]
#
# In production the speech launchd agent runs it (scripts/services.sh), which also downloads the model first. By hand, the first run builds
# .venv-speech (a few minutes) and downloads the model at the revision config/speech.toml pins (about 2.5 GiB).

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

"$PROJECT_DIR/scripts/speech_env.sh"
exec "$PROJECT_DIR/.venv-speech/bin/speech-server" "$@"
