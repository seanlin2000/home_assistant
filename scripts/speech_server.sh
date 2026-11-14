#!/bin/bash
# Build the speech server's environment and run it: Qwen3-ASR and Qwen3-TTS over Wyoming, in one MLX process. Arguments go to speech-server.
# Usage: scripts/speech_server.sh [--asr-port 10301 --tts-port 10211]
#
# The server has an environment of its own, .venv-speech, because mlx-audio needs a newer transformers than the voice agents' Kokoro allows: installing
# it into .venv would break whisper and kokoro. The first run builds it (a few minutes) and downloads both models at the revisions config/speech.toml
# pins (about 4 GiB).

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SPEECH_ENVIRONMENT="$PROJECT_DIR/.venv-speech"

cd "$PROJECT_DIR"
UV_PROJECT_ENVIRONMENT="$SPEECH_ENVIRONMENT" uv sync --locked --no-group voice --no-group docs --group speech --quiet
chflags -R nohidden "$SPEECH_ENVIRONMENT"
exec "$SPEECH_ENVIRONMENT/bin/speech-server" "$@"
