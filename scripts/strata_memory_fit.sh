#!/bin/bash
# Does Strata fit beside the whole production stack (Home Assistant VM, speech, Kokoro, harness, tool server, dashboard)? Strata phase 4a.
# For each variant: a llama-server baseline, then Strata on production's port 8090 under the full stack, three smoke rounds, the engine probe, and
# memory snapshots, then llama-server back before the next variant, so every variant is read against a baseline taken just before it.
# Usage: scripts/strata_memory_fit.sh <variant>[@context]...   e.g. dflash2-f16 lean1 lean2 lean3 plain lean2@17408
#   (variants: scripts/strata_trial.sh; @context starts with that context, to measure the K/V's cost per token; plain logs its K/V size)
# Results: benchmark/results/strata_phase4/memory_fit.txt (every snapshot), fit.tsv (one row a variant), engine_probe.md.
# Run it on the Studio, from this worktree.

set -u
RUN=strata_phase4
# shellcheck disable=SC1091  # the shared helpers beside this script
source "$(dirname "$0")/strata_trial_common.sh"
OUT="${TRIAL}/benchmark/results/${RUN}"
SETTLE_SECONDS=120

measure_variant() {
    local spec="$1" variant="${1%@*}" context=""
    [[ "$spec" == *@* ]] && context="${spec#*@}"
    sleep "$SETTLE_SECONDS"
    snapshot "llama-server baseline before ${spec}"
    local swap_before swapouts_before
    swap_before="$(swap_used_mb)"
    swapouts_before="$(vm_counter Swapouts)"
    stop_llama
    local started
    if ! started="$(STRATA_PORT=8090 STRATA_CONTEXT="${context:-34816}" "${TRIAL}/scripts/strata_trial.sh" start "$variant" 2>&1)"; then
        echo "$started"
        stop_strata
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
    free_after_smokes="$(memory_pressure_free_percent)"
    probe "$spec"
    snapshot "Strata ${spec} after the engine probe"
    echo "-- Strata's memory by region (pauses the idle engine for a moment)"
    vmmap --summary "$(pgrep -x strata)" 2>&1 | head -60
    local row
    row="${spec}\t${swap_before}\t${swap_after_smokes}\t$(swap_used_mb)\t$(counter_mb_since Swapouts "$swapouts_before")\t${free_after_smokes}\t$(strata_footprint)\t$(gpu_buffers)"
    stop_strata
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
