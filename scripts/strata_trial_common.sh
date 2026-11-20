#!/bin/bash
# Shared by the Strata trial's checks on the Studio (scripts/strata_memory_fit.sh, scripts/strata_release_experiment.sh): memory snapshots, smoke
# tests, the engine probe, and moving production's port between llama-server and Strata. Sourced, not run; the caller sets RUN, the results folder's name.

# shellcheck disable=SC2034  # FLAG, STRATA_LOG and ENGINE_LOG are read by the scripts that source this file
TRIAL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# uv and Homebrew's tools, which a non-login shell over SSH does not have on its PATH
export PATH="${HOME}/.local/bin:/opt/homebrew/bin:${PATH}"
LIVE=~/Code/home_assistant_live
FLAG=~/Library/Logs/studio-assistant/maintenance
AGENT="gui/$(id -u)/com.studio-assistant"
API_KEY_FILE="${HOME}/Library/Application Support/studio-assistant/llama-server.key"
STRATA_LOG="${HOME}/strata/strata-trial.log"
ENGINE_LOG="${HOME}/strata/engine/strata-iq3_xxs.log"
PAGE_BYTES=16384
HARNESS_WARM_UP_SECONDS=45
ENGINE_EXIT_SECONDS=60

snapshot() {
    echo "== $1 ($(date +%T))"
    sysctl -n vm.swapusage
    memory_pressure | tail -1
    vm_stat | grep -E "Pages (free|active|inactive|wired down|occupied by compressor|stored in compressor)|File-backed|Anonymous|Pageins|Swapins|Swapouts"
    echo "-- by memory in RAM (CMPRS: compressed, including any part written to swap)"
    top -l 1 -o mem -n 12 -stats pid,command,mem,cmprs | tail -13
}

swap_used_mb() { sysctl -n vm.swapusage | sed -E 's/.*used = ([0-9.]+)M.*/\1/'; }
memory_pressure_free_percent() { memory_pressure | tail -1 | grep -oE '[0-9]+%' | tr -d '%'; }
# One of vm_stat's counters, e.g. vm_counter Pageins or vm_counter "Pages free"
vm_counter() { vm_stat | awk -v name="$1" -F: '$1 == name {gsub(/[ .]/, "", $2); print $2}'; }
counter_mb_since() { echo $((($(vm_counter "$1") - $2) * PAGE_BYTES / 1048576)); }
strata_footprint() { footprint -p "$(pgrep -x strata)" 2>/dev/null | sed -nE 's/.*Footprint: ([0-9.]+ [KMG]B).*/\1/p' | head -1; }
# vmmap's summary columns: virtual, resident, dirty, swapped (compressed or in swap), ...
gpu_buffers() { vmmap --summary "$(pgrep -x strata)" 2>/dev/null | awk '/^IOAccelerator \(graphics\)/ {print $4 " resident, " $6 " swapped"; exit}'; }

smoke() { (cd "$LIVE" && uv run python -m ops.smoke --full 2>&1 | tail -3); }
smoke_passes() { (cd "$LIVE" && uv run python -m ops.smoke --full >/dev/null 2>&1); }

stop_llama() {
    launchctl bootout "$AGENT.llama" 2>/dev/null
    while pgrep -x llama-server >/dev/null; do sleep 1; done
}

# Only llama-server's agent: services.sh start restarts every agent, and a restarted Kokoro or speech server starts with all its memory in RAM,
# which would flatter whichever engine runs next.
start_llama() {
    launchctl bootstrap "gui/$(id -u)" "${HOME}/Library/LaunchAgents/com.studio-assistant.llama.plist"
    until curl -sf -o /dev/null http://127.0.0.1:8090/health; do sleep 5; done
}

# Never two 47 GB engines at once: an engine that outlives its server is killed before anything else starts.
stop_strata() {
    "${TRIAL}/scripts/strata_trial.sh" stop || true
    local waited=0
    while pgrep -x strata >/dev/null && ((waited < ENGINE_EXIT_SECONDS)); do
        sleep 1
        ((waited += 1))
    done
    if pgrep -x strata >/dev/null; then
        echo "the engine outlived its server; killing pid $(pgrep -x strata | tr '\n' ' ')"
        pkill -9 -x strata
        while pgrep -x strata >/dev/null; do sleep 1; done
    fi
}

wait_for_harness() {
    # A smoke test sent while the harness restarts answers "I can't reach the assistant"; its warm-up reads both slots' prompts first.
    until nc -z 127.0.0.1 8770 2>/dev/null; do sleep 2; done
    sleep "$HARNESS_WARM_UP_SECONDS"
}

restart_harness() {
    launchctl kickstart -k "$AGENT.harness"
    wait_for_harness
}

restore_production() {
    pgrep -x strata >/dev/null && stop_strata
    pgrep -x llama-server >/dev/null || start_llama
    restart_harness
    (cd "$LIVE" && uv run python -m ops.deploy clear-maintenance >/dev/null)
}

probe() {
    (cd "$TRIAL" && uv run engine-probe --base-url http://127.0.0.1:8090 --api-key-file "$API_KEY_FILE" --process-name strata --label "strata-$1" --run "$RUN" 2>&1 | tail -4)
}
