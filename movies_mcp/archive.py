"""A dated copy of each night's movie listings, kept two weeks. The snapshot itself is replaced every night, so without these nothing could say which
movies are new since last week.

Each copy is named for the first day its listings cover (movies-2026-11-21.json), which is the day the refresh ran.
"""

import re
from datetime import date, timedelta
from pathlib import Path

from pydantic import BaseModel

from movies_mcp.movies import MoviesSnapshot
from movies_mcp.settings import MoviesSettings
from utils.snapshot_utils import read_snapshot, write_snapshot

ARCHIVE_NAME = re.compile(r"movies-(\d{4}-\d{2}-\d{2})\.json")


class ArchivedSnapshot(BaseModel):
    day: date  # the first day the copy's listings cover
    snapshot: MoviesSnapshot


def archive_snapshot(settings: MoviesSettings, snapshot: MoviesSnapshot) -> None:
    """Writes tonight's copy, then deletes the copies older than archive_days."""
    directory = settings.archive_directory
    write_snapshot(directory / f"movies-{snapshot.first_day.isoformat()}.json", snapshot)
    oldest_kept = snapshot.first_day - timedelta(days=settings.archive_days - 1)
    for day, path in archived_copies(directory).items():
        if day < oldest_kept:
            path.unlink(missing_ok=True)


def snapshot_from_before(settings: MoviesSettings, day: date) -> ArchivedSnapshot | None:
    """The newest copy from that day or before. In the first week there is none that old, so the oldest copy stands in; the caller says which day it
    compares with, and may find it is today's. None when no copy has been written. Raises SnapshotMissing when the chosen copy does not read."""
    copies = archived_copies(settings.archive_directory)
    if not copies:
        return None
    old_enough = [copy_day for copy_day in copies if copy_day <= day]
    chosen = max(old_enough) if old_enough else min(copies)
    return ArchivedSnapshot(day=chosen, snapshot=read_snapshot(copies[chosen], MoviesSnapshot))


def archived_copies(directory: Path) -> dict[date, Path]:
    if not directory.is_dir():
        return {}
    named = {path: ARCHIVE_NAME.fullmatch(path.name) for path in directory.iterdir()}
    return {date.fromisoformat(match.group(1)): path for path, match in named.items() if match}
