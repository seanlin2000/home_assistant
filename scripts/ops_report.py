"""Print the operations report from a mirrored log directory (design doc 10 §3.7).

uv run python scripts/ops_report.py --days 7 logs/mini            # after scripts/mini.sh logs
uv run python scripts/ops_report.py --days 1 ~/Library/Logs/studio-assistant   # this machine's own logs
"""

import argparse
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from ops.report import render  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarise turn records, health history, pipeline runs, and Ollama speeds.")
    parser.add_argument("log_dir", type=Path, nargs="?", default=PROJECT / "logs" / "mini")
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    if not args.log_dir.exists():
        print(f"{args.log_dir} does not exist; run scripts/mini.sh logs first", file=sys.stderr)
        return 1
    print(render(args.log_dir, args.days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
