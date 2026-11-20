#!/usr/bin/env bash
# Build Strata at exactly the commit config/serving.toml pins, with our patches, and check it (design doc v2/02 section 3.10). Run it at the Studio's
# keyboard; it never updates Strata on its own.
#
#   scripts/strata.sh install   clone the pinned commit (detached), run Strata's setup, apply the patches, build, check. An install already at the
#                               pin with the patches built only checks; one at another commit stops and points at update.
#   scripts/strata.sh update    after a PR changed the pinned commit: take the patches off, check out the new commit, put them back, build, check.
#                               The running engine keeps its old binary until the next deploy or scripts/services.sh restart llama.
#   scripts/strata.sh check     the launch's own check: the pinned commit, exactly our patches, a binary built from them
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"
STRATA_REPOSITORY="https://github.com/Niko1221/Strata"
BUILD_DIR="engine/build-metal"

fail() {
    echo "strata.sh: $*" >&2
    exit 1
}

usage() {
    sed -n '2,10p' "$0"
    exit 1
}

read_pin() {
    # One value per line: the install folder, the commit, its release name, the model folder, the context, the port, setup's config, then the patches.
    "$PYTHON" - <<'PY'
from serving.settings import load_serving_config

config = load_serving_config()
model = config.served_model
if model.strata is None:
    raise SystemExit(f"config/serving.toml has no [models.\"{config.server.model}\".strata] table")
strata = model.strata
print(strata.install_path, strata.commit, strata.release, model.gguf_path.parent, model.context_tokens, config.server.port, strata.setup_config, sep="\n")
print(*strata.patch_paths, sep="\n")
PY
}

load_pin() {
    local values line
    values="$(read_pin)" || exit 1
    PIN=()
    while IFS= read -r line; do PIN+=("$line"); done <<<"$values" # macOS's bash 3.2 has no mapfile
    INSTALL_DIR="${PIN[0]}" COMMIT="${PIN[1]}" RELEASE="${PIN[2]}" MODEL_DIR="${PIN[3]}" CONTEXT_TOKENS="${PIN[4]}" PORT="${PIN[5]}" SETUP_CONFIG="${PIN[6]}"
    PATCHES=("${PIN[@]:7}")
}

check() {
    "$PYTHON" -c 'from serving.settings import load_serving_config
from serving.strata import verify_strata_install
verify_strata_install(load_serving_config().served_model.strata)' || exit 1
    echo "Strata $RELEASE (${COMMIT:0:12}) at $INSTALL_DIR: the pinned commit with our patches, built"
}

head_commit() { git -C "$INSTALL_DIR" rev-parse HEAD; }

install_strata() {
    if [[ -d "$INSTALL_DIR/.git" ]]; then
        [[ "$(head_commit)" == "$COMMIT" ]] || fail "$INSTALL_DIR is at $(head_commit | cut -c1-12), not the pinned ${COMMIT:0:12}; run scripts/strata.sh update"
        if "$PYTHON" -c 'from serving.settings import load_serving_config
from serving.strata import strata_install_problems
raise SystemExit(1 if strata_install_problems(load_serving_config().served_model.strata) else 0)'; then
            check
            return
        fi
    else
        clone_pinned_commit
    fi
    [[ -f "$INSTALL_DIR/$SETUP_CONFIG" ]] || run_setup
    apply_patches
    build_engine
    check
}

clone_pinned_commit() {
    xcode-select -p >/dev/null 2>&1 || fail "Strata builds its engine with the Command Line Tools: xcode-select --install"
    git clone "$STRATA_REPOSITORY" "$INSTALL_DIR"
    git -C "$INSTALL_DIR" checkout --detach "$COMMIT"
}

run_setup() {
    # Setup counts 64 GB as a streaming Mac and may write a 40 GB copy of the experts that a resident run never reads; the copy is deleted.
    (cd "$INSTALL_DIR" && ./setup.sh --model IQ3_XXS --gguf-dir "$MODEL_DIR" --vision no --context "$CONTEXT_TOKENS" --port "$PORT" --no-browser --no-start --yes)
    rm -f "$MODEL_DIR"/*.experts
    fetch_drafter
}

fetch_drafter() {
    # Setup fetches DFlash2 only for the sets it defaults to, and a start never downloads, so the drafter is fetched here.
    (
        cd "$INSTALL_DIR/terminal" && .venv/bin/python - "$INSTALL_DIR/$SETUP_CONFIG" <<'PY'
import json, sys
from pathlib import Path
from strata_control import drafting_fetch
config = json.loads(Path(sys.argv[1]).read_text())
print("DFlash2 drafter:", drafting_fetch.ensure_for(Path(config["tokenizer"]).parent.parent.parent, model_name=config["model_name"], backend="metal"))
PY
    )
}

apply_patches() {
    [[ -z "$(git -C "$INSTALL_DIR" status --porcelain --untracked-files=no)" ]] || fail "$INSTALL_DIR has changes that are not ours; look at git -C $INSTALL_DIR diff"
    local patch
    for patch in "${PATCHES[@]}"; do
        git -C "$INSTALL_DIR" apply "$patch"
    done
}

build_engine() {
    local cmake
    cmake="$(find "$INSTALL_DIR/terminal/.venv" -path '*/cmake/data/bin/cmake' | head -1)"
    [[ -n "$cmake" ]] || fail "no cmake in Strata's Python environment; run Strata's setup again"
    PATH="$INSTALL_DIR/terminal/.venv/bin:$PATH" "$cmake" --build "$INSTALL_DIR/$BUILD_DIR"
}

update_strata() {
    [[ -d "$INSTALL_DIR/.git" ]] || fail "no Strata at $INSTALL_DIR; run scripts/strata.sh install"
    [[ "$(head_commit)" != "$COMMIT" ]] || fail "already at the pinned ${COMMIT:0:12}; run scripts/strata.sh install to finish or check it"
    # This checkout's patches are the new commit's, so they cannot reverse the old ones; the old changes are discarded instead, but only when every
    # changed file is one our patches touch, so nothing else is lost.
    local changed
    changed="$(git -C "$INSTALL_DIR" diff --name-only HEAD | grep -vxF -f <(git -C "$INSTALL_DIR" apply --numstat "${PATCHES[@]}" | cut -f3) || true)"
    [[ -z "$changed" ]] || fail "$INSTALL_DIR has changes our patches do not explain: $changed"
    git -C "$INSTALL_DIR" checkout -- .
    git -C "$INSTALL_DIR" fetch origin
    git -C "$INSTALL_DIR" checkout --detach "$COMMIT"
    apply_patches
    build_engine
    check
}

[[ $# -eq 1 ]] || usage
load_pin
case "$1" in
install) install_strata ;;
update) update_strata ;;
check) check ;;
*) usage ;;
esac
