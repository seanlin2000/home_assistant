"""The dated copies of the movie listings: how long they are kept, and which one stands for last week, including in the first week, when no copy is
that old. The listings are the benchmark's own (benchmark/fixtures/movies/movies.json, from 2026-10-25), re-dated for each copy."""

from datetime import date, timedelta
from pathlib import Path

from benchmark.mcp_process import MOVIES_RECORDED_ON, MOVIES_SNAPSHOT_PATH
from movies_mcp.archive import archive_snapshot, archived_copies, snapshot_from_before
from movies_mcp.movies import MoviesSnapshot
from movies_mcp.settings import MoviesSettings
from utils.snapshot_utils import read_snapshot

RECORDED_ON = date.fromisoformat(MOVIES_RECORDED_ON)
RECORDED = read_snapshot(MOVIES_SNAPSHOT_PATH, MoviesSnapshot)


def settings_in(tmp_path: Path) -> MoviesSettings:
    return MoviesSettings(snapshot_path=tmp_path / "movies.json")


def snapshot_for(day: date) -> MoviesSnapshot:
    return RECORDED.model_copy(update={"first_day": day})


def archive_nights(settings: MoviesSettings, days: list[date]) -> None:
    for day in days:
        archive_snapshot(settings, snapshot_for(day))


def test_copies_sit_beside_the_snapshot_unless_a_folder_is_set(tmp_path: Path) -> None:
    assert settings_in(tmp_path).archive_directory == tmp_path / "movies_archive"
    assert settings_in(tmp_path).model_copy(update={"archive_dir": tmp_path / "elsewhere"}).archive_directory == tmp_path / "elsewhere"


def test_two_weeks_of_copies_are_kept_and_older_ones_deleted(tmp_path: Path) -> None:
    settings = settings_in(tmp_path)
    archive_nights(settings, [RECORDED_ON - timedelta(days=offset) for offset in range(20, -1, -1)])
    kept = sorted(archived_copies(settings.archive_directory))
    assert kept == [RECORDED_ON - timedelta(days=offset) for offset in range(13, -1, -1)]


def test_last_week_is_the_newest_copy_from_that_day_or_before(tmp_path: Path) -> None:
    settings = settings_in(tmp_path)
    week_ago = RECORDED_ON - timedelta(days=7)
    archive_nights(settings, [week_ago - timedelta(days=2), week_ago - timedelta(days=1), week_ago + timedelta(days=1), RECORDED_ON])  # the night a week ago failed
    archived = snapshot_from_before(settings, week_ago)
    assert archived is not None
    assert archived.day == week_ago - timedelta(days=1)
    assert archived.snapshot == snapshot_for(week_ago - timedelta(days=1))


def test_in_the_first_week_the_oldest_copy_stands_in_and_with_none_there_is_nothing(tmp_path: Path) -> None:
    settings = settings_in(tmp_path)
    assert snapshot_from_before(settings, RECORDED_ON - timedelta(days=7)) is None
    archive_nights(settings, [RECORDED_ON - timedelta(days=2), RECORDED_ON])
    archived = snapshot_from_before(settings, RECORDED_ON - timedelta(days=7))
    assert archived is not None and archived.day == RECORDED_ON - timedelta(days=2)


def test_files_that_are_not_dated_copies_are_ignored_and_kept(tmp_path: Path) -> None:
    settings = settings_in(tmp_path)
    settings.archive_directory.mkdir()
    stray = settings.archive_directory / "notes.txt"
    stray.write_text("")
    archive_nights(settings, [RECORDED_ON])
    assert list(archived_copies(settings.archive_directory)) == [RECORDED_ON]
    assert stray.exists()
