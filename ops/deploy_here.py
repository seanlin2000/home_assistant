"""A whole deploy on the Mac that serves, run at its keyboard by scripts/deploy.sh (design doc v2/10 section 3.11).

The protocol scripts/mini.sh drives from the laptop, run where the services are: `ops.deploy` checks out the commit, tests it and restarts what
changed; this waits until the harness reports the model and the tool server ready, asks the smoke test's question, and keeps the commit or rolls
back to the last good one. Exit codes: 0 deployed or nothing to do, 1 not deployed and the old commit is answering, 2 a person has to look.
"""

import argparse
import asyncio
import subprocess
import sys
import time
from collections.abc import Callable

import httpx

from assistant_core.harness_client import HarnessClient
from assistant_service.settings import load_harness_config
from ops import deploy, paths, smoke
from serving.settings import read_api_key

DEPLOYED = 0
NOT_DEPLOYED = 1
NEEDS_A_PERSON = 2
# A restart of llama-server reloads the model from disk, which takes minutes for a large one.
READY_TIMEOUT_SECONDS = 900
READY_POLL_SECONDS = 5
ACTIONS_THAT_RESTART_THE_ANSWER_PATH = {"sync_env", "reinstall_agents", "restart:llama", "restart:mcp", "restart:harness"}


def deploy_here(ref: str, smoke_flags: list[str], run_tests: bool) -> int:
    refuse_a_branch_checkout()
    remember_the_running_commit_as_good()
    summary = deploy.with_lock(lambda: deploy.switch_to(ref, run_tests=run_tests, dry_run=False))
    print(f"deploy: {summary['to'][:10]}  {deploy.git('log', '-1', '--format=%s', summary['to'])}")
    if not summary["applied"]:
        return report_nothing_applied(summary)
    print(f"deploy: tests {summary['tests'] or 'skipped'}; restarted: {', '.join(summary['plan']) or 'nothing'}")
    if answers_after(summary["plan"], smoke_flags):
        deploy.mark_good(summary["to"])
        deploy.clear_maintenance()
        print(f"deploy: done. {summary['to'][:10]} is live and recorded as the last good commit")
        return DEPLOYED
    print("deploy: the test question FAILED; going back to the last good commit", file=sys.stderr)
    return roll_back(smoke_flags)


def refuse_a_branch_checkout() -> None:
    """The serving checkout is detached at one commit; a checkout on a branch is somebody's working copy, which a deploy would detach."""
    on_a_branch = subprocess.run(["git", "-C", str(deploy.PROJECT_DIR), "symbolic-ref", "-q", "HEAD"], capture_output=True).returncode == 0
    if on_a_branch:
        raise SystemExit(f"deploy: {deploy.PROJECT_DIR} is on a branch; run this from the serving checkout (~/Code/home_assistant_live)")


def remember_the_running_commit_as_good() -> None:
    """A Mac set up before this script has no last good commit, so the first failed deploy would have nothing to return to. The commit it runs
    today is the best one known."""
    if not paths.last_good_ref().exists():
        sha = deploy.mark_good("HEAD")
        print(f"deploy: no last good commit recorded yet; recording the running one, {sha[:10]}")


def report_nothing_applied(summary: dict) -> int:
    # Nothing restarted and the old commit is checked out again, so the health check can go back to work.
    deploy.clear_maintenance()
    if summary.get("note") == "already at this commit":
        print("deploy: already at this commit; nothing to do")
        return DEPLOYED
    print(f"deploy: NOT deployed. Tests {summary['tests']}", file=sys.stderr)
    print(f"deploy: still running {summary['from'][:10]}; nothing was restarted", file=sys.stderr)
    return NOT_DEPLOYED


def answers_after(plan: list[str], smoke_flags: list[str]) -> bool:
    if ACTIONS_THAT_RESTART_THE_ANSWER_PATH.intersection(plan):
        wait_until_ready(lambda: asyncio.run(harness_reports_ready()))
    return smoke.main(smoke_flags) == 0


def wait_until_ready(is_ready: Callable[[], bool], timeout_seconds: float = READY_TIMEOUT_SECONDS, poll_seconds: float = READY_POLL_SECONDS) -> bool:
    """Poll until the harness reports both of its dependencies; the smoke test then judges the answers, not the start-up time."""
    print("deploy: waiting for the model and the tool server to be ready", flush=True)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if is_ready():
            return True
        time.sleep(poll_seconds)
    print(f"deploy: not ready after {timeout_seconds:.0f} s; asking the test question anyway", file=sys.stderr)
    return False


async def harness_reports_ready() -> bool:
    service = load_harness_config().service
    client = HarnessClient(f"http://127.0.0.1:{service.port}", read_api_key(service.api_key_path))
    try:
        return (await client.health()).status == "ok"
    except httpx.HTTPError:
        return False


def roll_back(smoke_flags: list[str]) -> int:
    summary = deploy.with_lock(lambda: deploy.switch_to(paths.last_good_ref().read_text().strip(), run_tests=False, dry_run=False))
    if answers_after(summary["plan"], smoke_flags):
        deploy.clear_maintenance()
        print(f"deploy: rolled back to {summary['to'][:10]}, which answers. The new commit was NOT kept", file=sys.stderr)
        return NOT_DEPLOYED
    print("deploy: the last good commit does not answer either. The health check stays off until you look: scripts/services.sh status", file=sys.stderr)
    return NEEDS_A_PERSON


def show_plan(ref: str) -> int:
    summary = deploy.switch_to(ref, run_tests=False, dry_run=True)
    print(f"deploy (dry run): {summary['from'][:10]} -> {summary['to'][:10]}, {summary['changed']} files changed")
    for action in summary["plan"]:
        print(f"  {action:20} {summary['reasons'][action]}")
    if not summary["plan"]:
        print("  nothing to restart")
    return DEPLOYED


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deploy a commit to this Mac: test it, restart what changed, ask the test question, keep it or roll back.")
    parser.add_argument("--ref", default="origin/main", help="what to deploy (default: origin/main, fetched first)")
    parser.add_argument("--full-smoke", action="store_true", help="also ask a searched question, which needs the web")
    parser.add_argument("--skip-tests", action="store_true", help="skip the test suite before restarting")
    parser.add_argument("--dry-run", action="store_true", help="print what would restart and why, and change nothing")
    args = parser.parse_args(argv)
    if args.dry_run:
        return show_plan(args.ref)
    return deploy_here(args.ref, ["--full"] if args.full_smoke else [], run_tests=not args.skip_tests)


if __name__ == "__main__":
    sys.exit(main())
