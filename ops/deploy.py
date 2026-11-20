"""The deploy protocol that runs on the Mac mini (design doc 10 §3.8).

The laptop drives it over SSH:  python -m ops.deploy apply --ref SHA | rollback | mark-good SHA | clear-maintenance | status

`apply` raises the maintenance flag (so the health check stands down), fetches and checks out the exact commit, syncs the environments if the
lock changed, runs the tests, then derives the smallest set of restarts from what changed between the old and new commits, adding a restart for
each service whose environment's installed packages the sync actually changed. The rules table is
data and `plan_actions` is pure, so the tests pin it. Nothing here talks to the laptop: the smoke test and the decision to mark the commit good
or roll back happen on the laptop side (scripts/mini.sh), which is the only place that can see both ends.
"""

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import NamedTuple

from packaging.requirements import Requirement
from packaging.version import Version
from pydantic import BaseModel

from ops import paths
from utils import launchd_utils

PROJECT_DIR = Path(__file__).resolve().parent.parent
HEALTH_AGENT = "health"
MANIFEST = PROJECT_DIR / "custom_components" / "studio_assistant" / "manifest.json"
LOCK = PROJECT_DIR / "uv.lock"
PATH_WITH_BREW = "/opt/homebrew/bin:" + os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
SERVICES_SCRIPT = PROJECT_DIR / "scripts" / "services.sh"


class Rule(BaseModel):
    prefixes: tuple[str, ...]
    actions: tuple[str, ...]
    why: str


class Environment(NamedTuple):
    folder: str
    setup_script: str
    restarts: tuple[str, ...]  # the services that run from it


# A lock change can move packages in one environment and not the other (a speech-group bump leaves .venv alone), so each is restarted only when
# its sync changed what is installed.
ENVIRONMENTS = (
    Environment(".venv", "dev_setup.sh", ("restart:mcp", "restart:harness", "restart:dashboard", "restart:kokoro")),
    Environment(".venv-speech", "speech_env.sh", ("restart:speech",)),
)


# Order matters twice: rules are matched in this order, and ACTION_ORDER below decides execution order.
RULES: tuple[Rule, ...] = (
    Rule(
        prefixes=("uv.lock", "pyproject.toml"),
        actions=("sync_env",),
        why="dependencies changed: sync both environments, then restart the services of each one whose installed packages changed",
    ),
    Rule(
        prefixes=(
            "assistant_mcp/",
            "web_search_mcp/",
            "calculator_mcp/",
            "weather_mcp/",
            "wikipedia_mcp/",
            "sports_mcp/",
            "broadway_mcp/",
            "movies_mcp/",
            "reddit_mcp/",
            "restaurants_mcp/",
            "newsletters_mcp/",
            "assistant_core/",
            "utils/",
        ),
        actions=("restart:mcp",),
        why="tool server code changed",
    ),
    Rule(prefixes=("assistant_core/", "assistant_service/", "config/harness.toml", "utils/"), actions=("restart:harness",), why="the harness's code or settings changed"),
    Rule(prefixes=("custom_components/", *paths.VENDORED_CORE_FILES), actions=("deploy_component",), why="the component or its vendored core changed"),
    Rule(
        prefixes=("config/serving.toml", "serving/", "scripts/strata_patches/"),
        actions=("restart:llama", "restart:harness"),
        why="the engine's settings, its launcher or Strata's patches changed; the harness reads the model's budget from them",
    ),
    Rule(prefixes=("voice/", "utils/pronunciation_utils.py"), actions=("restart:kokoro",), why="Kokoro server wrapper, or the pronunciation dictionary code it runs, changed"),
    Rule(prefixes=("speech_server/", "config/speech.toml", "scripts/speech_env.sh"), actions=("restart:speech",), why="the speech server's code or settings changed"),
    Rule(prefixes=("scripts/services.sh",), actions=("reinstall_agents",), why="launchd definitions changed"),
    Rule(prefixes=("docker/searxng/",), actions=("restart_searxng",), why="SearXNG configuration changed"),
    Rule(prefixes=("config/tools.toml",), actions=("restart:harness",), why="the tools the harness may call changed; it reads them at start"),
    Rule(
        prefixes=("dashboard/", "assistant_core/", "assistant_service/", "ops/paths.py", "utils/"),
        actions=("restart:dashboard",),
        why="the exchange dashboard's code, or code it imports, changed",
    ),
)
ACTION_ORDER = (
    "sync_env",
    "reinstall_agents",
    "restart:llama",
    "restart:mcp",
    "restart:harness",
    "restart:dashboard",
    "restart:kokoro",
    "restart:speech",
    "restart_searxng",
    "deploy_component",
)
# Actions that start the engine again; before them `serving check` must pass, or launchd would keep restarting a launch that refuses.
ENGINE_STARTS = {"restart:llama", "reinstall_agents"}
RESTARTS_COVERED_BY_REINSTALL = {"restart:llama", "restart:mcp", "restart:harness", "restart:dashboard", "restart:kokoro", "restart:speech"}


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
    return ordered_plan(wanted, changed)


def plan_after_sync(plan: Plan, changed_environments: Iterable[Environment]) -> Plan:
    """The plan with a restart for every service whose environment the sync changed; a reinstall still covers them all."""
    wanted = dict(plan.reasons)
    for environment in changed_environments:
        for action in environment.restarts:
            wanted.setdefault(action, f"{environment.folder}: the sync changed its installed packages")
    return ordered_plan(wanted, plan.changed)


def ordered_plan(wanted: dict[str, str], changed: list[str]) -> Plan:
    if "reinstall_agents" in wanted:
        wanted = {action: why for action, why in wanted.items() if action not in RESTARTS_COVERED_BY_REINSTALL}
    ordered = [action for action in ACTION_ORDER if action in wanted]
    return Plan(actions=ordered, reasons={action: wanted[action] for action in ordered}, changed=changed)


def environments_changed(before: dict[str, frozenset[str]], after: dict[str, frozenset[str]]) -> list[Environment]:
    return [environment for environment in ENVIRONMENTS if before[environment.folder] != after[environment.folder]]


def installed_packages() -> dict[str, frozenset[str]]:
    """Per environment, its dist-info folder names, which carry each installed package's name and version; empty for one not made yet."""
    return {environment.folder: frozenset(path.name for path in (PROJECT_DIR / environment.folder).glob("lib/python*/site-packages/*.dist-info")) for environment in ENVIRONMENTS}


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
        for environment in ENVIRONMENTS:
            run([str(scripts / environment.setup_script)])
    elif action == "reinstall_agents":
        retire_agents_the_checkout_does_not_list()
        run([str(scripts / "services.sh"), "install"])
    elif action.startswith("restart:"):
        run([str(scripts / "services.sh"), "restart", action.split(":", 1)[1]])
    elif action == "restart_searxng":
        run([str(scripts / "searxng.sh"), "restart"])
    elif action == "deploy_component":
        run([str(PROJECT_DIR / ".venv" / "bin" / "python"), str(scripts / "deploy_component.py")])
    else:
        raise ValueError(f"unknown action {action}")


def retire_agents_the_checkout_does_not_list() -> None:
    """An agent a newer commit added stays loaded when a deploy goes back to a commit that never heard of it: rolling back past the speech server
    would leave it holding port 10300 against the Whisper agent the old install starts. So before installing, unload and delete every agent of
    ours that the checked-out services.sh does not list."""
    for name in sorted(installed_agent_names() - services_listed_in(SERVICES_SCRIPT.read_text())):
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{paths.LAUNCHD_PREFIX}.{name}"], capture_output=True)
        (paths.LAUNCH_AGENTS_DIR / f"{paths.LAUNCHD_PREFIX}.{name}.plist").unlink(missing_ok=True)
        print(f"retired the {name} agent, which this commit's services.sh does not list", flush=True)


def installed_agent_names() -> set[str]:
    return {path.name.removeprefix(f"{paths.LAUNCHD_PREFIX}.").removesuffix(".plist") for path in paths.LAUNCH_AGENTS_DIR.glob(f"{paths.LAUNCHD_PREFIX}.*.plist")}


def services_listed_in(services_script: str) -> set[str]:
    listed = re.search(r"^SERVICES=\(([^)]*)\)", services_script, re.MULTILINE)
    if listed is None:
        raise SystemExit("scripts/services.sh has no SERVICES=(...) line; refusing to guess which agents to keep")
    return set(listed.group(1).split())


def carry_out(actions: list[str]) -> list[str]:
    """Every action is tried even when one fails, so one failed step cannot leave the services after it stopped; the smoke test then decides
    whether the commit stays. Returns what failed."""
    failures = []
    for action in actions:
        try:
            execute(action)
        except subprocess.CalledProcessError as error:
            failures.append(f"{action} exited {error.returncode}")
    return failures


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
            packages_before = installed_packages()
            execute("sync_env")
            plan = plan_after_sync(plan, environments_changed(packages_before, installed_packages()))
            summary.update(plan=plan.actions, reasons=plan.reasons)
        check_manifest_matches_lock()
        if ENGINE_STARTS & set(plan.actions):
            run([str(PROJECT_DIR / ".venv" / "bin" / "serving"), "check"], timeout=300)  # hashes the model (about 47 GB), then checks Strata's install
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
    summary["failed_steps"] = carry_out([action for action in plan.actions if action != "sync_env"])
    summary["applied"] = True
    return summary


def with_lock(fn: Callable[[], dict]) -> dict:
    paths.log_dir().mkdir(parents=True, exist_ok=True)
    with paths.deploy_lock().open("w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("another deploy is running on this machine") from None
        return fn()


def mark_good(ref: str) -> str:
    sha = git("rev-parse", "--verify", f"{ref}^{{commit}}")
    paths.log_dir().mkdir(parents=True, exist_ok=True)
    paths.last_good_ref().write_text(sha + "\n")
    return sha


def hand_back_to_health_check() -> None:
    """Lowers the maintenance flag and wakes the health check, so whatever the deploy left for it (SearXNG started or stopped to match what the
    new commit needs, a service to restart) happens now rather than at its next five-minute run."""
    paths.maintenance_flag().unlink(missing_ok=True)
    launchd_utils.wake_agent(HEALTH_AGENT)


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
        result = {"last_good_ref": mark_good(args.ref)}
    elif args.command == "clear-maintenance":
        hand_back_to_health_check()
        result = {"maintenance": False}
    else:
        result = status()
    print(json.dumps(result, indent=1))
    if args.command == "apply" and not result["applied"] and not args.dry_run and result.get("note") != "already at this commit":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
