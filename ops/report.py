"""Summarise the mirrored logs from the mini (design doc 10 §3.7): what the assistant did, how fast, what failed, what the machine did to itself.

Reads only the local copy in logs/mini/ (turns/*.jsonl, health.jsonl, pipeline_runs.jsonl, ollama.log); it never talks to the mini.
"""

import re
import statistics
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from assistant_core.turn_record import TurnRecord
from ops.health import Snapshot
from ops.pipeline_runs import PipelineRun
from utils.jsonl_utils import read_jsonl
from web_search_mcp.turn_log import TurnLog

PRINT_TIMING = re.compile(r"print_timing:.*\|\s+(prompt eval time|eval time)\s+=\s+([\d.]+) ms /\s+(\d+) tokens")
OLLAMA_TIMESTAMP = re.compile(r"time=(\d{4}-\d{2}-\d{2})")


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def fmt(value: float | None, unit: str = "s", digits: int = 1) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}{unit}"


def load_turns(log_dir: Path, since: date) -> list[TurnRecord]:
    return TurnLog(log_dir / "turns").read_since(since)


def load_snapshots(log_dir: Path, since: date) -> list[Snapshot]:
    path = log_dir / "health.jsonl"
    if not path.exists():
        return []
    return [snapshot for snapshot in read_jsonl(path, Snapshot) if snapshot.checked_at[:10] >= since.isoformat()]


def load_pipeline_runs(log_dir: Path, since: date) -> list[PipelineRun]:
    path = log_dir / "pipeline_runs.jsonl"
    if not path.exists():
        return []
    return [run for run in read_jsonl(path, PipelineRun) if run.started_at[:10] >= since.isoformat()]


def ollama_speeds(log_dir: Path, since: date) -> dict[str, list[float]]:
    """Tokens per second from Ollama's own `print_timing` lines (every request, not only the assistant's). Lines carry no timestamp of their
    own, so each is dated by the most recent `time=` line above it."""
    path = log_dir / "ollama.log"
    speeds: dict[str, list[float]] = {"prompt": [], "generation": []}
    if not path.exists():
        return speeds
    current_day = ""
    for line in path.read_text(errors="replace").splitlines():
        stamp = OLLAMA_TIMESTAMP.search(line)
        if stamp:
            current_day = stamp.group(1)
        match = PRINT_TIMING.search(line)
        if not match or (current_day and current_day < since.isoformat()):
            continue
        kind, ms, tokens = match.group(1), float(match.group(2)), int(match.group(3))
        if ms <= 0 or tokens < 2:
            continue
        speeds["prompt" if kind.startswith("prompt") else "generation"].append(tokens / (ms / 1000))
    return speeds


# ---------------------------------------------------------------- sections


def turns_section(turns: list[TurnRecord]) -> list[str]:
    lines = [f"Turns: {len(turns)}"]
    if not turns:
        return lines + ["  (no turn records in this window)"]
    per_day = Counter(turn.recorded_at[:10] for turn in turns)
    lines.append("  per day: " + ", ".join(f"{day} {count}" for day, count in sorted(per_day.items())))
    first_word = [turn.time_to_first_spoken_seconds for turn in turns if turn.time_to_first_spoken_seconds is not None]
    totals = [turn.total_seconds for turn in turns]
    lines.append(f"  time to first spoken word: median {fmt(statistics.median(first_word) if first_word else None)}, p90 {fmt(percentile(first_word, 0.9))}")
    lines.append(f"  total per turn: median {fmt(statistics.median(totals))}, p90 {fmt(percentile(totals, 0.9))}, max {fmt(max(totals))}")
    routes = Counter((turn.route.route.value if turn.route else "none") for turn in turns)
    lines.append("  routes: " + ", ".join(f"{route} {count}" for route, count in routes.most_common()))
    tools = Counter(call.name for turn in turns for call in turn.tool_calls)
    errors = Counter(call.name for turn in turns for call in turn.tool_calls if call.error)
    if tools:
        lines.append("  tool calls: " + ", ".join(f"{name} {count}" + (f" ({errors[name]} failed)" if errors[name] else "") for name, count in tools.most_common()))
    flags = {
        "error": sum(1 for turn in turns if turn.error),
        "empty answer": sum(1 for turn in turns if not turn.final_answer.strip()),
        "truncated": sum(1 for turn in turns if turn.truncated),
        "hit tool round cap": sum(1 for turn in turns if turn.hit_tool_round_cap),
        "malformed tool calls": sum(turn.malformed_tool_call_count for turn in turns),
        "empty completion retries": sum(turn.empty_completion_retries for turn in turns),
    }
    lines.append("  failure flags: " + ", ".join(f"{name} {count}" for name, count in flags.items() if count) if any(flags.values()) else "  failure flags: none")
    prompt_tokens = [call.prompt_tokens for turn in turns for call in turn.model_calls if call.prompt_tokens]
    if prompt_tokens:
        lines.append(f"  prompt tokens per model call: median {statistics.median(prompt_tokens):.0f}, max {max(prompt_tokens)}")
    slow = sorted(turns, key=lambda turn: turn.total_seconds, reverse=True)[:3]
    lines.append("  slowest: " + "; ".join(f"{turn.total_seconds:.0f}s {turn.user_text[:50]!r}" for turn in slow))
    models = Counter(turn.model for turn in turns)
    lines.append("  models: " + ", ".join(f"{model} {count}" for model, count in models.most_common()))
    return lines


def health_section(snapshots: list[Snapshot]) -> list[str]:
    lines = [f"Health checks: {len(snapshots)}"]
    if not snapshots:
        return lines + ["  (no snapshots in this window)"]
    incidents: list[str] = []
    failing_since: dict[str, str] = {}
    for snapshot in snapshots:
        for name, check in snapshot.checks.items():
            if check.ok is False and name not in failing_since:
                failing_since[name] = snapshot.checked_at
            elif check.ok is not False and name in failing_since:
                incidents.append(f"{name} down {failing_since.pop(name)[5:16]} -> {snapshot.checked_at[5:16]}")
    for name, since in failing_since.items():
        incidents.append(f"{name} down since {since[5:16]} (still failing at the last check)")
    lines.append(f"  incidents: {len(incidents)}" + ("" if not incidents else "\n    " + "\n    ".join(incidents[:12])))
    actions = [action for snapshot in snapshots for action in snapshot.actions]
    lines.append(f"  actions taken by the machine: {len(actions)}" + ("" if not actions else "\n    " + "\n    ".join(actions[-8:])))
    maintenance = sum(1 for snapshot in snapshots if snapshot.maintenance)
    if maintenance:
        lines.append(f"  checks skipped under the maintenance flag: {maintenance}")
    free = [snapshot.memory.free_percent for snapshot in snapshots if snapshot.memory.free_percent is not None]
    swap = [snapshot.memory.swap_used_mb for snapshot in snapshots if snapshot.memory.swap_used_mb is not None]
    if free:
        lines.append(f"  memory free: median {statistics.median(free):.0f}%, min {min(free)}%; swap used: median {statistics.median(swap):.0f} MB, max {max(swap):.0f} MB")
    resident = Counter(model for snapshot in snapshots for model in snapshot.memory.resident_models)
    if resident:
        lines.append("  resident model seen: " + ", ".join(f"{model} in {count} checks" for model, count in resident.most_common(3)))
    return lines


def pipeline_section(runs: list[PipelineRun]) -> list[str]:
    lines = [f"Home Assistant pipeline runs pulled: {len(runs)}"]
    if not runs:
        return lines
    stt = [run.stt_seconds for run in runs if run.stt_seconds is not None]
    agent = [run.agent_seconds for run in runs if run.agent_seconds is not None]
    tts = [run.tts_seconds for run in runs if run.tts_seconds is not None]
    lines.append(
        f"  speech to text after end of speech: median {fmt(statistics.median(stt) if stt else None)}; agent: median {fmt(statistics.median(agent) if agent else None)}; text to speech: median {fmt(statistics.median(tts) if tts else None)}"
    )
    errors = [run.error for run in runs if run.error]
    if errors:
        lines.append(f"  errors: {len(errors)}: " + "; ".join(sorted(set(errors))[:5]))
    return lines


def ollama_section(speeds: dict[str, list[float]]) -> list[str]:
    prompt, generation = speeds["prompt"], speeds["generation"]
    if not prompt and not generation:
        return ["Ollama speeds: no print_timing lines in ollama.log for this window"]
    return [
        f"Ollama speeds from ollama.log ({len(prompt)} requests): prompt reading median {fmt(statistics.median(prompt) if prompt else None, ' tok/s', 0)}, "
        f"generation median {fmt(statistics.median(generation) if generation else None, ' tok/s', 0)}, generation min {fmt(min(generation) if generation else None, ' tok/s', 0)}"
    ]


def render(log_dir: Path, days: int, today: date | None = None) -> str:
    today = today or datetime.now(UTC).date()
    since = today - timedelta(days=days - 1)
    header = [f"Operations report for {log_dir}  ({since} to {today}, {days} days)", ""]
    turns = load_turns(log_dir, since)
    body = (
        turns_section(turns)
        + [""]
        + health_section(load_snapshots(log_dir, since))
        + [""]
        + pipeline_section(load_pipeline_runs(log_dir, since))
        + [""]
        + ollama_section(ollama_speeds(log_dir, since))
    )
    return "\n".join(header + body)
