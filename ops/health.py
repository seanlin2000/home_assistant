"""Health check and self-healing for the Mac that runs the assistant (design doc 10 §3.5 and §3.6).

launchd runs `scripts/health_check.py` every five minutes. Each run probes every part of the stack, records a snapshot, and decides from a
policy table whether to do anything about a failure. The decision is a pure function of the snapshot, the state carried from earlier runs, and
the policy, so the thresholds and cooldowns are unit-tested without touching launchd, UTM, or the network.
"""

import asyncio
import json
import os
import re
import shutil
import socket
import subprocess
import time
from collections.abc import Awaitable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from assistant_core.models import REQUIRED_TOOL_NAMES
from ops import paths
from utils.jsonl_utils import append_jsonl
from web_search_mcp.turn_log import TurnLog

LAUNCHD_PREFIX = "com.studio-assistant"
LAUNCHD_SERVICES = ("ollama", "mcp", "whisper", "kokoro")
DEFAULT_VM_NAME = "Home Assistant"
PROJECT_DIR = Path(__file__).resolve().parent.parent
SNAPSHOT_HISTORY_DAYS = 90
ROTATE_OVER_BYTES = 20 * 1024 * 1024
ROTATE_GENERATIONS = 3


class Check(BaseModel):
    ok: bool | None  # None: the part is deliberately not installed or unloaded here, so it is neither healthy nor failing
    detail: str = ""
    seconds: float = 0.0


class Memory(BaseModel):
    free_percent: int | None = None
    swap_used_mb: float | None = None
    resident_models: list[str] = Field(default_factory=list)
    resident_model_mb: float | None = None


class Snapshot(BaseModel):
    checked_at: str
    checks: dict[str, Check]
    memory: Memory = Field(default_factory=Memory)
    maintenance: bool = False
    full: bool = False
    actions: list[str] = Field(default_factory=list)  # what this run did to the machine, in order
    housekeeping: list[str] = Field(default_factory=list)

    @property
    def failing(self) -> list[str]:
        return sorted(name for name, check in self.checks.items() if check.ok is False)


class State(BaseModel):
    """Carried between runs in health_state.json."""

    consecutive_failures: dict[str, int] = Field(default_factory=dict)
    last_action_at: dict[str, float] = Field(default_factory=dict)  # action key -> unix time
    last_housekeeping_day: str | None = None


class Policy(BaseModel):
    agent_failures: int = 2
    agent_cooldown_seconds: float = 30 * 60
    searxng_failures: int = 2
    searxng_cooldown_seconds: float = 30 * 60
    vm_start_cooldown_seconds: float = 30 * 60
    ha_failures: int = 5
    vm_restart_cooldown_seconds: float = 2 * 60 * 60


class Action(BaseModel):
    kind: str  # kickstart | searxng_up | vm_start | vm_restart
    target: str
    reason: str

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.target}"


class Settings(BaseModel):
    ollama_url: str = "http://127.0.0.1:11434"
    mcp_url: str = "http://127.0.0.1:8765"
    whisper_port: int = 10300
    kokoro_port: int = 10210
    searxng_url: str = "http://127.0.0.1:8080"
    ha_base: str | None = None
    ha_token: str | None = None
    vm_name: str = DEFAULT_VM_NAME
    probe_timeout_seconds: float = 5.0


def settings_from_environment() -> Settings:
    host = os.environ.get("HA_HOST")
    return Settings(
        ha_base=os.environ.get("HA_BASE") or (f"http://{host}" if host else None),
        ha_token=os.environ.get("HA_TOKEN"),
        vm_name=os.environ.get("HAOS_VM_NAME", DEFAULT_VM_NAME),
        searxng_url=os.environ.get("SEARXNG_URL", "http://127.0.0.1:8080"),
    )


# ---------------------------------------------------------------- probes


async def run_checks(settings: Settings, full: bool = False) -> dict[str, Check]:
    async with httpx.AsyncClient(timeout=settings.probe_timeout_seconds) as client:
        results = await asyncio.gather(
            timed("ollama", check_ollama(client, settings)),
            timed("mcp", check_mcp(client, settings)),
            timed("whisper", check_tcp("127.0.0.1", settings.whisper_port, settings.probe_timeout_seconds)),
            timed("kokoro", check_tcp("127.0.0.1", settings.kokoro_port, settings.probe_timeout_seconds)),
            timed("searxng", check_searxng(client, settings, full)),
            timed("home_assistant", check_home_assistant(client, settings)),
            timed("vm", asyncio.to_thread(check_vm, settings.vm_name)),
        )
    checks = dict(results)
    for name in LAUNCHD_SERVICES:
        if checks[name].ok is False and not agent_loaded(name):
            checks[name] = Check(ok=None, detail="launchd agent not loaded (stopped on purpose)")
    return checks


async def timed(name: str, probe: Awaitable[Check]) -> tuple[str, Check]:
    started = time.monotonic()
    try:
        check = await probe
    except Exception as error:  # noqa: BLE001 - a probe that blows up is a failed check, not a crashed health run
        check = Check(ok=False, detail=f"{type(error).__name__}: {error}"[:200])
    check.seconds = round(time.monotonic() - started, 3)
    return name, check


async def check_ollama(client: httpx.AsyncClient, settings: Settings) -> Check:
    response = await client.get(f"{settings.ollama_url}/api/version")
    if response.status_code != 200:
        return Check(ok=False, detail=f"HTTP {response.status_code}")
    return Check(ok=True, detail=f"ollama {response.json().get('version', '?')}")


async def check_mcp(client: httpx.AsyncClient, settings: Settings) -> Check:
    response = await client.get(f"{settings.mcp_url}/healthz")
    if response.status_code != 200:
        return Check(ok=False, detail=f"HTTP {response.status_code}")
    body = response.json()
    missing = sorted(REQUIRED_TOOL_NAMES - set(body.get("tools", [])))
    if missing:
        return Check(ok=False, detail=f"not our tool server: missing {', '.join(missing)}")
    return Check(ok=True, detail=f"{len(body['tools'])} tools")


async def check_tcp(host: str, port: int, timeout: float) -> Check:
    _reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    writer.close()
    await writer.wait_closed()
    return Check(ok=True, detail=f"port {port} open")


async def check_searxng(client: httpx.AsyncClient, settings: Settings, full: bool) -> Check:
    if not full:
        response = await client.get(settings.searxng_url)
        return Check(ok=response.status_code < 500, detail=f"HTTP {response.status_code}")
    response = await client.get(f"{settings.searxng_url}/search", params={"q": "test", "format": "json"}, timeout=20)
    if response.status_code != 200:
        return Check(ok=False, detail=f"search HTTP {response.status_code}")
    count = len(response.json().get("results", []))
    return Check(ok=count > 0, detail=f"{count} results for a test query")


async def check_home_assistant(client: httpx.AsyncClient, settings: Settings) -> Check:
    if not settings.ha_base:
        return Check(ok=None, detail="HA_BASE and HA_HOST unset")
    headers = {"Authorization": f"Bearer {settings.ha_token}"} if settings.ha_token else {}
    response = await client.get(f"{settings.ha_base}/api/", headers=headers)
    if response.status_code in (200, 401):
        return Check(ok=True, detail=f"HTTP {response.status_code}")
    return Check(ok=False, detail=f"HTTP {response.status_code}")


def check_vm(vm_name: str) -> Check:
    if shutil.which("utmctl") is None:
        return Check(ok=None, detail="utmctl not installed")
    result = subprocess.run(["utmctl", "status", vm_name], capture_output=True, text=True, timeout=30)
    return parse_vm_status(result.returncode, result.stdout, result.stderr)


def parse_vm_status(returncode: int, stdout: str, stderr: str) -> Check:
    status = stdout.strip().lower()
    if returncode != 0:
        return Check(ok=None, detail=f"utmctl failed: {stderr.strip()[:120] or status}")
    return Check(ok=status == "started", detail=status or "unknown")


def agent_loaded(name: str) -> bool:
    result = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{LAUNCHD_PREFIX}.{name}"], capture_output=True, text=True)
    return result.returncode == 0


# ---------------------------------------------------------------- memory


def read_memory(settings: Settings) -> Memory:
    memory = Memory()
    try:
        memory.free_percent = parse_memory_pressure(subprocess.run(["memory_pressure"], capture_output=True, text=True, timeout=10).stdout)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        memory.swap_used_mb = parse_swapusage(subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, timeout=10).stdout)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        response = httpx.get(f"{settings.ollama_url}/api/ps", timeout=settings.probe_timeout_seconds)
        models = response.json().get("models", []) if response.status_code == 200 else []
        memory.resident_models = [model.get("name", "?") for model in models]
        memory.resident_model_mb = round(sum(model.get("size", 0) for model in models) / 1e6, 1) if models else 0.0
    except (httpx.HTTPError, ValueError):
        pass
    return memory


def parse_memory_pressure(text: str) -> int | None:
    match = re.search(r"free percentage:\s*(\d+)%", text)
    return int(match.group(1)) if match else None


def parse_swapusage(text: str) -> float | None:
    match = re.search(r"used\s*=\s*([\d.]+)([MG])", text)
    if not match:
        return None
    value = float(match.group(1))
    return round(value * 1024, 1) if match.group(2) == "G" else value


# ---------------------------------------------------------------- policy


def update_failure_counts(state: State, checks: dict[str, Check]) -> State:
    counts = dict(state.consecutive_failures)
    for name, check in checks.items():
        counts[name] = counts.get(name, 0) + 1 if check.ok is False else 0
    return state.model_copy(update={"consecutive_failures": counts})


def decide_actions(checks: dict[str, Check], state: State, policy: Policy, now: float, maintenance: bool) -> list[Action]:
    """The policy table from design doc 10 §3.5. `state` must already hold this run's failure counts."""
    if maintenance:
        return []
    actions: list[Action] = []

    def cooled(key: str, cooldown: float) -> bool:
        return now - state.last_action_at.get(key, float("-inf")) >= cooldown

    failures = state.consecutive_failures
    for name in LAUNCHD_SERVICES:
        if failures.get(name, 0) >= policy.agent_failures and cooled(f"kickstart:{name}", policy.agent_cooldown_seconds):
            actions.append(Action(kind="kickstart", target=name, reason=f"{name} failed {failures[name]} checks in a row"))
    if failures.get("searxng", 0) >= policy.searxng_failures and cooled("searxng_up:searxng", policy.searxng_cooldown_seconds):
        actions.append(Action(kind="searxng_up", target="searxng", reason=f"searxng failed {failures['searxng']} checks in a row"))
    vm_check = checks.get("vm")
    if vm_check is not None and vm_check.ok is False and cooled("vm_start:vm", policy.vm_start_cooldown_seconds):
        actions.append(Action(kind="vm_start", target="vm", reason=f"vm is {vm_check.detail}"))
    elif vm_check is not None and vm_check.ok and failures.get("home_assistant", 0) >= policy.ha_failures and cooled("vm_restart:vm", policy.vm_restart_cooldown_seconds):
        actions.append(Action(kind="vm_restart", target="vm", reason=f"home assistant failed {failures['home_assistant']} checks while the vm runs"))
    return actions


def execute(action: Action, settings: Settings) -> str:
    """Run one action and return a one-line account of it for the snapshot."""
    if action.kind == "kickstart":
        result = subprocess.run(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{LAUNCHD_PREFIX}.{action.target}"], capture_output=True, text=True)
    elif action.kind == "searxng_up":
        result = subprocess.run([str(PROJECT_DIR / "scripts" / "searxng.sh"), "up"], capture_output=True, text=True, timeout=120)
    elif action.kind == "vm_start":
        result = subprocess.run(["utmctl", "start", settings.vm_name], capture_output=True, text=True, timeout=60)
    elif action.kind == "vm_restart":
        subprocess.run(["utmctl", "stop", settings.vm_name], capture_output=True, text=True, timeout=120)
        time.sleep(10)
        result = subprocess.run(["utmctl", "start", settings.vm_name], capture_output=True, text=True, timeout=60)
    else:
        raise ValueError(f"unknown action {action.kind}")
    outcome = "ok" if result.returncode == 0 else f"exit {result.returncode}: {(result.stderr or result.stdout).strip()[:120]}"
    return f"{action.key} ({action.reason}): {outcome}"


# ---------------------------------------------------------------- housekeeping


def rotate_log(path: Path, over_bytes: int = ROTATE_OVER_BYTES, generations: int = ROTATE_GENERATIONS) -> bool:
    """Copy-truncate: copy the live file to .1 (shifting older generations up), then truncate it in place.

    launchd holds the file open with O_APPEND, so the writer carries on at the new end without a restart."""
    if not path.exists() or path.stat().st_size <= over_bytes:
        return False
    for index in range(generations, 1, -1):
        older = path.with_name(f"{path.name}.{index}")
        newer = path.with_name(f"{path.name}.{index - 1}")
        if newer.exists():
            newer.replace(older)
    shutil.copyfile(path, path.with_name(f"{path.name}.1"))
    with path.open("r+b") as live:
        live.truncate(0)
    return True


def prune_history(path: Path, retention_days: int = SNAPSHOT_HISTORY_DAYS, today: date | None = None) -> int:
    """Drop health snapshots older than the retention period; returns how many lines were removed."""
    if not path.exists():
        return 0
    cutoff = ((today or datetime.now(UTC).date()) - timedelta(days=retention_days)).isoformat()
    lines = path.read_text().splitlines()
    kept = [line for line in lines if snapshot_day(line) >= cutoff]
    if len(kept) != len(lines):
        path.write_text("".join(line + "\n" for line in kept))
    return len(lines) - len(kept)


def snapshot_day(line: str) -> str:
    try:
        return json.loads(line).get("checked_at", "")[:10]
    except ValueError:
        return ""


def housekeeping(today: date | None = None) -> list[str]:
    today = today or datetime.now(UTC).date()
    notes = []
    for name in paths.SERVICE_LOG_NAMES:
        if rotate_log(paths.service_log(name)):
            notes.append(f"rotated {name}.log")
    removed = prune_history(paths.health_jsonl(), today=today)
    if removed:
        notes.append(f"pruned {removed} health snapshots")
    for deleted in TurnLog(paths.turns_dir()).prune(today=today):
        notes.append(f"deleted {deleted.name}")
    return notes


# ---------------------------------------------------------------- one run


def load_state() -> State:
    path = paths.health_state()
    if path.exists():
        try:
            return State.model_validate_json(path.read_text())
        except ValueError:
            pass
    return State()


def save_state(state: State) -> None:
    paths.health_state().write_text(state.model_dump_json(indent=1))


def record_snapshot(snapshot: Snapshot) -> None:
    paths.log_dir().mkdir(parents=True, exist_ok=True)
    paths.health_json().write_text(snapshot.model_dump_json(indent=1))
    append_jsonl(paths.health_jsonl(), snapshot)


async def run_once(settings: Settings, policy: Policy | None = None, remediate: bool = True, dry_run: bool = False, full: bool = False) -> Snapshot:
    policy = policy or Policy()
    paths.log_dir().mkdir(parents=True, exist_ok=True)
    checks = await run_checks(settings, full=full)
    maintenance = paths.maintenance_flag().exists()
    state = update_failure_counts(load_state(), checks)
    now = time.time()
    snapshot = Snapshot(checked_at=datetime.now(UTC).isoformat(timespec="seconds"), checks=checks, memory=read_memory(settings), maintenance=maintenance, full=full)
    actions = decide_actions(checks, state, policy, now, maintenance) if remediate else []
    for action in actions:
        if dry_run:
            snapshot.actions.append(f"would run {action.key} ({action.reason})")
            continue
        snapshot.actions.append(execute(action, settings))
        state.last_action_at[action.key] = now
    today = datetime.now(UTC).date()
    if state.last_housekeeping_day != today.isoformat() and not dry_run:
        snapshot.housekeeping = housekeeping(today)
        state.last_housekeeping_day = today.isoformat()
    if not dry_run:
        save_state(state)
        record_snapshot(snapshot)
    return snapshot


def render(snapshot: Snapshot) -> str:
    width = max(len(name) for name in snapshot.checks)
    lines = [f"health at {snapshot.checked_at}" + ("  [maintenance: no actions]" if snapshot.maintenance else "")]
    for name, check in snapshot.checks.items():
        mark = {True: "ok  ", False: "FAIL", None: "skip"}[check.ok]
        lines.append(f"  {mark} {name:<{width}}  {check.detail}  ({check.seconds:.2f}s)")
    memory = snapshot.memory
    resident = ", ".join(memory.resident_models) or "none"
    lines.append(f"  memory: free {memory.free_percent}%  swap used {memory.swap_used_mb} MB  resident model: {resident} ({memory.resident_model_mb} MB)")
    for action in snapshot.actions:
        lines.append(f"  action: {action}")
    for note in snapshot.housekeeping:
        lines.append(f"  housekeeping: {note}")
    return "\n".join(lines)
