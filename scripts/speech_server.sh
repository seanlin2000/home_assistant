#!/bin/bash
# Build the speech server's environment and run it by hand: Qwen3-ASR and Qwen3-TTS over Wyoming, in one MLX process. Arguments go to speech-server.
# Usage: scripts/speech_server.sh [--asr-port 10301 --tts-port 10211]
#
# In production the speech launchd agent runs it (scripts/services.sh). The first run builds .venv-speech (a few minutes) and downloads both models at
# the revisions config/speech.toml pins (about 4 GiB).

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

"$PROJECT_DIR/scripts/speech_env.sh"
exec "$PROJECT_DIR/.venv-speech/bin/speech-server" "$@"
