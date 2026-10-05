#!/bin/bash
# Create or refresh the project virtual environment from the lock file.
# Usage: scripts/dev_setup.sh [--upgrade]
#
# macOS marks dot-prefixed items in iCloud-synced folders (such as ~/Desktop) as hidden, recursively.
# Python 3.12.14 and later refuse to load hidden .pth files, which silently breaks the editable install
# of this project. Clearing the flag after every sync keeps `uv run` working.

set -eu

cd "$(dirname "$0")/.."

if [ "${1:-}" = "--upgrade" ]; then
    uv lock --upgrade
fi
# --locked refuses a uv.lock that no longer matches pyproject.toml, so a forgotten `uv lock` fails here instead of being installed.
uv sync --locked

chflags -R nohidden .venv
git config core.hooksPath .githooks
uv run python -c "import assistant_core, benchmark, web_search_mcp; print('environment ready:', __import__('sys').executable)"
