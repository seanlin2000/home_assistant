"""Append-only store of TurnRecords on the Mac's disk, one JSON Lines file per day, pruned after a retention period (design doc 10 §3.4, §3.6)."""

import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from assistant_core.turn_record import TurnRecord
from utils.jsonl_utils import append_jsonl, read_jsonl

DAY_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.jsonl$")
DEFAULT_RETENTION_DAYS = 90


class TurnLog:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    @property
    def directory(self) -> Path:
        return self._directory

    def path_for(self, day: date) -> Path:
        return self._directory / f"{day.isoformat()}.jsonl"

    def append(self, record: TurnRecord) -> Path:
        path = self.path_for(datetime.now(UTC).date())
        append_jsonl(path, record)
        return path

    def day_files(self) -> list[tuple[date, Path]]:
        """Every day file that exists, oldest first. Files that do not match the day pattern are left alone."""
        found = []
        if not self._directory.exists():
            return found
        for path in self._directory.iterdir():
            match = DAY_FILE.match(path.name)
            if match:
                found.append((date.fromisoformat(match.group(1)), path))
        return sorted(found)

    def read_since(self, since: date) -> list[TurnRecord]:
        records: list[TurnRecord] = []
        for day, path in self.day_files():
            if day >= since:
                records.extend(read_jsonl(path, TurnRecord))
        return records

    def prune(self, retention_days: int = DEFAULT_RETENTION_DAYS, today: date | None = None) -> list[Path]:
        """Delete day files older than the retention period and return what was deleted."""
        cutoff = (today or datetime.now(UTC).date()) - timedelta(days=retention_days)
        deleted = []
        for day, path in self.day_files():
            if day < cutoff:
                path.unlink()
                deleted.append(path)
        return deleted
