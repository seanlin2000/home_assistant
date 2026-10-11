"""Place every step of an exchange on one time axis for the dashboard's timing chart (design doc v2/13 sections 3.2, 3.3 and 3.5).

Zero is the moment the agent got the question. Speech to text happened before it, so its bar sits left of zero; text to speech after. Records written
before the agent loop stamped its steps have no start offsets, so their steps are laid end to end in the order they ran and marked approximate.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from assistant_core.exchange_record import ExchangeRecord, ToolCallSummary
from assistant_core.models import GenerationStats, RouteDecision
from ops.pipeline_runs import PipelineRun

LONGEST_ARGUMENT_CHARS = 40


class Lane(StrEnum):
    SPEECH = "speech"
    ROUTER = "router"
    MODEL = "model"
    TOOL = "tool"


class Bar(BaseModel):
    lane: Lane
    label: str
    start: float
    seconds: float
    load_seconds: float | None = None
    read_seconds: float | None = None
    write_seconds: float | None = None
    detail: str = ""
    failed: bool = False


class Timeline(BaseModel):
    bars: list[Bar]
    approximate: bool
    first_spoken_seconds: float | None = None
    total_seconds: float


def build_timeline(record: ExchangeRecord, run: PipelineRun | None) -> Timeline:
    stamped = steps_are_stamped(record)
    agent_bars = stamped_bars(record) if stamped else sequential_bars(record)
    speech_bars = pipeline_bars(run) if run else []
    before, after = [bar for bar in speech_bars if bar.start < 0], [bar for bar in speech_bars if bar.start >= 0]
    return Timeline(bars=before + agent_bars + after, approximate=not stamped, first_spoken_seconds=record.time_to_first_spoken_seconds, total_seconds=record.total_seconds)


def steps_are_stamped(record: ExchangeRecord) -> bool:
    steps = [*record.model_calls, *record.tool_calls] + ([record.route] if record.route else [])
    return all(step.started_seconds is not None for step in steps)


def stamped_bars(record: ExchangeRecord) -> list[Bar]:
    bars = [route_bar(record.route, record.route.started_seconds)] if record.route else []
    bars += [model_bar(index, stats, stats.started_seconds) for index, stats in enumerate(record.model_calls)]
    bars += [tool_bar(summary, summary.started_seconds) for summary in record.tool_calls]
    return sorted(bars, key=lambda bar: bar.start)


def sequential_bars(record: ExchangeRecord) -> list[Bar]:
    """Route first, then each model call followed by the tools of its round, which ran together."""
    bars = [route_bar(record.route, 0.0)] if record.route else []
    cursor = record.route.seconds if record.route else 0.0
    for index, stats in enumerate(record.model_calls):
        bars.append(model_bar(index, stats, cursor))
        cursor += stats.total_seconds
        round_tools = [tool_bar(summary, cursor) for summary in record.tool_calls if summary.round_index == index]
        bars.extend(round_tools)
        cursor += max((bar.seconds for bar in round_tools), default=0.0)
    return bars


def route_bar(route: RouteDecision, start: float) -> Bar:
    return Bar(lane=Lane.ROUTER, label=f"router → {route.route}", start=start, seconds=route.seconds, detail=f"{route.source}: {route.detail}".strip(": "))


def model_bar(index: int, stats: GenerationStats, start: float) -> Bar:
    return Bar(
        lane=Lane.MODEL,
        label=f"model #{index + 1}",
        start=start,
        seconds=stats.total_seconds,
        load_seconds=stats.load_seconds,
        read_seconds=stats.prompt_eval_seconds,
        write_seconds=stats.generation_seconds,
        detail=token_counts(stats),
    )


def token_counts(stats: GenerationStats) -> str:
    parts = [f"{stats.prompt_tokens} prompt tokens" if stats.prompt_tokens is not None else ""]
    parts.append(f"{stats.cached_prompt_tokens} cached" if stats.cached_prompt_tokens else "")
    parts.append(f"{stats.output_tokens} written" if stats.output_tokens is not None else "")
    parts.append(f"stopped: {stats.stop_reason}" if stats.stop_reason else "")
    return ", ".join(part for part in parts if part)


def tool_bar(summary: ToolCallSummary, start: float) -> Bar:
    return Bar(lane=Lane.TOOL, label=f"{summary.name} {short_arguments(summary.arguments)}".strip(), start=start, seconds=summary.seconds, failed=bool(summary.error))


def short_arguments(arguments: dict) -> str:
    joined = ", ".join(str(value) for value in arguments.values())
    return joined if len(joined) <= LONGEST_ARGUMENT_CHARS else joined[: LONGEST_ARGUMENT_CHARS - 1] + "…"


def pipeline_bars(run: PipelineRun) -> list[Bar]:
    """Speech to text runs from the end of speech to the transcript, text to speech from its start to its end, both measured from the agent's start."""
    times = {event["type"]: datetime.fromisoformat(event["timestamp"]) for event in run.raw_events}
    origin = times.get("intent-start")
    if origin is None:
        return []
    bars = []
    speech_end = times.get("stt-vad-end") or times.get("stt-start")
    if speech_end and "stt-end" in times:
        bars.append(speech_bar("speech → text", speech_end, times["stt-end"], origin))
    if "tts-start" in times and "tts-end" in times:
        bars.append(speech_bar("text → speech", times["tts-start"], times["tts-end"], origin))
    return bars


def speech_bar(label: str, started: datetime, ended: datetime, origin: datetime) -> Bar:
    return Bar(lane=Lane.SPEECH, label=label, start=(started - origin).total_seconds(), seconds=(ended - started).total_seconds())
