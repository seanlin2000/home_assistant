"""The deploy protocol that runs on the Mac mini (design doc 10 §3.8).

The laptop drives it over SSH:  python -m ops.deploy apply --ref SHA | rollback | mark-good SHA | clear-maintenance | status

`apply` raises the maintenance flag (so the health check stands down), fetches and checks out the exact commit, syncs the environment if the
lock changed, runs the tests, then derives the smallest set of restarts from what changed between the old and new commits. The rules table is
data and `plan_actions` is pure, so the tests pin it. Nothing here talks to the laptop: the smoke test and the decision to mark the commit good
or roll back happen on the laptop side (scripts/mini.sh), which is the only place that can see both ends.
"""

import argparse
import fcntl
import json
import os
import subprocess
import sys
import tomllib
from collections.abc import Iterable
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version
from pydantic import BaseModel

from ops import paths

PROJECT_DIR = Path(__file__).resolve().parent.parent
MANIFEST = PROJECT_DIR / "custom_components" / "studio_assistant" / "manifest.json"
LOCK = PROJECT_DIR / "uv.lock"
PATH_WITH_BREW = "/opt/homebrew/bin:" + os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")


class Rule(BaseModel):
    prefixes: tuple[str, ...]
    actions: tuple[str, ...]
    why: str


# Order matters twice: rules are matched in this order, and ACTION_ORDER below decides execution order.
RULES: tuple[Rule, ...] = (
    Rule(
        prefixes=("uv.lock", "pyproject.toml"),
        actions=("sync_env", "restart:mcp", "restart:whisper", "restart:kokoro"),
        why="dependencies changed: sync the venv and restart every long-running Python service",
    ),
    Rule(prefixes=("web_search_mcp/", "calculator_mcp/", "assistant_core/", "utils/"), actions=("restart:mcp",), why="tool server code changed"),
    Rule(prefixes=("custom_components/", "assistant_core/"), actions=("deploy_component",), why="the component or its vendored core changed"),
    Rule(prefixes=("voice/",), actions=("restart:kokoro",), why="Kokoro server wrapper changed"),
    Rule(prefixes=("scripts/services.sh",), actions=("reinstall_agents",), why="launchd definitions changed"),
    Rule(prefixes=("docker/searxng/",), actions=("restart_searxng",), why="SearXNG configuration changed"),
)
ACTION_ORDER = ("sync_env", "reinstall_agents", "restart:mcp", "restart:kokoro", "restart:whisper", "restart_searxng", "deploy_component")
RESTARTS_COVERED_BY_REINSTALL = {"restart:mcp", "restart:kokoro", "restart:whisper"}


class Plan(BaseModel):
    actions: list[str]
    reasons: dict[str, str]  # action -> the first rule that asked for it
    changed: list[str]


def plan_actions(changed_paths: Iterable[str]) -> Plan:
    changed = sorted(set(changed_paths))
    wanted: dict[str, str] = {}
    for path in changed:
        for rule in RULES:
            if any(path == prefix or path.startswith(prefix) for prefix in rule.prefixes):
                for action in rule.actions:
                    wanted.setdefault(action, f"{path}: {rule.why}")
    if "reinstall_agents" in wanted:
        for action in RESTARTS_COVERED_BY_REINSTALL:
            wanted.pop(action, None)
    ordered = [action for action in ACTION_ORDER if action in wanted]
    return Plan(actions=ordered, reasons={action: wanted[action] for action in ordered}, changed=changed)


# ---------------------------------------------------------------- preflight


def manifest_lock_mismatches(manifest_text: str, lock_text: str) -> list[str]:
    """Design doc 09 §4: the component's manifest must ask Home Assistant for the versions the venv was tested with.

    Home Assistant installs the manifest's `requirements` into its own environment; if they drift from uv.lock, the vendored assistant_core runs
    against a pydantic or ollama it was never tested with."""
    locked = {package["name"].lower(): Version(package["version"]) for package in tomllib.loads(lock_text).get("package", []) if "version" in package}
    problems = []
    for spec in json.loads(manifest_text).get("requirements", []):
        requirement = Requirement(spec)
        name = requirement.name.lower()
        if name not in locked:
            problems.append(f"{spec}: not in uv.lock")
        elif not requirement.specifier.contains(locked[name], prereleases=True):
            problems.append(f"{spec}: uv.lock has {locked[name]}")
    return problems


def check_manifest_matches_lock() -> None:
    problems = manifest_lock_mismatches(MANIFEST.read_text(), LOCK.read_text())
    if problems:
        raise SystemExit("manifest.json disagrees with uv.lock: " + "; ".join(problems))


# ---------------------------------------------------------------- shell helpers


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(PROJECT_DIR), *args], check=True, capture_output=True, text=True).stdout.strip()


def run(cmd: list[str], timeout: int = 1800) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=PROJECT_DIR, env={**os.environ, "PATH": PATH_WITH_BREW}, timeout=timeout)


def tree_is_dirty() -> bool:
    return bool(git("status", "--porcelain", "--untracked-files=no"))


def execute(action: str) -> None:
    scripts = PROJECT_DIR / "scripts"
    if action == "sync_env":
        run([str(scripts / "dev_setup.sh")])
    elif action == "reinstall_agents":
        run([str(scripts / "services.sh"), "install"])
    elif action.startswith("restart:"):
        run([str(scripts / "services.sh"), "restart", action.split(":", 1)[1]])
    elif action == "restart_searxng":
        run([str(scripts / "searxng.sh"), "restart"])
    elif action == "deploy_component":
        run([str(PROJECT_DIR / ".venv" / "bin" / "python"), str(scripts / "deploy_component.py")])
    else:
        raise ValueError(f"unknown action {action}")


# ---------------------------------------------------------------- commands


def switch_to(ref: str, run_tests: bool, dry_run: bool) -> dict:
    """Check out `ref`, sync and test as needed, and carry out the plan. Returns a summary for the laptop to print."""
    paths.log_dir().mkdir(parents=True, exist_ok=True)
    if tree_is_dirty() and not dry_run:
        raise SystemExit("the checkout on this machine has local changes; refusing to deploy over them")
    old = git("rev-parse", "HEAD")
    git("fetch", "--quiet", "origin")
    new = git("rev-parse", "--verify", f"{ref}^{{commit}}")
    changed = git("diff", "--name-only", old, new).splitlines()
    plan = plan_actions(changed)
    summary = {"from": old, "to": new, "changed": len(changed), "plan": plan.actions, "reasons": plan.reasons, "tests": None, "applied": False}
    if dry_run or old == new and not plan.actions:
        summary["note"] = "already at this commit" if old == new else "dry run"
        return summary
    paths.maintenance_flag().touch()
    git("checkout", "--detach", "--quiet", new)
    try:
        if "sync_env" in plan.actions:
            execute("sync_env")
        check_manifest_matches_lock()
        if run_tests:
            run([str(PROJECT_DIR / ".venv" / "bin" / "python"), "-m", "pytest", "-q", "-x"], timeout=900)
            summary["tests"] = "passed"
    except (subprocess.CalledProcessError, SystemExit) as error:
        git("checkout", "--detach", "--quiet", old)
        if "sync_env" in plan.actions:
            execute("sync_env")  # put the environment back with the old lock
        summary["tests"] = f"failed: {error}"
        summary["note"] = f"aborted before any restart; checkout returned to {old[:10]}; maintenance flag left set"
        return summary
    for action in plan.actions:
        if action != "sync_env":
            execute(action)
    summary["applied"] = True
    return summary


def with_lock(fn):
    paths.log_dir().mkdir(parents=True, exist_ok=True)
    with paths.deploy_lock().open("w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("another deploy is running on this machine") from None
        return fn()


def status() -> dict:
    head = git("rev-parse", "HEAD")
    last_good = paths.last_good_ref().read_text().strip() if paths.last_good_ref().exists() else None
    return {
        "head": head,
        "head_subject": git("log", "-1", "--format=%s", head),
        "last_good_ref": last_good,
        "head_is_last_good": head == last_good,
        "maintenance": paths.maintenance_flag().exists(),
        "dirty": tree_is_dirty(),
        "manifest_lock_mismatches": manifest_lock_mismatches(MANIFEST.read_text(), LOCK.read_text()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deploy protocol on the assistant's Mac (driven by scripts/mini.sh from the laptop).")
    sub = parser.add_subparsers(dest="command", required=True)
    apply = sub.add_parser("apply", help="check out a commit, test it, restart what changed; leaves the maintenance flag set")
    apply.add_argument("--ref", required=True, help="commit SHA (or remote branch) to deploy")
    apply.add_argument("--skip-tests", action="store_true")
    apply.add_argument("--dry-run", action="store_true", help="print the plan without changing anything")
    sub.add_parser("rollback", help="return to last_good_ref and apply the reverse plan (tests skipped: that commit already passed)")
    good = sub.add_parser("mark-good", help="record a commit as the last known good")
    good.add_argument("ref")
    sub.add_parser("clear-maintenance", help="remove the maintenance flag so the health check may act again")
    sub.add_parser("status")
    args = parser.parse_args(argv)

    if args.command == "apply":
        result = with_lock(lambda: switch_to(args.ref, run_tests=not args.skip_tests, dry_run=args.dry_run))
    elif args.command == "rollback":
        if not paths.last_good_ref().exists():
            raise SystemExit("no last_good_ref recorded on this machine; nothing to roll back to")
        result = with_lock(lambda: switch_to(paths.last_good_ref().read_text().strip(), run_tests=False, dry_run=False))
    elif args.command == "mark-good":
        sha = git("rev-parse", "--verify", f"{args.ref}^{{commit}}")
        paths.log_dir().mkdir(parents=True, exist_ok=True)
        paths.last_good_ref().write_text(sha + "\n")
        result = {"last_good_ref": sha}
    elif args.command == "clear-maintenance":
        paths.maintenance_flag().unlink(missing_ok=True)
        result = {"maintenance": False}
    else:
        result = status()
    print(json.dumps(result, indent=1))
    if args.command == "apply" and not result["applied"] and not args.dry_run and result.get("note") != "already at this commit":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
