"""Diagnostics beside scripts/strata_voice_latency.sh, started separately so the timed run is untouched. Every 15 s, one row in samples_extra.tsv:
every vm_stat counter, load average, the engine's physical footprint, and how much of each large file the engine maps is in RAM (mincore, the
dashboard's own measure). Every 3 minutes, Home Assistant's recent Assist pipeline runs go into pipeline_runs.jsonl, since Home Assistant keeps only
the last few. It stops when the timed run's script is gone.

    uv run python scripts/strata_voice_extra_sampler.py benchmark/results/strata_voice
"""

import csv
import subprocess
import sys
import time
from pathlib import Path

from dashboard.model_memory import resident_bytes

SAMPLE_SECONDS = 15
PIPELINE_PULL_SECONDS = 180
LARGE_FILE_BYTES = 100 * 1024**2
MODEL_FILE_SUFFIXES = (".gguf", ".bin", ".safetensors", ".pack", ".strata")
LIVE_CHECKOUT = Path.home() / "Code/home_assistant_live"
TIMED_RUN_SCRIPT = "strata_voice_latency.sh"


def main() -> None:
    out = Path(sys.argv[1]).resolve()
    model_files: set[Path] = set()
    last_pull, last_header = 0.0, ""
    while timed_run_is_alive():
        last_header = append_row(out / "samples_extra.tsv", sample(out, model_files), last_header)
        if time.time() - last_pull >= PIPELINE_PULL_SECONDS:
            pull_pipeline_runs(out / "pipeline_runs.jsonl")
            last_pull = time.time()
        time.sleep(SAMPLE_SECONDS)
    pull_pipeline_runs(out / "pipeline_runs.jsonl")


def timed_run_is_alive() -> bool:
    return subprocess.run(["pgrep", "-f", TIMED_RUN_SCRIPT], capture_output=True).returncode == 0


def sample(out: Path, model_files: set[Path]) -> dict[str, str]:
    label, _, phase = (out / "phase").read_text().strip().partition("\t")
    row = {"epoch": str(int(time.time())), "label": label, "phase": phase, "load_1m": command_output(["sysctl", "-n", "vm.loadavg"]).split()[1]}
    row |= vm_stat_counters()
    engine_pid = command_output(["pgrep", "-x", "llama-server"]) or command_output(["pgrep", "-x", "strata"])
    row["engine_pid"] = engine_pid.split("\n")[0]
    row["engine_footprint_mb"] = footprint_mb(row["engine_pid"])
    model_files.update(large_mapped_files(row["engine_pid"]))  # every file either engine has mapped, so the columns stay the same across engines
    for path in sorted(model_files):
        row[f"resident_mb:{path.name}"] = str(resident_bytes(path) // 1024**2)
    return row


def command_output(arguments: list[str]) -> str:
    return subprocess.run(arguments, capture_output=True, text=True).stdout.strip()


def vm_stat_counters() -> dict[str, str]:
    counters = {}
    for line in command_output(["vm_stat"]).splitlines()[1:]:
        name, _, value = line.partition(":")
        counters[name.strip().replace(" ", "_").replace('"', "")] = value.strip().rstrip(".")
    return counters


def footprint_mb(pid: str) -> str:
    if not pid:
        return ""
    for line in command_output(["footprint", "-p", pid]).splitlines():
        if "Footprint:" in line:
            amount, unit = line.split("Footprint:")[1].split()[:2]
            return str(round(float(amount) * {"KB": 1 / 1024, "MB": 1, "GB": 1024}[unit]))
    return ""


def large_mapped_files(pid: str) -> list[Path]:
    """The model files the engine has open or mapped, by size: the same GGUF shards for both engines, plus each engine's own drafter or pack."""
    if not pid:
        return []
    names = {line[1:] for line in command_output(["lsof", "-p", pid, "-Fn"]).splitlines() if line.startswith("n/")}
    return sorted(Path(name) for name in names if name.endswith(MODEL_FILE_SUFFIXES) and large_file(Path(name)))


def large_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size >= LARGE_FILE_BYTES
    except OSError:
        return False


def append_row(path: Path, row: dict[str, str], last_header: str) -> str:
    """Rows gain columns when the engine changes (its own files), so a "#"-prefixed header line goes before any row whose columns differ; returns it."""
    header = "\t".join(row)
    with path.open("a") as handle:
        if header != last_header:
            handle.write("#" + header + "\n")
        csv.writer(handle, delimiter="\t", lineterminator="\n").writerow(row.values())
    return header


def pull_pipeline_runs(output: Path) -> None:
    subprocess.run(["uv", "run", "python", "-m", "ops.pipeline_runs", str(output), "--pipeline", "Jarvis"], cwd=LIVE_CHECKOUT, capture_output=True)


if __name__ == "__main__":
    main()
