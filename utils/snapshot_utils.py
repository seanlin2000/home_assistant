"""Listings snapshots on disk: the nightly refresh writes one JSON file per source family, and the tools only ever read it.

The file is written beside its final name and then renamed over it, so a tool reading while the refresh runs sees the old snapshot or the new one,
never half of either.
"""

import os
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

DEFAULT_LISTINGS_DIR = Path.home() / "Library" / "Caches" / "studio-assistant" / "listings"
Snapshot = TypeVar("Snapshot", bound=BaseModel)


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
