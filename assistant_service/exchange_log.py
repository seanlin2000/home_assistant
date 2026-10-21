"""The harness's two day-file logs on the Mac's disk: the trimmed exchange record, kept 90 days (design doc 10 §3.4, §3.6), and the full trace of
the same exchange with every tool result, kept 14 days for the exchange dashboard (design doc v2/13 section 3.1)."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

from assistant_core.converse_protocol import ConverseRequest
from assistant_core.exchange_record import ExchangeRecord, ExchangeTrace, exchange_record_from_transcript
from assistant_core.models import Transcript
from utils.daily_log_utils import DailyLog

DEFAULT_RETENTION_DAYS = 90
TRACE_RETENTION_DAYS = 14


class ExchangeLog(DailyLog[ExchangeRecord]):
    def __init__(self, directory: Path) -> None:
        super().__init__(directory, ExchangeRecord, DEFAULT_RETENTION_DAYS)


class TraceLog(DailyLog[ExchangeTrace]):
    def __init__(self, directory: Path) -> None:
        super().__init__(directory, ExchangeTrace, TRACE_RETENTION_DAYS)


class ExchangeArchive:
    """Keeps each finished exchange in both logs under one id, so the dashboard can find the trace behind a record."""

    def __init__(self, records: ExchangeLog, traces: TraceLog) -> None:
        self.records = records
        self.traces = traces

    def keep(self, request: ConverseRequest, transcript: Transcript) -> ExchangeRecord:
        identity = {"exchange_id": uuid.uuid4().hex[:12], "conversation_id": request.conversation_id}
        record = exchange_record_from_transcript(transcript, source=request.source, recorded_at=datetime.now(UTC)).model_copy(update=identity)
        self.records.append(record)
        self.traces.append(ExchangeTrace(recorded_at=record.recorded_at, source=request.source, transcript=transcript, **identity))
        return record
