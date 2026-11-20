#!/bin/bash
# What the user hears under each engine: spoken benchmark questions through Home Assistant's Assist pipeline (Qwen3-ASR, the agent, Kokoro), for
# llama-server as production runs it and for Strata lean2 with the host weight copies released, alternated llama, Strata, llama, Strata.
# One round: settle, one typed question (so the round does not start on a cold prompt cache), 10 quiet minutes, A11 (the first question after
# quiet), a burst of six questions back to back (long explanation, calculator, restaurant tool, search, finance reasoning, search with the
# calculator), 10 more quiet minutes, then B90 (a cold question that needs a tool).
# A sampler writes memory every 5 seconds through all of it: swap, swap-ins and -outs, file reads, memory_pressure's free %, wired, the compressor,
# and the engine, Qwen3-ASR, Kokoro and the HA VM each in RAM and compressed. Production returns to llama-server on any exit.
# Usage: scripts/strata_voice_latency.sh
# Results: benchmark/results/strata_voice/ (voice.txt the log, voice_latency.jsonl one row a question, samples.tsv, summary.md).
# Run it on the Studio, from this worktree.

set -u
RUN=strata_voice
# shellcheck disable=SC1091  # the shared helpers beside this script
source "$(dirname "$0")/strata_trial_common.sh"
OUT="${TRIAL}/benchmark/results/${RUN}"
SETTLE_SECONDS=120
QUIET_SECONDS=600
SAMPLE_SECONDS=5
FIRST_AFTER_QUIET=A11
BURST=(A77 A80 B93 B91 A84 B92) # A83 is spoken in 19 s, past Home Assistant's 15-second limit on one voice command
COLD_TOOL=B90
ROUNDS=(llama-1 strata-1 llama-2 strata-2)
sampler_pid=""

set_phase() { # label, phase
    printf "%s\t%s\n" "$1" "$2" >"$OUT/phase"
    echo "== $1: $2 ($(date +%T))"
}

ask() { # label, then question ids
    local label="$1"
    shift
    (cd "$TRIAL" && uv run voice-latency ask --run "$RUN" --env-file "$LIVE/.env" --label "$label" "$@")
}

# top's sizes ("9234M", "512K", "2G", "0B", sometimes with a trailing + or -) as whole MB
to_mb() { awk '{v = $1; sub(/[+-]$/, "", v); unit = substr(v, length(v)); n = v + 0; if (unit == "K") n /= 1024; else if (unit == "G") n *= 1024; else if (unit == "B") n /= 1048576; printf "%.0f", n}'; }

# One process's memory in RAM and compressed, in MB, tab-separated; empty fields when it is not running
process_memory() { # pid
    [[ -n "$1" ]] || {
        printf "\t"
        return
    }
    local line
    line="$(top -l 1 -pid "$1" -stats pid,mem,cmprs | awk -v pid="$1" '$1 == pid {print $2, $3}')"
    printf "%s\t%s" "$(echo "${line% *}" | to_mb)" "$(echo "${line#* }" | to_mb)"
}

engine_pid_now() { pgrep -x llama-server || pgrep -x strata; }

sample_once() {
    local stats
    stats="$(vm_stat | awk -F: '{gsub(/[ .]/, "", $2)} $1 == "Swapins" {si = $2} $1 == "Swapouts" {so = $2} $1 == "Pageins" {pi = $2}
        $1 == "Pages wired down" {w = $2} $1 == "Pages occupied by compressor" {c = $2} END {printf "%s\t%s\t%s\t%s\t%s", si, so, pi, w, c}')"
    printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$(date +%s)" "$(cat "$OUT/phase")" "$(swap_used_mb)" "$stats" "$(memory_pressure_free_percent)" \
        "$(process_memory "$(engine_pid_now | head -1)")" "$(process_memory "$(pgrep -f 'bin/speech-server' | head -1)")" \
        "$(process_memory "$(pgrep -f 'bin/kokoro-server' | head -1)")" "$(process_memory "$(pgrep -f QEMULauncher | head -1)")" >>"$OUT/samples.tsv"
}

sample_forever() {
    while true; do
        sample_once
        sleep "$SAMPLE_SECONDS"
    done
}

start_strata_released() {
    stop_llama
    engine_log_start="$(wc -l <"$ENGINE_LOG")"
    if ! STRATA_PORT=8090 STRATA_RELEASE_HOST_WEIGHTS=release STRATA_RELEASE_MIN_MIB=32 "${TRIAL}/scripts/strata_trial.sh" start lean2 | head -1; then
        echo "Strata lean2 did not start; see ${STRATA_LOG}"
        return 1
    fi
    engine_pid="$(pgrep -x strata)"
    restart_harness
}

# The release happened and the engine stayed healthy: the same process all round, and no given-back, abort or error line in its log.
report_strata_health() { # label
    local log
    log="$(tail -n +"$((engine_log_start + 1))" "$ENGINE_LOG")"
    echo "-- $1: $(echo "$log" | grep "strata metal resident: release" | tail -1)"
    echo "-- $1: engine pid ${engine_pid} at the start, $(pgrep -x strata || echo none) now; $(echo "$log" | grep -ciE "given back|abort|assert|segmentation|ERR") error lines"
    cp "$ENGINE_LOG" "$OUT/engine_$1.log"
}

run_round() { # label
    local label="$1"
    set_phase "$label" start
    if [[ "$label" == strata-* ]]; then start_strata_released || return 1; else restart_harness; fi
    set_phase "$label" settle
    sleep "$SETTLE_SECONDS"
    # After a harness restart the first real question re-reads the whole ~7,900-token prompt (the warm-up's cached state cannot be reused), which
    # production pays only after a deploy; one typed question first makes the question after quiet measure the quiet, not the restart.
    set_phase "$label" prime
    smoke
    set_phase "$label" quiet
    sleep "$QUIET_SECONDS"
    set_phase "$label" first-after-quiet
    ask "$label" "$FIRST_AFTER_QUIET"
    set_phase "$label" burst
    ask "$label" "${BURST[@]}"
    set_phase "$label" quiet-2
    sleep "$QUIET_SECONDS"
    set_phase "$label" cold-tool
    ask "$label" "$COLD_TOOL"
    snapshot "$label: end of the round"
    if [[ "$label" == strata-* ]]; then
        report_strata_health "$label"
        set_phase switch back-to-llama
        stop_strata
        start_llama
    fi
}

finish() {
    [[ -n "$sampler_pid" ]] && kill "$sampler_pid" 2>/dev/null
    restore_production
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
    (cd "$TRIAL" && git log --oneline -1)
    [[ -d "$OUT/audio" ]] || (cd "$TRIAL" && uv run voice-latency prepare --run "$RUN")
    [[ -f "$OUT/samples.tsv" ]] || printf "epoch\tlabel\tphase\tswap_used_mb\tswapins\tswapouts\tpageins\twired_pages\tcompressor_pages\tpressure_free_percent\tengine_mb\tengine_cmprs_mb\tspeech_mb\tspeech_cmprs_mb\tkokoro_mb\tkokoro_cmprs_mb\tvm_mb\tvm_cmprs_mb\n" >"$OUT/samples.tsv"
    trap finish EXIT
    touch "$FLAG"
    set_phase setup start
    sample_forever &
    sampler_pid=$!
    for label in "${ROUNDS[@]}"; do
        run_round "$label" || {
            echo "== ${label} failed; stopping"
            break
        }
    done
    kill "$sampler_pid" 2>/dev/null
    sampler_pid=""
    restore_production
    echo "== production restored on llama-server"
    smoke
    (cd "$TRIAL" && uv run voice-latency summarize --run "$RUN") | tee "$OUT/summary.md"
    echo VOICE_LATENCY_DONE
}

mkdir -p "$OUT"
main "$@" 2>&1 | tee -a "$OUT/voice.txt"
