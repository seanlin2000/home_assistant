"""Append-only JSON Lines stores with one file per UTC day, pruned after a retention period. The harness keeps its exchange records and traces this
way, and the dashboard its Home Assistant pipeline runs (design doc 10 §3.4, v2/13 section 3.1)."""

import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel

from utils.jsonl_utils import append_jsonl, read_jsonl

DAY_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.jsonl$")
RecordT = TypeVar("RecordT", bound=BaseModel)


class DailyLog(Generic[RecordT]):
    def __init__(self, directory: Path, record_type: type[RecordT], retention_days: int) -> None:
        self._directory = directory
        self._record_type = record_type
        self._retention_days = retention_days

    @property
    def directory(self) -> Path:
        return self._directory

    def path_for(self, day: date) -> Path:
        return self._directory / f"{day.isoformat()}.jsonl"

    def append(self, record: RecordT) -> Path:
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

    def read_day(self, day: date) -> list[RecordT]:
        return read_jsonl(self.path_for(day), self._record_type)

    def read_since(self, since: date) -> list[RecordT]:
        records: list[RecordT] = []
        for day, path in self.day_files():
            if day >= since:
                records.extend(read_jsonl(path, self._record_type))
        return records

    def prune(self, retention_days: int | None = None, today: date | None = None) -> list[Path]:
        """Delete day files older than the retention period and return what was deleted."""
        kept_days = self._retention_days if retention_days is None else retention_days
        cutoff = (today or datetime.now(UTC).date()) - timedelta(days=kept_days)
        deleted = []
        for day, path in self.day_files():
            if day < cutoff:
                path.unlink()
                deleted.append(path)
        return deleted
