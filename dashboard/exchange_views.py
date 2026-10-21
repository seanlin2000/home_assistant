"""What the dashboard's API returns: the exchanges of a day as one-line summaries, and one exchange in full, built from its record, its trace when
one is kept, and its Home Assistant pipeline run when one matches (design doc v2/13 sections 3.1 to 3.4)."""

from datetime import date, timedelta
from pathlib import Path

from pydantic import BaseModel, Field

from assistant_core.exchange_record import ExchangeRecord, ExchangeTrace, ToolCallSummary
from assistant_core.models import Message, Role, ToolCallRecord, Transcript
from assistant_service.exchange_log import ExchangeLog, TraceLog
from dashboard.evidence import ToolEvidence, tool_evidence
from dashboard.pipeline_match import matching_run
from dashboard.timeline import Timeline, build_timeline
from ops.pipeline_runs import PipelineRun, PipelineRunLog


class DaySummary(BaseModel):
    day: str
    exchanges: int


class ExchangeSummary(BaseModel):
    day: str
    index: int  # the line in the day's record file, which never changes because the file only grows
    recorded_at: str
    source: str
    model: str
    user_text: str
    final_answer: str
    total_seconds: float
    time_to_first_spoken_seconds: float | None
    route: str | None
    tools: list[str]
    failed: bool


class ToolCard(BaseModel):
    call_id: str
    name: str
    arguments: dict
    round_index: int
    seconds: float
    started_seconds: float | None = None
    result_chars: int
    error: str | None = None
    refused: bool = False
    repeated: bool = False
    result: str | None = None  # None when the exchange's trace is gone
    evidence: ToolEvidence | None = None


class Turn(BaseModel):
    """One model call that the conversation kept: what it thought, what it wrote beside its tool calls, and those calls."""

    thinking: str = ""
    text: str = ""
    tools: list[ToolCard]


class SpeechRun(BaseModel):
    heard: str | None
    agent_seconds: float | None
    stt_seconds: float | None
    tts_seconds: float | None
    error: str | None


class ExchangeDetail(BaseModel):
    summary: ExchangeSummary
    record: ExchangeRecord
    has_trace: bool
    system_prompt: str | None = None
    earlier_messages: list[Message]
    filler_text: str = ""
    turns: list[Turn]
    timeline: Timeline
    speech: SpeechRun | None = None
    earlier_exchanges: list[ExchangeSummary] = Field(default_factory=list)  # the exchanges before this one in its conversation, oldest first


class ExchangeStore:
    def __init__(self, records: ExchangeLog, traces: TraceLog, runs: PipelineRunLog) -> None:
        self._records = records
        self._traces = traces
        self._runs = runs

    def days(self) -> list[DaySummary]:
        """Every day with exchanges, newest first."""
        return [DaySummary(day=day.isoformat(), exchanges=line_count(path)) for day, path in reversed(self._records.day_files())]

    def latest(self) -> ExchangeSummary | None:
        """The newest exchange, whose model the page shows as the one the harness is running now."""
        day_files = self._records.day_files()
        if not day_files:
            return None
        day = day_files[-1][0]
        records = self._records.read_day(day)
        return summarize(day, len(records) - 1, records[-1]) if records else None

    def summaries(self, day: date) -> list[ExchangeSummary]:
        return [summarize(day, index, record) for index, record in enumerate(self._records.read_day(day))]

    def detail(self, day: date, index: int) -> ExchangeDetail | None:
        records = self._records.read_day(day)
        if not 0 <= index < len(records):
            return None
        record = records[index]
        trace = self.trace_for(record, day)
        run = matching_run(record, self.runs_around(day))
        earlier = self.earlier_in_conversation(day, records[:index], record)
        return detail_from(summarize(day, index, record), record, trace, run).model_copy(update={"earlier_exchanges": earlier})

    def earlier_in_conversation(self, day: date, earlier_that_day: list[ExchangeRecord], record: ExchangeRecord) -> list[ExchangeSummary]:
        """The exchanges that share this one's conversation id: earlier lines of its day, and the day before, since a conversation can cross midnight UTC."""
        if not record.conversation_id:
            return []
        previous_day = day - timedelta(days=1)
        days = [(previous_day, self._records.read_day(previous_day)), (day, earlier_that_day)]
        return [summarize(each_day, index, earlier) for each_day, records in days for index, earlier in enumerate(records) if earlier.conversation_id == record.conversation_id]

    def trace_for(self, record: ExchangeRecord, day: date) -> ExchangeTrace | None:
        """A trace is written right after its record, so it is in the same day's file, or the next one when the record was the last before midnight UTC."""
        if not record.exchange_id:
            return None
        candidates = self._traces.read_day(day) + self._traces.read_day(day + timedelta(days=1))
        return next((trace for trace in candidates if trace.exchange_id == record.exchange_id), None)

    def runs_around(self, day: date) -> list[PipelineRun]:
        """A run kept again once it finished replaces its earlier, partial copy."""
        latest_by_id = {run.run_id: run for offset in (-1, 0, 1) for run in self._runs.read_day(day + timedelta(days=offset))}
        return list(latest_by_id.values())


def line_count(path: Path) -> int:
    return sum(1 for line in path.read_text().splitlines() if line.strip())


def summarize(day: date, index: int, record: ExchangeRecord) -> ExchangeSummary:
    return ExchangeSummary(
        day=day.isoformat(),
        index=index,
        recorded_at=record.recorded_at,
        source=record.source,
        model=record.model,
        user_text=record.user_text,
        final_answer=record.final_answer,
        total_seconds=record.total_seconds,
        time_to_first_spoken_seconds=record.time_to_first_spoken_seconds,
        route=record.route.route if record.route else None,
        tools=[summary.name for summary in record.tool_calls],
        failed=record.failed,
    )


def detail_from(summary: ExchangeSummary, record: ExchangeRecord, trace: ExchangeTrace | None, run: PipelineRun | None) -> ExchangeDetail:
    timeline = build_timeline(record, run)
    speech = speech_run(run) if run else None
    if trace is None:
        return ExchangeDetail(summary=summary, record=record, has_trace=False, earlier_messages=[], turns=turns_from_record(record), timeline=timeline, speech=speech)
    transcript = trace.transcript
    question_index = last_question_index(transcript.conversation)
    return ExchangeDetail(
        summary=summary,
        record=record,
        has_trace=True,
        system_prompt=transcript.system_prompt,
        earlier_messages=transcript.conversation[:question_index],
        filler_text=transcript.filler_text,
        turns=turns_from_transcript(transcript, question_index, record),
        timeline=timeline,
        speech=speech,
    )


def speech_run(run: PipelineRun) -> SpeechRun:
    return SpeechRun(heard=run.stt_text, agent_seconds=run.agent_seconds, stt_seconds=run.stt_seconds, tts_seconds=run.tts_seconds, error=run.error)


def last_question_index(conversation: list[Message]) -> int:
    return max((index for index, message in enumerate(conversation) if message.role == Role.USER), default=0)


def turns_from_transcript(transcript: Transcript, question_index: int, record: ExchangeRecord) -> list[Turn]:
    """Each assistant message after the question is a turn, holding the tool calls it asked for; calls no kept message asked for go in a last turn."""
    cards = {tool_call.call.id: card_with_result(tool_call, record) for tool_call in transcript.tool_call_records}
    turns = []
    for message in transcript.conversation[question_index + 1 :]:
        if message.role == Role.ASSISTANT:
            turns.append(Turn(thinking=message.thinking, text=message.content if message.tool_calls else "", tools=[cards.pop(call.id) for call in message.tool_calls if call.id in cards]))
    if cards:
        turns.append(Turn(tools=list(cards.values())))
    return turns


def card_with_result(tool_call: ToolCallRecord, record: ExchangeRecord) -> ToolCard:
    return ToolCard(
        call_id=tool_call.call.id,
        name=tool_call.call.name,
        arguments=tool_call.call.arguments,
        round_index=tool_call.round_index,
        seconds=tool_call.seconds,
        started_seconds=tool_call.started_seconds,
        result_chars=len(tool_call.result),
        error=tool_call.error,
        refused=tool_call.refused,
        repeated=tool_call.repeated,
        result=tool_call.result,
        evidence=tool_evidence(tool_call.result, record.final_answer, record.user_text),
    )


def turns_from_record(record: ExchangeRecord) -> list[Turn]:
    rounds = sorted({summary.round_index for summary in record.tool_calls})
    return [Turn(tools=[card_without_result(summary) for summary in record.tool_calls if summary.round_index == round_index]) for round_index in rounds]


def card_without_result(summary: ToolCallSummary) -> ToolCard:
    return ToolCard(
        call_id="",
        name=summary.name,
        arguments=summary.arguments,
        round_index=summary.round_index,
        seconds=summary.seconds,
        started_seconds=summary.started_seconds,
        result_chars=summary.result_chars,
        error=summary.error,
        refused=summary.refused,
    )
