#!/bin/bash
# The Strata release experiment (phase 4). In resident mode Strata keeps the host code's device copies of the weights, which its Metal window never
# reads; macOS compresses them, and compressed they still cost RAM. The engine patch (scripts/strata_patches/release_host_weights.patch, built into
# ~/strata/engine/build-metal/strata) overwrites them ("poison") or gives them back ("release") at the first request. lean2 runs on production's
# port under the full stack, three times:
#   off      the patched engine with the switch off: the reference answers, read twice across a restart to show they repeat
#   poison   the copies overwritten with 0xFF: a changed answer or a dead engine means something still reads them
#   release  the copies given back: the same answers, and the memory they held
# off and release also time a first request after IDLE_SECONDS of quiet, with the file reads (pageins) and swap-ins it costs.
# The first failed check stops the experiment; production returns to llama-server on any exit.
# Usage: scripts/strata_release_experiment.sh [smallest allocation touched, in MiB; default 32]
# Results: benchmark/results/strata_release/ (experiment.txt every snapshot, checks.tsv, results.tsv, greedy_check.jsonl, engine_probe.md).
# Run it on the Studio, from this worktree.

set -u
RUN=strata_release
# shellcheck disable=SC1091  # the shared helpers beside this script
source "$(dirname "$0")/strata_trial_common.sh"
OUT="${TRIAL}/benchmark/results/${RUN}"
SETTLE_SECONDS=120
IDLE_SECONDS=600
MIN_HANDLED_GB=1.4
MAX_DECODE_DROP=0.05
MAX_SWAP_GROWTH_MB=500
MIN_MEMORY_PRESSURE_FREE_PERCENT=10
MIN_RELEASE_SAVING_MB=1024
MIN_MIB="${1:-32}"
failed=0
engine_pid=""
engine_log_start=0

record_check() { # run, check, pass|FAIL, detail
    printf "%s\t%s\t%s\t%s\n" "$1" "$2" "$3" "$4" | tee -a "$OUT/checks.tsv"
    [[ "$3" == pass ]] || failed=1
}

check_that() { # run, check, detail, then the command whose exit status decides it
    local run="$1" name="$2" detail="$3"
    shift 3
    if "$@"; then record_check "$run" "$name" pass "$detail"; else record_check "$run" "$name" FAIL "$detail"; fi
}

start_engine() {
    local mode="$1" release_mode=""
    [[ "$mode" == off ]] || release_mode="$mode"
    engine_log_start="$(wc -l <"$ENGINE_LOG")"
    if ! STRATA_PORT=8090 STRATA_RELEASE_HOST_WEIGHTS="$release_mode" STRATA_RELEASE_MIN_MIB="$MIN_MIB" "${TRIAL}/scripts/strata_trial.sh" start lean2 | head -1; then
        record_check "$mode" start FAIL "Strata lean2 did not start; see ${STRATA_LOG}"
        return 1
    fi
    engine_pid="$(pgrep -x strata)"
    restart_harness
}

engine_log_since_start() { tail -n +"$((engine_log_start + 1))" "$ENGINE_LOG"; }

greedy() { # label, then greedy-check's own options
    local label="$1"
    shift
    (cd "$TRIAL" && uv run greedy-check --base-url http://127.0.0.1:8090 --api-key-file "$API_KEY_FILE" --run "$RUN" --label "$label" "$@")
}

handled_gb() { engine_log_since_start | sed -nE "s/.*strata metal resident: $1: ([0-9.]+) GB.*/\1/p" | tail -1; }
at_least() { awk -v value="$1" -v floor="$2" 'BEGIN {exit !(value + 0 >= floor + 0)}'; }
at_most() { awk -v value="$1" -v ceiling="$2" 'BEGIN {exit !(value + 0 <= ceiling + 0)}'; }
no_engine_errors() { ! engine_log_since_start | grep -qiE "given back|abort|assert|segmentation|ERR"; }
engine_unchanged() { [[ "$(pgrep -x strata)" == "$engine_pid" ]]; }
three_smokes_pass() { smoke_passes && smoke_passes && smoke_passes; }

median_decode() {
    (
        cd "$TRIAL" && uv run python - "$OUT/engine_probe.jsonl" "strata-$1" <<'PY'
import json, statistics, sys
rows = [json.loads(line) for line in open(sys.argv[1]) if line.strip()]
print(statistics.median([row for row in rows if row["label"] == sys.argv[2]][-1]["decode_rates"]))
PY
    )
}

decode_within_tolerance() { awk -v run="$1" -v reference="$2" -v drop="$MAX_DECODE_DROP" 'BEGIN {exit !(run >= reference * (1 - drop))}'; }

# The reference answers, the same answers after a restart, then the measurements every run takes.
run_off() {
    start_engine off || return 1
    snapshot "off: loaded, harness warmed up"
    greedy off-1
    stop_strata
    start_engine off || return 1
    check_that off F0-answers-repeat "off-2 against off-1, across a restart" greedy off-2 --compare-to off-1
    measure off
}

run_switched() {
    local mode="$1"
    start_engine "$mode" || return 1
    snapshot "${mode}: loaded, harness warmed up"
    engine_log_since_start | grep "strata metal resident:"
    local handled
    handled="$(handled_gb "$mode")"
    check_that "$mode" F1-copies-handled "${handled:-none} GB ${mode}ed (at least ${MIN_HANDLED_GB})" at_least "${handled:-0}" "$MIN_HANDLED_GB"
    check_that "$mode" F2-same-answers "${mode} against off-1" greedy "$mode" --compare-to off-1
    measure "$mode"
}

measure() {
    local mode="$1"
    check_that "$mode" F5-smokes "three smoke rounds through the harness" three_smokes_pass
    snapshot "${mode}: after three smoke rounds"
    local swap_after_smokes pressure_free free_pages_mb compressor_mb footprint buffers
    swap_after_smokes="$(swap_used_mb)"
    pressure_free="$(memory_pressure_free_percent)"
    free_pages_mb=$(($(vm_counter "Pages free") * PAGE_BYTES / 1048576))
    compressor_mb=$(($(vm_counter "Pages occupied by compressor") * PAGE_BYTES / 1048576))
    footprint="$(strata_footprint)"
    buffers="$(gpu_buffers)"
    probe "lean2-${mode}"
    local decode
    decode="$(median_decode "lean2-${mode}")"
    [[ "$mode" == off ]] || check_that "$mode" F3-decode "median ${decode} tok/s against off's ${off_decode}" decode_within_tolerance "$decode" "$off_decode"
    [[ "$mode" == off ]] && off_decode="$decode"
    local idle_pageins_mb="-" idle_swapins_mb="-" request_pageins_mb="-" request_swapins_mb="-"
    if [[ "$mode" != poison ]]; then
        idle_test "$mode"
    fi
    echo "-- Strata's memory by region (pauses the idle engine for a moment)"
    vmmap --summary "$(pgrep -x strata)" 2>&1 | head -60
    check_that "$mode" F4-engine-healthy "no given-back, abort or error line in the engine log; engine pid ${engine_pid} unchanged" eval "no_engine_errors && engine_unchanged"
    local swap_growth_mb
    swap_growth_mb="$(awk -v after="$swap_after_smokes" -v before="$baseline_swap_mb" 'BEGIN {printf "%.0f", after - before}')"
    printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$mode" "$baseline_swap_mb" "$swap_after_smokes" "$swap_growth_mb" "$pressure_free" "$free_pages_mb" \
        "$compressor_mb" "$footprint" "$buffers" "$decode" "$idle_pageins_mb" "$idle_swapins_mb" "${request_pageins_mb}/${request_swapins_mb}" >>"$OUT/results.tsv"
    if [[ "$mode" == release ]]; then
        check_that release G4-swap "swap grew ${swap_growth_mb} MB over its llama-server baseline (at most ${MAX_SWAP_GROWTH_MB})" at_most "$swap_growth_mb" "$MAX_SWAP_GROWTH_MB"
        check_that release G4-memory-pressure-free "memory_pressure's free ${pressure_free}% (at least ${MIN_MEMORY_PRESSURE_FREE_PERCENT}%)" at_least "$pressure_free" "$MIN_MEMORY_PRESSURE_FREE_PERCENT"
        check_that release F6-compressor-smaller "compressor ${compressor_mb} MB against off's ${off_compressor_mb} MB (at least ${MIN_RELEASE_SAVING_MB} MB less)" \
            at_most "$compressor_mb" "$((off_compressor_mb - MIN_RELEASE_SAVING_MB))"
    fi
    [[ "$mode" == off ]] && off_compressor_mb="$compressor_mb"
    return 0
}

# A first request after a quiet spell, as the assistant is used: what the quiet cost in file reads (pageins) and swap-ins, and how long the answer took.
idle_test() {
    local mode="$1" pageins swapins
    snapshot "${mode}: before ${IDLE_SECONDS} s of quiet"
    pageins="$(vm_counter Pageins)"
    swapins="$(vm_counter Swapins)"
    sleep "$IDLE_SECONDS"
    snapshot "${mode}: after ${IDLE_SECONDS} s of quiet"
    idle_pageins_mb="$(counter_mb_since Pageins "$pageins")"
    idle_swapins_mb="$(counter_mb_since Swapins "$swapins")"
    pageins="$(vm_counter Pageins)"
    swapins="$(vm_counter Swapins)"
    greedy "${mode}-after-quiet" --prompts short
    request_pageins_mb="$(counter_mb_since Pageins "$pageins")"
    request_swapins_mb="$(counter_mb_since Swapins "$swapins")"
    echo "-- quiet: ${idle_pageins_mb} MB read from files, ${idle_swapins_mb} MB swapped in; first request: ${request_pageins_mb} MB read from files, ${request_swapins_mb} MB swapped in"
}

run_mode() {
    local mode="$1"
    echo "######## ${mode} (allocations of ${MIN_MIB} MiB or more)"
    sleep "$SETTLE_SECONDS"
    snapshot "llama-server baseline before ${mode}"
    baseline_swap_mb="$(swap_used_mb)"
    stop_llama
    if [[ "$mode" == off ]]; then run_off; else run_switched "$mode"; fi
    cp "$ENGINE_LOG" "$OUT/engine_${mode}.log"
    stop_strata
    start_llama
    restart_harness
}

main() {
    pgrep -x strata >/dev/null && {
        echo "an engine named strata already runs; stop it first" >&2
        exit 1
    }
    strings "${HOME}/strata/engine/build-metal/strata" | grep -q "STRATA_METAL_RELEASE_HOST_WEIGHTS" || {
        echo "the engine at ~/strata/engine/build-metal/strata is not built with the release patch" >&2
        exit 1
    }
    [[ -f "$OUT/checks.tsv" ]] || printf "run\tcheck\tresult\tdetail\n" >"$OUT/checks.tsv"
    [[ -f "$OUT/results.tsv" ]] || printf "run\tswap MB before (llama)\tswap MB after smokes\tswap growth MB\tmemory_pressure free %%\tfree pages MB\tcompressor MB\tStrata footprint\tGPU buffers\tdecode tok/s\tquiet: pageins MB\tquiet: swap-ins MB\tfirst request: pageins/swap-ins MB\n" >"$OUT/results.tsv"
    trap restore_production EXIT
    touch "$FLAG"
    (cd "$TRIAL" && git log --oneline -1)
    for mode in off poison release; do
        run_mode "$mode"
        if ((failed)); then
            echo "== a check failed in the ${mode} run; stopping before the next run"
            break
        fi
    done
    restore_production
    echo "== production restored on llama-server"
    smoke
    snapshot "production restored on llama-server"
    column -t -s $'\t' "$OUT/checks.tsv"
    column -t -s $'\t' "$OUT/results.tsv"
    echo RELEASE_EXPERIMENT_DONE
}

mkdir -p "$OUT"
main "$@" 2>&1 | tee -a "$OUT/experiment.txt"
