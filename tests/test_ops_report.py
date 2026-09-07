"""The operations report renders from fixture lines shaped exactly like what the mini writes."""

import json
from datetime import date
from pathlib import Path

from assistant_core.models import GenerationStats, Message, Role, RouteDecision, ToolCall, ToolExchange, Transcript
from assistant_core.turn_record import turn_record_from_transcript
from ops import report
from ops.pipeline_runs import summarize


def write_lines(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records))


def turn(day: str, text: str, seconds: float, route: str = "calculate", error: str | None = None) -> dict:
    call = ToolCall(id="c", name="percent", arguments={"a": 12, "b": 250, "kind": "of"})
    transcript = Transcript(
        model="gemma4:26b",
        system_prompt="",
        conversation=[Message(role=Role.USER, content=text), Message(role=Role.ASSISTANT, content="30")],
        tool_exchanges=[ToolExchange(round_index=0, call=call, result="30", seconds=0.5, error=error)],
        model_calls=[GenerationStats(model="gemma4:26b", prompt_tokens=1800, output_tokens=20, total_seconds=seconds / 2)],
        final_answer="It is 30.",
        total_seconds=seconds,
        time_to_first_spoken_seconds=seconds / 3,
        route=RouteDecision(route=route, source="rule"),
        tool_call_count=1,
    )
    record = turn_record_from_transcript(transcript)
    return json.loads(record.model_dump_json()) | {"recorded_at": f"{day}T12:00:00+00:00"}


def snapshot(stamp: str, mcp_ok: bool, actions: list[str] | None = None, maintenance: bool = False) -> dict:
    checks = {name: {"ok": True, "detail": "", "seconds": 0.1} for name in ("ollama", "mcp", "whisper", "kokoro", "searxng", "home_assistant", "vm")}
    checks["mcp"]["ok"] = mcp_ok
    return {
        "checked_at": stamp,
        "checks": checks,
        "memory": {"free_percent": 40, "swap_used_mb": 512.0, "resident_models": ["gemma4:26b"], "resident_model_mb": 17000.0},
        "maintenance": maintenance,
        "full": False,
        "actions": actions or [],
        "housekeeping": [],
    }


def pipeline_events() -> list[dict]:
    return [
        {"type": "run-start", "timestamp": "2026-09-07T12:00:00+00:00", "data": {}},
        {"type": "stt-start", "timestamp": "2026-09-07T12:00:00+00:00", "data": {"engine": "stt.mlx_whisper"}},
        {"type": "stt-vad-end", "timestamp": "2026-09-07T12:00:03+00:00", "data": {}},
        {"type": "stt-end", "timestamp": "2026-09-07T12:00:04+00:00", "data": {"stt_output": {"text": "what is twelve percent of 250"}}},
        {"type": "intent-start", "timestamp": "2026-09-07T12:00:04+00:00", "data": {}},
        {"type": "intent-end", "timestamp": "2026-09-07T12:00:09+00:00", "data": {"intent_output": {"response": {"speech": {"plain": {"speech": "It is 30."}}}}}},
        {"type": "tts-start", "timestamp": "2026-09-07T12:00:09+00:00", "data": {}},
        {"type": "tts-end", "timestamp": "2026-09-07T12:00:10+00:00", "data": {}},
        {"type": "run-end", "timestamp": "2026-09-07T12:00:10+00:00", "data": {}},
    ]


def fixture_dir(tmp_path: Path) -> Path:
    write_lines(
        tmp_path / "turns" / "2026-09-06.jsonl", [turn("2026-09-06", "What is 12 percent of 250?", 4.0), turn("2026-09-06", "Search the web for the Fed rate", 20.0, route="search", error="timeout")]
    )
    write_lines(tmp_path / "turns" / "2026-09-07.jsonl", [turn("2026-09-07", "Why does bread rise?", 3.0, route="answer")])
    write_lines(tmp_path / "turns" / "2026-06-01.jsonl", [turn("2026-06-01", "old", 99.0)])
    write_lines(
        tmp_path / "health.jsonl",
        [
            snapshot("2026-09-07T10:00:00+00:00", True),
            snapshot("2026-09-07T10:05:00+00:00", False),
            snapshot("2026-09-07T10:10:00+00:00", False, actions=["kickstart:mcp (mcp failed 2 checks in a row): ok"]),
            snapshot("2026-09-07T10:15:00+00:00", True),
            snapshot("2026-09-07T10:20:00+00:00", True, maintenance=True),
        ],
    )
    run = summarize("Jarvis", "run1", pipeline_events())
    write_lines(tmp_path / "pipeline_runs.jsonl", [json.loads(run.model_dump_json())])
    (tmp_path / "ollama.log").write_text(
        "time=2026-09-07T02:14:00.037-04:00 level=INFO msg=x\n"
        "slot print_timing: id  0 | task 0 | prompt eval time =     245.13 ms /    11 tokens (   22.28 ms per token,    44.87 tokens per second)\n"
        "slot print_timing: id  0 | task 0 |        eval time =    1000.00 ms /    25 tokens (   40.00 ms per token,    25.00 tokens per second)\n"
        "slot print_timing: id  0 | task 1 |        eval time =       0.00 ms /     1 tokens (    0.00 ms per token,     0.00 tokens per second)\n"
    )
    return tmp_path


def test_report_covers_turns_health_pipeline_and_ollama(tmp_path: Path) -> None:
    text = report.render(fixture_dir(tmp_path), days=7, today=date(2026, 9, 7))
    assert "Turns: 3" in text  # the June turn is outside the window
    assert "2026-09-06 2, 2026-09-07 1" in text
    assert "routes: calculate 1, search 1, answer 1" in text or "routes: " in text
    assert "percent 3 (1 failed)" in text
    assert "failure flags: none" in text
    assert "mcp down 09-07T10:05 -> 09-07T10:15" in text
    assert "actions taken by the machine: 1" in text and "kickstart:mcp" in text
    assert "checks skipped under the maintenance flag: 1" in text
    assert "resident model seen: gemma4:26b in 5 checks" in text
    assert "pipeline runs pulled: 1" in text and "speech to text after end of speech: median 1.0s" in text and "agent: median 5.0s" in text
    assert "prompt reading median 45 tok/s" in text and "generation median 25 tok/s" in text


def test_report_on_an_empty_directory_does_not_crash(tmp_path: Path) -> None:
    text = report.render(tmp_path, days=1, today=date(2026, 9, 7))
    assert "Turns: 0" in text and "Health checks: 0" in text and "no print_timing" in text


def test_pipeline_summary_reads_stage_timings_and_errors() -> None:
    events = pipeline_events() + [{"type": "error", "timestamp": "2026-09-07T12:00:10+00:00", "data": {"code": "stt-no-text-recognized", "message": "No text recognized"}}]
    run = summarize("Jarvis", "run2", events)
    assert run.stt_text == "what is twelve percent of 250"
    assert (run.stt_seconds, run.agent_seconds, run.tts_seconds, run.total_seconds) == (1.0, 5.0, 1.0, 10.0)
    assert run.agent_said == "It is 30."
    assert run.error == "stt-no-text-recognized: No text recognized"


def test_percentile_is_defined_on_small_samples() -> None:
    assert report.percentile([], 0.9) is None
    assert report.percentile([5.0], 0.9) == 5.0
    assert report.percentile([1.0, 2.0, 3.0, 10.0], 0.9) == 10.0
