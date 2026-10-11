"""Find the Home Assistant pipeline run behind an exchange, which holds its speech timings (design doc v2/13 section 3.3).

Home Assistant keeps one conversation id across the turns of a conversation, so the id alone does not pick out one exchange; a run counts when its
id or the text it handed the agent matches, it started within two minutes of the exchange, and among those the run matching on both, then the
closest in time, wins.
"""

from datetime import datetime, timedelta

from assistant_core.exchange_record import ExchangeRecord
from ops.pipeline_runs import PipelineRun

MATCH_WINDOW_SECONDS = 120


def matching_run(record: ExchangeRecord, runs: list[PipelineRun]) -> PipelineRun | None:
    exchange_started = datetime.fromisoformat(record.recorded_at) - timedelta(seconds=record.total_seconds)
    candidates = [run for run in runs if run.intent_started_at and (same_conversation(run, record) or same_question(run, record))]
    in_window = [run for run in candidates if seconds_apart(run, exchange_started) <= MATCH_WINDOW_SECONDS]
    return min(in_window, key=lambda run: (-(same_conversation(run, record) + same_question(run, record)), seconds_apart(run, exchange_started)), default=None)


def same_conversation(run: PipelineRun, record: ExchangeRecord) -> bool:
    return bool(record.conversation_id) and run.conversation_id == record.conversation_id


def same_question(run: PipelineRun, record: ExchangeRecord) -> bool:
    return bool(run.intent_input) and run.intent_input.strip().casefold() == record.user_text.strip().casefold()


def seconds_apart(run: PipelineRun, exchange_started: datetime) -> float:
    return abs((datetime.fromisoformat(run.intent_started_at) - exchange_started).total_seconds())
