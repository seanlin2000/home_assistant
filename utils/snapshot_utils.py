"""Listings snapshots on disk: the nightly refresh writes one JSON file per source family, and the tools only ever read it.

The file is written beside its final name and then renamed over it, so a tool reading while the refresh runs sees the old snapshot or the new one,
never half of either.
"""

import os
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from utils.text_utils import spoken_month_day

DEFAULT_LISTINGS_DIR = Path.home() / "Library" / "Caches" / "studio-assistant" / "listings"
Snapshot = TypeVar("Snapshot", bound=BaseModel)


class DatedSnapshot(BaseModel):
    refreshed_at: datetime


Listing = TypeVar("Listing", bound=DatedSnapshot)


class ListingsSettings(Protocol):
    snapshot_path: Path
    stale_after_days: int  # older than this, an answer says how old its listings are
    today: date | None  # the day the benchmark's snapshot was taken; set only by the benchmark


class ListingsUnavailable(RuntimeError):
    """A listings source could not be read, or answered in a shape the refresh does not know; the last snapshot stays."""


class SnapshotMissing(RuntimeError):
    """No snapshot has been written yet, or the file no longer reads as the snapshot it should be."""


def write_snapshot(path: Path, snapshot: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = path.with_name(f".{path.name}.partial")
    partial_path.write_text(snapshot.model_dump_json(), encoding="utf-8")
    os.replace(partial_path, path)


def read_snapshot(path: Path, shape: type[Snapshot]) -> Snapshot:
    try:
        return shape.model_validate_json(path.read_bytes())
    except FileNotFoundError as error:
        raise SnapshotMissing(f"{path} has not been written yet") from error
    except ValidationError as error:
        raise SnapshotMissing(f"{path} does not read as a {shape.__name__} ({error.error_count()} problems)") from error


def listing_today(settings: ListingsSettings) -> date:
    """The user's local date, unless the benchmark pins it to the day its snapshot was taken."""
    return settings.today or date.today()


def answered_from_snapshot(settings: ListingsSettings, shape: type[Listing], answer: Callable[[Listing, date], str]) -> str:
    """A listings tool's answer from its snapshot, then a note when the nightly refresh has not run for days, which no word budget cuts. Raises
    SnapshotMissing when there is no snapshot to answer from."""
    snapshot = read_snapshot(settings.snapshot_path, shape)
    today = listing_today(settings)
    text = answer(snapshot, today)
    stale_note = age_note(snapshot.refreshed_at, today, settings.stale_after_days)
    return f"{text}\n{stale_note}" if stale_note else text


def age_note(refreshed_at: datetime, today: date, stale_after_days: int) -> str:
    refreshed_on = refreshed_at.astimezone().date()
    days_old = (today - refreshed_on).days
    if days_old <= stale_after_days:
        return ""
    return f"These listings were last refreshed {days_old} days ago, on {spoken_month_day(refreshed_on, today)}; tell the user they may be out of date."
