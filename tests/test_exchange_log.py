"""The harness's day-file store of exchange records."""

from datetime import date, timedelta
from pathlib import Path

from assistant_core.exchange_record import exchange_record_from_transcript
from assistant_core.models import GenerationStats, Message, Role, Transcript
from assistant_service.exchange_log import ExchangeLog


def sample_record():
    transcript = Transcript(
        model="gemma4:26b",
        system_prompt="You are Jarvis.",
        conversation=[Message(role=Role.USER, content="What is 12 percent of 250?"), Message(role=Role.ASSISTANT, content="It is 30.")],
        model_calls=[GenerationStats(model="gemma4:26b", prompt_tokens=100, output_tokens=10, total_seconds=1.2)],
        final_answer="It is 30.",
        total_seconds=1.5,
    )
    return exchange_record_from_transcript(transcript)


def test_append_writes_one_line_per_record_in_the_day_file(tmp_path: Path) -> None:
    log = ExchangeLog(tmp_path)
    path = log.append(sample_record())
    log.append(sample_record())
    assert len(path.read_text().splitlines()) == 2


def test_exchange_log_prunes_only_old_day_files(tmp_path: Path):
    log = ExchangeLog(tmp_path)
    today = date(2026, 9, 7)
    for days_ago in (0, 89, 90, 91, 400):
        log.path_for(today - timedelta(days=days_ago)).write_text("{}\n")
    (tmp_path / "notes.txt").write_text("keep me")
    deleted = log.prune(retention_days=90, today=today)
    assert sorted(path.name for path in deleted) == ["2025-08-03.jsonl", "2026-06-08.jsonl"]
    remaining = sorted(path.name for path in tmp_path.iterdir())
    assert remaining == ["2026-06-09.jsonl", "2026-06-10.jsonl", "2026-09-07.jsonl", "notes.txt"]


def test_exchange_log_read_since_returns_records_in_day_order(tmp_path: Path):
    log = ExchangeLog(tmp_path)
    record = sample_record()
    for day in (date(2026, 9, 1), date(2026, 9, 5)):
        log.path_for(day).write_text(record.model_dump_json() + "\n")
    assert len(log.read_since(date(2026, 9, 1))) == 2
    assert len(log.read_since(date(2026, 9, 2))) == 1
