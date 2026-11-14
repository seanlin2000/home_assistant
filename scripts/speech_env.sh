#!/bin/bash
# Create or refresh the speech server's environment, .venv-speech, from the lock file.
# Usage: scripts/speech_env.sh
#
# The speech server has an environment of its own because mlx-audio needs a newer transformers than the voice group's Kokoro allows. services.sh install
# and a deploy that changes the lock run this; scripts/speech_server.sh runs it before starting the server by hand.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SPEECH_ENVIRONMENT="$PROJECT_DIR/.venv-speech"

cd "$PROJECT_DIR"
UV_PROJECT_ENVIRONMENT="$SPEECH_ENVIRONMENT" uv sync --locked --no-group voice --no-group docs --group speech --quiet
# The same iCloud hidden-flag guard as scripts/dev_setup.sh.
chflags -R nohidden "$SPEECH_ENVIRONMENT"
