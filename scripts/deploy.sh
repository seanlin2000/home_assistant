#!/usr/bin/env bash
# Deploy what is on GitHub's main to this Mac, at its keyboard (docs/DEPLOYING.md, design doc v2/10 section 3.11).
#
#   cd ~/Code/home_assistant_live && scripts/deploy.sh
#   scripts/deploy.sh --dry-run        what would restart and why; changes nothing
#   scripts/deploy.sh --ref SHA        a particular commit instead of origin/main
#   scripts/deploy.sh --full-smoke     also ask a searched question
#
# Tests the commit, restarts only what changed, waits for the model, asks the test question, then keeps the commit or goes back to the last good
# one. Exit codes: 0 deployed or nothing to do, 1 not deployed and the old commit is answering, 2 a person has to look.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"
exec "$PROJECT_DIR/.venv/bin/python" -m ops.deploy_here "$@"
