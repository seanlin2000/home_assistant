"""One-time move of the exchange logs out of turns/, the folder they were written to before "turn" was renamed "exchange", into exchanges/.

services.sh runs it on the mini while the tool server is stopped, and scripts/mini.sh runs it on the laptop's mirror before pulling new logs.
Running it again changes nothing. Each file moves only when exchanges/ has no file of that name, and the old record field history_turns is
renamed history_messages on the way. A file that exchanges/ already holds with the same migrated content is a duplicate and is deleted; one
with different content stays in turns/, and so does turns/ itself, so nothing is ever overwritten or lost.

    python -m ops.legacy_exchange_logs [LOG_DIR]      # default: this machine's log directory
"""

import argparse
import os
from pathlib import Path

from ops import paths

LEGACY_FOLDER = "turns"
LEGACY_FIELD = b'"history_turns":'
CURRENT_FIELD = b'"history_messages":'


def move_legacy_exchange_logs(log_dir: Path) -> list[Path]:
    """Move what can be moved and return the files left behind in turns/ (an empty list when turns/ is gone or never existed)."""
    legacy_dir = log_dir / LEGACY_FOLDER
    if not legacy_dir.is_dir():
        return []
    target_dir = log_dir / paths.EXCHANGES_FOLDER
    target_dir.mkdir(parents=True, exist_ok=True)
    left_behind = [source for source in sorted(legacy_dir.iterdir()) if not move_file(source, target_dir / source.name)]
    if not left_behind:
        legacy_dir.rmdir()
    return left_behind


def move_file(source: Path, destination: Path) -> bool:
    """True when `source` is gone afterwards: moved to `destination`, or deleted as a duplicate of it."""
    if not source.is_file() or source.is_symlink():
        return False
    migrated = source.read_bytes().replace(LEGACY_FIELD, CURRENT_FIELD)
    if destination.exists():
        if destination.read_bytes() != migrated:
            return False
    else:
        write_atomically(destination, migrated)
    source.unlink()
    return True


def write_atomically(destination: Path, content: bytes) -> None:
    staging = destination.with_name(f".{destination.name}.moving")
    staging.write_bytes(content)
    os.replace(staging, destination)


def describe(log_dir: Path, left_behind: list[Path]) -> str:
    if not left_behind:
        return f"{log_dir}: moved {LEGACY_FOLDER}/ into {paths.EXCHANGES_FOLDER}/"
    names = ", ".join(path.name for path in left_behind)
    return f"{log_dir / LEGACY_FOLDER}: left {len(left_behind)} files that differ from their namesakes in {paths.EXCHANGES_FOLDER}/: {names}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Move exchange logs from the old turns/ folder into exchanges/.")
    parser.add_argument("log_dir", type=Path, nargs="?", default=None, help="log directory holding turns/ (default: this machine's)")
    log_dir = parser.parse_args().log_dir or paths.log_dir()
    if (log_dir / LEGACY_FOLDER).is_dir():
        print(describe(log_dir, move_legacy_exchange_logs(log_dir)))


if __name__ == "__main__":
    main()
