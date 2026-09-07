"""One health check of the assistant's Mac: probe every service, record a snapshot, and heal what the policy allows (design doc 10 §3.5).

launchd runs this every five minutes (scripts/services.sh installs the agent). Run it by hand to see the machine's state:

    uv run python scripts/health_check.py                  # probe, record, act
    uv run python scripts/health_check.py --dry-run        # probe and say what it would do; writes nothing
    uv run python scripts/health_check.py --no-remediate   # probe and record, take no action
    uv run python scripts/health_check.py --full           # also run a real SearXNG query (hits upstream engines)
    uv run python scripts/health_check.py --json           # the snapshot as JSON
"""

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from ops import health  # noqa: E402


def main() -> int:
    load_dotenv(PROJECT / ".env")
    parser = argparse.ArgumentParser(description="Probe the assistant's services, record a health snapshot, and self-heal per policy.")
    parser.add_argument("--json", action="store_true", help="print the snapshot as JSON instead of a table")
    parser.add_argument("--no-remediate", action="store_true", help="record only; never restart anything")
    parser.add_argument("--dry-run", action="store_true", help="print what would happen; write nothing")
    parser.add_argument("--full", action="store_true", help="run the SearXNG query probe too")
    parser.add_argument("--last", action="store_true", help="print the last recorded snapshot in one line and exit")
    args = parser.parse_args()
    if args.last:
        return print_last()
    snapshot = asyncio.run(health.run_once(health.settings_from_environment(), remediate=not args.no_remediate, dry_run=args.dry_run, full=args.full))
    print(snapshot.model_dump_json(indent=1) if args.json else health.render(snapshot))
    return 1 if snapshot.failing else 0


def print_last() -> int:
    from ops import paths

    if not paths.health_json().exists():
        print("no health snapshot yet")
        return 0
    snapshot = health.Snapshot.model_validate_json(paths.health_json().read_text())
    summary = "all ok" if not snapshot.failing else "FAILING " + ", ".join(snapshot.failing)
    actions = f"; actions: {'; '.join(snapshot.actions)}" if snapshot.actions else ""
    print(f"last health snapshot {snapshot.checked_at}: {summary}{actions}")
    return 1 if snapshot.failing else 0


if __name__ == "__main__":
    sys.exit(main())
