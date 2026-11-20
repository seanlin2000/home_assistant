#!/bin/bash
# Start the speech lab and open it in the browser: Qwen3-ASR, Qwen3-TTS and OmniVoice on this Mac, at http://127.0.0.1:8795. Ctrl-C stops it.
# Usage: scripts/speech_lab.sh
#
# The lab has an environment of its own, .venv-speech-lab, because mlx-audio needs a newer transformers than the voice agents' Kokoro allows:
# installing it into .venv would break whisper and kokoro. The first run builds that environment (a few minutes), and each model downloads from
# Hugging Face the first time the page uses it (2 to 3 GiB each).

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LAB_ENVIRONMENT="$PROJECT_DIR/.venv-speech-lab"
LAB_URL="http://127.0.0.1:8795"

if curl -sf "$LAB_URL/api/catalog" >/dev/null; then
    echo "speech lab already running: $LAB_URL"
    open "$LAB_URL"
    exit 0
fi

cd "$PROJECT_DIR"
UV_PROJECT_ENVIRONMENT="$LAB_ENVIRONMENT" uv sync --locked --no-group voice --group speech-lab --quiet
chflags -R nohidden "$LAB_ENVIRONMENT"

open_when_listening() {
    local half_seconds=0
    until curl -sf "$LAB_URL/api/catalog" >/dev/null; do
        ((half_seconds >= 60)) && return 1
        sleep 0.5
        half_seconds=$((half_seconds + 1))
    done
    echo "speech lab: $LAB_URL"
    open "$LAB_URL"
}

open_when_listening &
exec "$LAB_ENVIRONMENT/bin/speech-lab"
