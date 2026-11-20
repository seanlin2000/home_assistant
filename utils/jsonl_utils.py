"""Read and write JSON Lines files of pydantic records: one record per line, appended in place, so a file can grow forever and be tailed."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel


def write_jsonl(path: Path, records: list[BaseModel]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for record in records:
            handle.write(record.model_dump_json() + "\n")


def append_jsonl(path: Path, record: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(record.model_dump_json() + "\n")


def read_jsonl(path: Path, record_type: type[BaseModel]) -> list[Any]:
    if not path.exists():
        return []
    return [record_type.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()]
