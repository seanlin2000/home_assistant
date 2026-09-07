#!/usr/bin/env bash
# Drive the headless Mac mini from the laptop over SSH (design doc 10). Everything here runs on the laptop.
#
#   scripts/mini.sh bootstrap [--dry-run|--skip-system]   first-time setup on the mini (after Remote Login is on): Homebrew, clone, venv, agents
#   scripts/mini.sh deploy [--ref REF] [--full-smoke] [--skip-tests]
#                                                        pinned commit -> tests on the mini -> restart what changed -> smoke -> mark good or roll back
#   scripts/mini.sh rollback                              return the mini to its last good commit, then smoke
#   scripts/mini.sh status                                commit, last good, maintenance flag, listening ports, last health snapshot
#   scripts/mini.sh logs [NAME]                           rsync the mini's log directory to logs/mini/ (plus HA pipeline runs); NAME tails one log live
#   scripts/mini.sh report [--days N]                     pull logs, then summarise the last N days (default 7)
#   scripts/mini.sh push-env                              copy .env to the mini (chmod 600)
#   scripts/mini.sh push-models [--pull]                  copy the default Ollama model, digest-exact (or have the mini pull it)
#   scripts/mini.sh push-vm                               copy the Home Assistant UTM bundle (local VM must be stopped)
#   scripts/mini.sh ssh [CMD]                             a shell (or one command) on the mini
#
# Reads MINI_HOST, MINI_USER (default: your user name), MINI_PROJECT_DIR (default: code/home_assistant, relative to the mini's home) and
# MINI_MODEL (default: gemma4:e4b-it-qat) from .env. SSH must already work with a key: ssh-copy-id "$MINI_USER@$MINI_HOST".
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"
if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi
MINI_HOST="${MINI_HOST:-}"
MINI_USER="${MINI_USER:-$USER}"
MINI_PROJECT_DIR="${MINI_PROJECT_DIR:-code/home_assistant}"
MINI_MODEL="${MINI_MODEL:-gemma4:e4b-it-qat}"
REMOTE="$MINI_USER@$MINI_HOST"
REMOTE_LOG_DIR="Library/Logs/studio-assistant"
LOCAL_LOGS="$PROJECT_DIR/logs/mini"
PYTHON="$PROJECT_DIR/.venv/bin/python"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10)
UTM_BUNDLE="Library/Containers/com.utmapp.UTM/Data/Documents/${HAOS_VM_NAME:-Home Assistant}.utm"

usage() {
    sed -n '2,17p' "$0"
    exit 1
}

need_host() {
    if [[ -z "$MINI_HOST" ]]; then
        echo "MINI_HOST is not set in .env" >&2
        exit 1
    fi
}

remote() {
    # Run a command on the mini inside the project checkout with Homebrew on PATH (non-interactive SSH shells do not have it).
    # shellcheck disable=SC2029  # the project dir and command are meant to expand here, on the laptop
    ssh "${SSH_OPTS[@]}" "$REMOTE" "cd '$MINI_PROJECT_DIR' && export PATH=/opt/homebrew/bin:\$PATH && $*"
}

remote_deploy() {
    remote ".venv/bin/python -m ops.deploy $*"
}

json_field() {
    # $1 json text, $2 field -> value (python keeps this dependency-free on the laptop side)
    "$PYTHON" -c 'import json,sys; v=json.loads(sys.argv[1]).get(sys.argv[2]); print(v if not isinstance(v,(dict,list)) else json.dumps(v))' "$1" "$2"
}

smoke() {
    "$PYTHON" -m ops.smoke "$@"
}

cmd_bootstrap() {
    need_host
    local flags=("$@")
    ssh "${SSH_OPTS[@]}" "$REMOTE" 'mkdir -p /tmp/studio-bootstrap'
    scp -q "${SSH_OPTS[@]}" scripts/bootstrap_mac.sh Brewfile "$REMOTE:/tmp/studio-bootstrap/"
    # -t: the bootstrap asks for the user's password once for the sudo steps (power, firewall, sshd).
    ssh -t "${SSH_OPTS[@]}" "$REMOTE" "bash /tmp/studio-bootstrap/bootstrap_mac.sh --repo '$(git remote get-url origin)' --dir '$MINI_PROJECT_DIR' ${flags[*]:-}"
}

cmd_deploy() {
    need_host
    local ref="" skip_tests=""
    local smoke_flags=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
        --ref)
            ref="$2"
            shift 2
            ;;
        --full-smoke)
            smoke_flags=(--full)
            shift
            ;;
        --skip-tests)
            skip_tests="--skip-tests"
            shift
            ;;
        *) usage ;;
        esac
    done
    if [[ -z "$ref" ]]; then
        if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
            echo "deploy: the laptop's working tree has uncommitted changes; commit or stash them first (or pass --ref)" >&2
            exit 1
        fi
        ref="$(git rev-parse HEAD)"
    fi
    local sha
    sha="$(git rev-parse --verify "$ref^{commit}")"
    git fetch --quiet origin
    if ! git branch -r --contains "$sha" | grep -q 'origin/'; then
        echo "deploy: $sha is not on any origin branch; git push first (the mini can only fetch what the remote has)" >&2
        exit 1
    fi
    echo "deploy: $sha  $(git log -1 --format=%s "$sha")"
    local result
    result="$(remote_deploy apply --ref "$sha" $skip_tests)" || {
        echo "$result"
        echo "deploy: apply failed on the mini; the maintenance flag is set (scripts/mini.sh status). Fix, then deploy again or 'scripts/mini.sh rollback'." >&2
        exit 1
    }
    echo "$result"
    if [[ "$(json_field "$result" applied)" != "True" ]]; then
        echo "deploy: nothing applied ($(json_field "$result" note)); clearing the maintenance flag"
        remote_deploy clear-maintenance >/dev/null
        exit 0
    fi
    if smoke "${smoke_flags[@]}"; then
        remote_deploy mark-good "$sha" >/dev/null
        remote_deploy clear-maintenance >/dev/null
        echo "deploy: done, $sha is the mini's last good commit"
        return 0
    fi
    echo "deploy: smoke test FAILED; rolling the mini back" >&2
    cmd_rollback_inner "${smoke_flags[@]}"
    echo "deploy: rolled back after a failed smoke test; the new commit was NOT kept" >&2
    exit 1
}

cmd_rollback_inner() {
    # $@: flags for the smoke test
    remote_deploy rollback || {
        echo "rollback: the mini could not return to its last good commit; maintenance flag left set. Restore by hand: scripts/mini.sh ssh" >&2
        exit 2
    }
    if smoke "$@"; then
        remote_deploy clear-maintenance >/dev/null
        echo "rollback: the mini is back on its last good commit and answering"
    else
        echo "rollback: smoke test still failing after the rollback; maintenance flag left set, self-healing is off. Look before restarting anything: scripts/mini.sh logs" >&2
        exit 2
    fi
}

cmd_status() {
    need_host
    remote_deploy status
    remote scripts/services.sh status
}

cmd_logs() {
    need_host
    if [[ $# -gt 0 ]]; then
        exec ssh -t "${SSH_OPTS[@]}" "$REMOTE" "tail -n 100 -f '$REMOTE_LOG_DIR/$1.log'"
    fi
    mkdir -p "$LOCAL_LOGS"
    # No --delete: the laptop keeps history the mini has pruned.
    rsync -az --exclude 'deploy.lock' "$REMOTE:$REMOTE_LOG_DIR/" "$LOCAL_LOGS/"
    "$PYTHON" -m ops.pipeline_runs "$LOCAL_LOGS/pipeline_runs.jsonl"
    echo "logs: mirrored to $LOCAL_LOGS"
}

cmd_report() {
    local days=7
    if [[ "${1:-}" == "--days" ]]; then days="$2"; fi
    if [[ -n "$MINI_HOST" ]]; then cmd_logs; fi
    "$PYTHON" scripts/ops_report.py --days "$days" "$LOCAL_LOGS"
}

cmd_push_env() {
    need_host
    scp -q "${SSH_OPTS[@]}" .env "$REMOTE:$MINI_PROJECT_DIR/.env"
    remote "chmod 600 .env"
    echo "push-env: .env copied"
}

cmd_push_models() {
    need_host
    if [[ "${1:-}" == "--pull" ]]; then
        remote "ollama pull '$MINI_MODEL'"
        return
    fi
    local models="$HOME/.ollama/models" name tag manifest
    name="${MINI_MODEL%%:*}"
    tag="${MINI_MODEL#*:}"
    [[ "$MINI_MODEL" == *:* ]] || tag=latest
    manifest="manifests/registry.ollama.ai/library/$name/$tag"
    if [[ ! -f "$models/$manifest" ]]; then
        echo "push-models: $MINI_MODEL is not pulled on this laptop ($models/$manifest missing)" >&2
        exit 1
    fi
    # The manifest names every blob by digest; copying exactly those files gives the mini the same bytes the benchmark ran on.
    local list
    list="$(mktemp)"
    {
        echo "$manifest"
        "$PYTHON" -c 'import json,sys; m=json.load(open(sys.argv[1])); print("\n".join("blobs/"+d["digest"].replace(":","-") for d in [m["config"]]+m["layers"]))' "$models/$manifest"
    } >"$list"
    echo "push-models: $MINI_MODEL, $(wc -l <"$list" | tr -d ' ') files"
    rsync -az --progress --files-from="$list" "$models/" "$REMOTE:.ollama/models/"
    rm -f "$list"
    remote "ollama list | grep -F '$name:$tag'" && echo "push-models: the mini sees $MINI_MODEL"
}

cmd_push_vm() {
    need_host
    if [[ ! -d "$HOME/$UTM_BUNDLE" ]]; then
        echo "push-vm: no VM bundle at ~/$UTM_BUNDLE" >&2
        exit 1
    fi
    if command -v utmctl >/dev/null && [[ "$(utmctl status "${HAOS_VM_NAME:-Home Assistant}" 2>/dev/null)" == "started" ]]; then
        echo "push-vm: stop the local VM first (scripts/haos_vm.sh stop); copying a running disk gives a corrupt image" >&2
        exit 1
    fi
    echo "push-vm: copying ~/$UTM_BUNDLE (the disk is large; rsync resumes if interrupted)"
    # shellcheck disable=SC2029
    ssh "${SSH_OPTS[@]}" "$REMOTE" "mkdir -p '$(dirname "$UTM_BUNDLE")'"
    rsync -az --progress "$HOME/$UTM_BUNDLE/" "$REMOTE:'$UTM_BUNDLE/'"
    echo "push-vm: done. On the mini: open UTM once so it registers the bundle, then scripts/haos_vm.sh start. The VM keeps its MAC address, so a DHCP reservation follows it."
}

case "${1:-}" in
bootstrap)
    shift
    cmd_bootstrap "$@"
    ;;
deploy)
    shift
    cmd_deploy "$@"
    ;;
rollback)
    need_host
    cmd_rollback_inner
    ;;
status) cmd_status ;;
logs)
    shift
    cmd_logs "$@"
    ;;
report)
    shift
    cmd_report "$@"
    ;;
push-env) cmd_push_env ;;
push-models)
    shift
    cmd_push_models "$@"
    ;;
push-vm) cmd_push_vm ;;
ssh)
    need_host
    shift
    if [[ $# -gt 0 ]]; then remote "$*"; else exec ssh -t "$REMOTE"; fi
    ;;
*) usage ;;
esac
