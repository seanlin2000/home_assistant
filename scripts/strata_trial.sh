#!/bin/bash
# The Strata trial on the Studio: install Strata beside our Flash Next file, start it on the bench port in one of the variants below, and stop it.
# Production must be stopped first (scripts/services.sh stop). Run it at the Studio's own keyboard, not over SSH.
# Usage: scripts/strata_trial.sh preflight|install|start <variant>|stop
# Variants: plain, dflash2, dflash2-f16, lowmem, and the phase 4 trims of dflash2-f16, each adding to the one before:
#   lean1  no conversation cache (--conversation-cache-mib 0): with route_questions off only the conversation runs, so nothing is parked
#   lean2  prompt chunks of 1024 rows instead of 2048 (STRATA_METAL_PROMPT_CHUNK), halving the prompt buffers
#   lean3  the hyper-connection matrices read as BF16 from the file (STRATA_HC_Q8=0) instead of a 0.63 GB Q8_0 copy
# STRATA_CONTEXT=N starts with a context of N tokens instead of 34,816, to measure what the K/V costs per token.
# STRATA_RELEASE_HOST_WEIGHTS=poison|release turns on the release experiment's engine patch (scripts/strata_release_experiment.sh), and
# STRATA_RELEASE_MIN_MIB sets the smallest allocation it touches; STRATA_RELEASE_PROJECTIONS=1 also touches the 300 native projection matrices
# (scripts/strata_patches/release_projections.patch, on top of release_host_weights.patch). STRATA_KEEPALIVE_WINDOW_S sets how long after the last request Strata's
# GPU keep-alive holds its buffers wired (Strata's default: 120 s; scripts/strata_voice_latency.sh).
#
# Every variant keeps the model resident (STRATA_METAL_STREAM=0): Strata's own sizing rule would stream it from the SSD on 64 GB, though llama-server
# holds the same file in memory. plain runs two request slots, one each for the conversation and the router as llama-server's two slots do. The DFlash2
# variants run one: on Metal, Strata starts no drafter beside two slots (strata_control/drafting.py, blocked_by), so the router shares the slot.

set -eu

STRATA_VERSION="v0.2.16"
STRATA_REPOSITORY="https://github.com/Niko1221/Strata"
STRATA_DIR="${HOME}/strata"
MODEL_DIR="${HOME}/models/gguf/Qwen3.8-Flash-Next-GSQ-RCO/IQ3_XXS"
API_KEY_FILE="${HOME}/Library/Application Support/studio-assistant/llama-server.key"
# STRATA_PORT=8090 puts Strata where production llama-server listens, so the whole stack runs on it (the memory-fit check)
PORT="${STRATA_PORT:-8092}"
CONTEXT_TOKENS="${STRATA_CONTEXT:-34816}"
REASONING_BUDGET_TOKENS=3072
HEALTH_TIMEOUT_SECONDS=900
ENGINE_EXIT_TIMEOUT_SECONDS=60
TRIAL_CONFIG="${STRATA_DIR}/strata-trial.json"
PID_FILE="${STRATA_DIR}/strata-trial.pid"
LOG_FILE="${STRATA_DIR}/strata-trial.log"

fail() {
    echo "strata_trial: $*" >&2
    exit 1
}

preflight() {
    if pgrep -x llama-server >/dev/null; then
        fail "llama-server still runs; stop it first: scripts/services.sh stop"
    fi
    pmset -g | grep -qE '^ *sleep +0( |$)' || fail "the Mac may sleep mid-run; set it with: sudo pmset -a sleep 0"
    xcode-select -p >/dev/null 2>&1 || fail "Strata builds its engine with the Command Line Tools: xcode-select --install"
    ls "${MODEL_DIR}"/*-00001-of-00002.gguf "${MODEL_DIR}"/*-00002-of-00002.gguf >/dev/null || fail "the model's two shards are not in ${MODEL_DIR}"
    [[ -f "${API_KEY_FILE}" ]] || fail "no API key file at ${API_KEY_FILE}"
    echo "free disk: $(df -h "${HOME}" | awk 'NR == 2 {print $4}')"
    echo "preflight ok"
}

install_strata() {
    preflight
    [[ -d "${STRATA_DIR}" ]] || git clone --branch "${STRATA_VERSION}" --depth 1 "${STRATA_REPOSITORY}" "${STRATA_DIR}"
    (cd "${STRATA_DIR}" && ./setup.sh --model IQ3_XXS --gguf-dir "${MODEL_DIR}" --vision no --context "${CONTEXT_TOKENS}" --port "${PORT}" --no-browser --no-start --yes)
    # Setup counts 64 GB as a streaming Mac and may write a 40 GB copy of the experts that a resident run never reads.
    rm -f "${MODEL_DIR}"/*.experts
    fetch_drafter
}

fetch_drafter() {
    # Setup fetches DFlash2 only for the sets it defaults to; a start never downloads, so the drafter is fetched here, into the folder a start reads.
    (
        cd "$(strata_terminal_dir)" && "$(strata_python)" - "$(setup_config)" <<'PY'
import json, sys
from pathlib import Path
from strata_control import drafting_fetch
config = json.loads(Path(sys.argv[1]).read_text())
data_dir = Path(config["tokenizer"]).parent.parent.parent
print("DFlash2 drafter:", drafting_fetch.ensure_for(data_dir, model_name=config["model_name"], backend="metal"))
PY
    )
}

start_variant() {
    local variant="$1"
    [[ ! -f "${PID_FILE}" ]] || fail "a trial server may still run (pid $(cat "${PID_FILE}")); run: scripts/strata_trial.sh stop"
    write_trial_config "${variant}"
    # cd on its own line: with "cd && nohup ... &", $! is the subshell running the pair, and stop would kill that instead of the server.
    (
        cd "$(strata_terminal_dir)"
        nohup "$(strata_python)" serve/server.py --engine strata --config "${TRIAL_CONFIG}" --port "${PORT}" >"${LOG_FILE}" 2>&1 &
        echo $! >"${PID_FILE}"
    )
    wait_until_healthy
    echo "Strata (${variant}) answers on ${PORT}; log: ${LOG_FILE}"
    echo "probe it: uv run engine-probe --base-url http://127.0.0.1:${PORT} --api-key-file \"${API_KEY_FILE}\" --process-name strata --label strata-${variant} --run <run>"
}

write_trial_config() {
    # Setup's own config, with the trial's memory, drafter, slots, budget and key on top. The key file is the one llama-server and the harness read.
    /usr/bin/python3 -I - "$(setup_config)" "${TRIAL_CONFIG}" "$1" "${API_KEY_FILE}" "${PORT}" "${REASONING_BUDGET_TOKENS}" "${CONTEXT_TOKENS}" \
        "${STRATA_RELEASE_HOST_WEIGHTS:-}" "${STRATA_RELEASE_MIN_MIB:-}" "${STRATA_RELEASE_PROJECTIONS:-}" "${STRATA_KEEPALIVE_WINDOW_S:-}" <<'PY'
import json, sys
from pathlib import Path
source, target, variant, key_file, port, budget, context, release_mode, release_min_mib, release_projections, keepalive_window = sys.argv[1:]
config = json.loads(Path(source).read_text())
f16 = {"STRATA_METAL_F16": "1"}
lean1 = {**f16}
lean2 = {**lean1, "STRATA_METAL_PROMPT_CHUNK": "1024"}
lean3 = {**lean2, "STRATA_HC_Q8": "0"}
variant_environments = {"plain": {}, "dflash2": {}, "dflash2-f16": f16, "lowmem": {"STRATA_METAL_PROMPT_CHUNK": "1024"}, "lean1": lean1, "lean2": lean2, "lean3": lean3}
if variant not in variant_environments:
    sys.exit(f"unknown variant {variant}: {', '.join(variant_environments)}")
drafts_with_dflash2 = variant not in ("plain", "lowmem")
arguments = config["args"]
# Setup writes --suffix-draft 0 only for a Mac it streams on; a resident config leaves Strata's own look-ahead in the text on.
if "--suffix-draft" in arguments:
    del arguments[arguments.index("--suffix-draft"):arguments.index("--suffix-draft") + 2]
arguments[arguments.index("--max-context") + 1] = context
if variant.startswith("lean"):
    arguments += ["--conversation-cache-mib", "0"]
release = {"STRATA_METAL_RELEASE_HOST_WEIGHTS": release_mode} if release_mode else {}
if release_mode and release_min_mib:
    release["STRATA_METAL_RELEASE_MIN_MIB"] = release_min_mib
if release_mode and release_projections == "1":
    release["STRATA_METAL_RELEASE_PROJECTIONS"] = "1"
keepalive = {"STRATA_METAL_KEEPALIVE_WINDOW_S": keepalive_window} if keepalive_window else {}
config.update(env={"STRATA_METAL_STREAM": "0", **variant_environments[variant], **release, **keepalive}, parallel=1 if drafts_with_dflash2 else 2, port=int(port), reasoning_budget_tokens=int(budget),
              api_key=Path(key_file).read_text().strip(), drafting="dflash2" if drafts_with_dflash2 else "off", open_browser=False)
Path(target).write_text(json.dumps(config, indent=2))
Path(target).chmod(0o600)
PY
}

wait_until_healthy() {
    local waited=0
    until curl -s -o /dev/null --fail --max-time 3 "http://127.0.0.1:${PORT}/health"; do
        kill -0 "$(cat "${PID_FILE}")" 2>/dev/null || {
            rm -f "${PID_FILE}"
            fail "the server stopped while loading; see ${LOG_FILE}"
        }
        ((waited += 5))
        ((waited < HEALTH_TIMEOUT_SECONDS)) || fail "no answer on ${PORT} after ${HEALTH_TIMEOUT_SECONDS} s; see ${LOG_FILE}"
        sleep 5
    done
}

stop_trial() {
    [[ -f "${PID_FILE}" ]] || {
        echo "no trial server recorded"
        return
    }
    kill "$(cat "${PID_FILE}")" 2>/dev/null || true
    rm -f "${PID_FILE}"
    wait_until_engine_exits
    if pgrep -x strata >/dev/null; then
        echo "an engine process named strata still runs (pid $(pgrep -x strata | tr '\n' ' ')); stop it before starting llama-server again" >&2
        exit 1
    fi
    echo "stopped"
}

wait_until_engine_exits() {
    # The server stops its engine as it exits; unmapping 47 GB of experts takes a few seconds.
    local waited=0
    while pgrep -x strata >/dev/null && ((waited < ENGINE_EXIT_TIMEOUT_SECONDS)); do
        sleep 1
        ((waited += 1))
    done
}

setup_config() {
    local found
    found="$(find "${STRATA_DIR}" -maxdepth 3 -name 'strata-iq3_xxs.json' | head -1)"
    [[ -n "${found}" ]] || fail "no strata-iq3_xxs.json under ${STRATA_DIR}; run: scripts/strata_trial.sh install"
    echo "${found}"
}

strata_python() {
    local found
    found="$(find "${STRATA_DIR}" -maxdepth 4 -path '*/.venv/bin/python' | head -1)"
    [[ -n "${found}" ]] || fail "no Python environment under ${STRATA_DIR}; run: scripts/strata_trial.sh install"
    echo "${found}"
}

strata_terminal_dir() {
    local server
    server="$(find "${STRATA_DIR}" -maxdepth 3 -path '*/serve/server.py' | head -1)"
    [[ -n "${server}" ]] || fail "no serve/server.py under ${STRATA_DIR}"
    dirname "$(dirname "${server}")"
}

case "${1:-}" in
preflight) preflight ;;
install) install_strata ;;
start) start_variant "${2:?usage: scripts/strata_trial.sh start plain|dflash2|dflash2-f16|lowmem|lean1|lean2|lean3}" ;;
stop) stop_trial ;;
*) fail "usage: scripts/strata_trial.sh preflight|install|start <variant>|stop" ;;
esac
