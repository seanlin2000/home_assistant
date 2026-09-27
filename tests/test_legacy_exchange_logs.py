"""The one-time move of exchange logs from turns/ to exchanges/, on the mini and on the laptop's mirror: nothing is overwritten, nothing is lost, and a
second run changes nothing."""

from datetime import date
from pathlib import Path

from assistant_core.exchange_record import ExchangeRecord
from ops import report
from ops.legacy_exchange_logs import move_legacy_exchange_logs


def current_line(user_text: str) -> str:
    """One day-file line exactly as the tool server writes it."""
    record = ExchangeRecord(recorded_at="2026-09-07T12:00:00+00:00", source="home_assistant", model="m", user_text=user_text, history_messages=0, final_answer="It is 30.", spoken_chars=9)
    return record.model_dump_json() + "\n"


def legacy_line(user_text: str) -> str:
    """The same line as it was written before the rename, when the history field was called history_turns."""
    return current_line(user_text).replace('"history_messages":', '"history_turns":')


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_no_legacy_folder_is_a_no_op(tmp_path: Path) -> None:
    assert move_legacy_exchange_logs(tmp_path) == []
    assert list(tmp_path.iterdir()) == []


def test_legacy_folder_moves_whole_and_the_old_field_is_renamed(tmp_path: Path) -> None:
    write(tmp_path / "turns" / "2026-09-06.jsonl", legacy_line("What is 12 percent of 250?"))
    write(tmp_path / "turns" / "2026-09-07.jsonl", legacy_line("Why does bread rise?") + legacy_line("And sourdough?"))
    assert move_legacy_exchange_logs(tmp_path) == []
    assert not (tmp_path / "turns").exists()
    moved = (tmp_path / "exchanges" / "2026-09-07.jsonl").read_text()
    assert '"history_messages":0' in moved and "history_turns" not in moved
    assert sorted(path.name for path in (tmp_path / "exchanges").iterdir()) == ["2026-09-06.jsonl", "2026-09-07.jsonl"]


def test_both_folders_merge_without_overwriting(tmp_path: Path) -> None:
    write(tmp_path / "turns" / "2026-06-01.jsonl", legacy_line("only in the old folder"))
    write(tmp_path / "turns" / "2026-09-06.jsonl", legacy_line("in both, same records"))
    write(tmp_path / "turns" / "2026-09-07.jsonl", legacy_line("in both, older copy"))
    write(tmp_path / "exchanges" / "2026-09-06.jsonl", current_line("in both, same records"))
    newer = current_line("in both, older copy") + current_line("written later")
    write(tmp_path / "exchanges" / "2026-09-07.jsonl", newer)
    left_behind = move_legacy_exchange_logs(tmp_path)
    assert left_behind == [tmp_path / "turns" / "2026-09-07.jsonl"]
    assert (tmp_path / "exchanges" / "2026-09-07.jsonl").read_text() == newer
    assert "only in the old folder" in (tmp_path / "exchanges" / "2026-06-01.jsonl").read_text()
    assert sorted(path.name for path in (tmp_path / "turns").iterdir()) == ["2026-09-07.jsonl"]


def test_a_second_run_changes_nothing(tmp_path: Path) -> None:
    write(tmp_path / "turns" / "2026-09-07.jsonl", legacy_line("Why does bread rise?"))
    move_legacy_exchange_logs(tmp_path)
    before = {path.name: path.read_bytes() for path in (tmp_path / "exchanges").iterdir()}
    assert move_legacy_exchange_logs(tmp_path) == []
    assert {path.name: path.read_bytes() for path in (tmp_path / "exchanges").iterdir()} == before


def test_the_report_reads_a_moved_mirror(tmp_path: Path) -> None:
    write(tmp_path / "turns" / "2026-09-07.jsonl", legacy_line("Why does bread rise?") + legacy_line("And sourdough?"))
    move_legacy_exchange_logs(tmp_path)
    assert "Exchanges: 2" in report.render(tmp_path, days=1, today=date(2026, 9, 7))
