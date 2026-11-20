#!/bin/bash
# Does Strata fit beside the whole production stack (Home Assistant VM, speech, Kokoro, harness, tool server, dashboard)? Strata phase 4a.
# For each variant: a llama-server baseline, then Strata on production's port 8090 under the full stack, three smoke rounds, the engine probe, and
# memory snapshots, then llama-server back before the next variant, so every variant is read against a baseline taken just before it.
# Usage: scripts/strata_memory_fit.sh <variant>[@context]...   e.g. dflash2-f16 lean1 lean2 lean3 plain lean2@17408
#   (variants: scripts/strata_trial.sh; @context starts with that context, to measure the K/V's cost per token; plain logs its K/V size)
# Results: benchmark/results/strata_phase4/memory_fit.txt (every snapshot), fit.tsv (one row a variant), engine_probe.md.
# Run it on the Studio, from this worktree.

set -u
TRIAL="$(cd "$(dirname "$0")/.." && pwd)"
# uv and Homebrew's tools, which a non-login shell over SSH does not have on its PATH
export PATH="${HOME}/.local/bin:/opt/homebrew/bin:${PATH}"
LIVE=~/Code/home_assistant_live
FLAG=~/Library/Logs/studio-assistant/maintenance
AGENT="gui/$(id -u)/com.studio-assistant"
API_KEY_FILE="${HOME}/Library/Application Support/studio-assistant/llama-server.key"
STRATA_LOG="${HOME}/strata/strata-trial.log"
RUN=strata_phase4
OUT="${TRIAL}/benchmark/results/${RUN}"
PAGE_BYTES=16384
SETTLE_SECONDS=120
HARNESS_WARM_UP_SECONDS=45

snapshot() {
    echo "== $1 ($(date +%T))"
    sysctl -n vm.swapusage
    memory_pressure | tail -1
    vm_stat | grep -E "Pages (free|active|inactive|wired down|occupied by compressor)|Swapins|Swapouts"
    echo "-- by memory in RAM (CMPRS: compressed, including any part written to swap)"
    top -l 1 -o mem -n 12 -stats pid,command,mem,cmprs | tail -13
}

swap_used_mb() { sysctl -n vm.swapusage | sed -E 's/.*used = ([0-9.]+)M.*/\1/'; }
free_percent() { memory_pressure | tail -1 | grep -oE '[0-9]+%' | tr -d '%'; }
swapouts() { vm_stat | awk '/Swapouts/ {gsub(/\./, "", $2); print $2}'; }
strata_footprint() { footprint -p "$(pgrep -x strata)" 2>/dev/null | sed -nE 's/.*Footprint: ([0-9.]+ [KMG]B).*/\1/p' | head -1; }
# vmmap's summary columns: virtual, resident, dirty, swapped (compressed or in swap), ...
gpu_buffers() { vmmap --summary "$(pgrep -x strata)" 2>/dev/null | awk '/^IOAccelerator \(graphics\)/ {print $4 " resident, " $6 " swapped"; exit}'; }

smoke() { (cd "$LIVE" && uv run python -m ops.smoke --full 2>&1 | tail -3); }

stop_llama() {
    launchctl bootout "$AGENT.llama" 2>/dev/null
    while pgrep -x llama-server >/dev/null; do sleep 1; done
}

start_llama() {
    (cd "$LIVE" && scripts/services.sh start 2>&1 | tail -1)
    until curl -sf -o /dev/null http://127.0.0.1:8090/health; do sleep 5; done
}

restore_production() {
    pgrep -x strata >/dev/null && "${TRIAL}/scripts/strata_trial.sh" stop
    pgrep -x llama-server >/dev/null || start_llama
    launchctl kickstart -k "$AGENT.harness"
    wait_for_harness
    (cd "$LIVE" && uv run python -m ops.deploy clear-maintenance >/dev/null)
}

wait_for_harness() {
    # A smoke test sent while the harness restarts answers "I can't reach the assistant"; its warm-up reads both slots' prompts first.
    until nc -z 127.0.0.1 8770 2>/dev/null; do sleep 2; done
    sleep "$HARNESS_WARM_UP_SECONDS"
}

probe() {
    (cd "$TRIAL" && uv run engine-probe --base-url http://127.0.0.1:8090 --api-key-file "$API_KEY_FILE" --process-name strata --label "strata-$1" --run "$RUN" 2>&1 | tail -4)
}

measure_variant() {
    local spec="$1" variant="${1%@*}" context=""
    [[ "$spec" == *@* ]] && context="${spec#*@}"
    sleep "$SETTLE_SECONDS"
    snapshot "llama-server baseline before ${spec}"
    local swap_before swapouts_before
    swap_before="$(swap_used_mb)"
    swapouts_before="$(swapouts)"
    stop_llama
    local started
    if ! started="$(STRATA_PORT=8090 STRATA_CONTEXT="${context:-34816}" "${TRIAL}/scripts/strata_trial.sh" start "$variant" 2>&1)"; then
        echo "$started"
        start_llama
        return 1
    fi
    echo "${started%%$'\n'*}"
    launchctl kickstart -k "$AGENT.harness"
    sleep 30
    snapshot "Strata ${spec} under the stack, idle"
    echo "-- the engine's own words on its buffers"
    grep -E "batch slots|K/V|GB|GiB|MiB" "$STRATA_LOG" | grep -v "^INFO" | head -40
    smoke
    smoke
    smoke
    snapshot "Strata ${spec} after three smoke rounds"
    local swap_after_smokes free_after_smokes
    swap_after_smokes="$(swap_used_mb)"
    free_after_smokes="$(free_percent)"
    probe "$spec"
    snapshot "Strata ${spec} after the engine probe"
    echo "-- Strata's memory by region (pauses the idle engine for a moment)"
    vmmap --summary "$(pgrep -x strata)" 2>&1 | head -60
    local row
    row="${spec}\t${swap_before}\t${swap_after_smokes}\t$(swap_used_mb)\t$((($(swapouts) - swapouts_before) * PAGE_BYTES / 1048576))\t${free_after_smokes}\t$(strata_footprint)\t$(gpu_buffers)"
    "${TRIAL}/scripts/strata_trial.sh" stop
    start_llama
    launchctl kickstart -k "$AGENT.harness"
    printf "%b\n" "$row" >>"$OUT/fit.tsv"
}

main() {
    (($# > 0)) || {
        echo "usage: scripts/strata_memory_fit.sh <variant>[@context]..." >&2
        exit 1
    }
    [[ -f "$OUT/fit.tsv" ]] || printf "variant\tswap MB before (llama)\tswap MB after smokes\tswap MB after probe\tswapped out MB\tfree %% after smokes\tStrata footprint\tGPU buffers\n" >"$OUT/fit.tsv"
    trap restore_production EXIT
    touch "$FLAG"
    (cd "$TRIAL" && git log --oneline -1)
    for spec in "$@"; do
        echo "######## ${spec}"
        measure_variant "$spec" || echo "${spec} did not start; see ${STRATA_LOG}"
    done
    restore_production
    echo "== production restored on llama-server"
    smoke
    snapshot "production restored on llama-server"
    column -t -s $'\t' "$OUT/fit.tsv"
    echo MEMORY_FIT_DONE
}

mkdir -p "$OUT"
main "$@" 2>&1 | tee -a "$OUT/memory_fit.txt"
