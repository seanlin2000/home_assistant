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

from assistant_core.converse_protocol import HEALTH_PATH, HarnessHealth
from assistant_core.models import REQUIRED_TOOL_NAMES
from assistant_service.exchange_log import ExchangeLog, TraceLog
from assistant_service.settings import load_harness_config
from ops import paths
from ops.pipeline_runs import PipelineRunLog
from serving.settings import load_serving_config, read_api_key
from utils.browser_utils import CHROME_RELEASE_PATH, FALLBACK_CHROME_MAJOR, ChromeRelease
from utils.jsonl_utils import append_jsonl
from utils.snapshot_utils import SnapshotMissing, read_snapshot
from web_search_mcp.searxng_client import describe_unresponsive_engines

LAUNCHD_PREFIX = "com.studio-assistant"
LAUNCHD_SERVICES = ("llama", "mcp", "harness", "whisper", "kokoro")
LLAMA_SERVER_PROCESS = "llama-server"
LLAMA_RESTART_KEY = "kickstart:llama"
DEFAULT_VM_NAME = "Home Assistant"
PROJECT_DIR = Path(__file__).resolve().parent.parent
SNAPSHOT_HISTORY_DAYS = 90
CHROME_RELEASE_STALE_DAYS = 14  # the listings refresh records it nightly, and Chrome ships a major version about every four weeks
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


class LlamaSlot(BaseModel):
    """A llama-server slot that was working on a request when the health check looked."""

    slot: int
    task: int
    decoded: int  # tokens written so far for that request


class Snapshot(BaseModel):
    checked_at: str
    checks: dict[str, Check]
    memory: Memory = Field(default_factory=Memory)
    llama_busy_slots: list[LlamaSlot] = Field(default_factory=list)
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
    llama_busy_slots: list[LlamaSlot] = Field(default_factory=list)  # what the last run saw, to tell a stuck request from a slow one
    last_daily_restart_day: str | None = None  # local date of the last llama-server restart


class Policy(BaseModel):
    agent_failures: int = 2
    agent_cooldown_seconds: float = 30 * 60
    searxng_failures: int = 2
    searxng_cooldown_seconds: float = 30 * 60
    vm_start_cooldown_seconds: float = 30 * 60
    ha_failures: int = 5
    vm_restart_cooldown_seconds: float = 2 * 60 * 60
    manage_vm: bool = True  # False on the laptop, where the VM is stopped on purpose
    daily_restart_hour: int = 4  # local time
    daily_restart_window_hours: int = 2  # a night busy all through the window skips that day's restart rather than restart in the day
    daily_restart_quiet_seconds: float = 10 * 60  # nobody has talked to the assistant for this long


class LlamaWatch(BaseModel):
    """What this run found about llama-server beyond /health, for the policy."""

    stuck_slots: list[LlamaSlot] = Field(default_factory=list)
    daily_restart_due: bool = False


class Action(BaseModel):
    kind: str  # kickstart | searxng_up | vm_start | vm_restart
    target: str
    reason: str

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.target}"


class Settings(BaseModel):
    llama_server_url: str = "http://127.0.0.1:8090"
    llama_key_path: Path = Field(default_factory=lambda: load_serving_config().server.api_key_path)
    mcp_url: str = "http://127.0.0.1:8765"
    harness_url: str = "http://127.0.0.1:8770"
    harness_key_path: Path = Field(default_factory=lambda: load_harness_config().service.api_key_path)
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
            timed("llama", check_llama_server(client, settings)),
            timed("mcp", check_mcp(client, settings)),
            timed("harness", check_harness(client, settings)),
            timed("whisper", check_tcp("127.0.0.1", settings.whisper_port, settings.probe_timeout_seconds)),
            timed("kokoro", check_tcp("127.0.0.1", settings.kokoro_port, settings.probe_timeout_seconds)),
            timed("searxng", check_searxng(client, settings, full)),
            timed("home_assistant", check_home_assistant(client, settings)),
            timed("vm", asyncio.to_thread(check_vm, settings.vm_name)),
            timed("browser", asyncio.to_thread(check_browser_agent, CHROME_RELEASE_PATH, date.today())),
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


async def check_llama_server(client: httpx.AsyncClient, settings: Settings) -> Check:
    """llama-server's /health needs no key: 200 once the model is loaded, 503 while it loads, which is neither healthy nor a failure."""
    response = await client.get(f"{settings.llama_server_url}/health")
    if response.status_code == httpx.codes.SERVICE_UNAVAILABLE:
        return Check(ok=None, detail="loading the model")
    if response.status_code != httpx.codes.OK:
        return Check(ok=False, detail=f"HTTP {response.status_code}")
    return Check(ok=True, detail="model loaded")


async def read_busy_llama_slots(client: httpx.AsyncClient, settings: Settings) -> list[LlamaSlot]:
    """The slots working on a request. /slots needs llama-server's key; a server that does not answer has no busy slots, and its /health check says why."""
    try:
        response = await client.get(f"{settings.llama_server_url}/slots", headers={"authorization": f"Bearer {read_api_key(settings.llama_key_path)}"})
        return busy_slots(response.json()) if response.status_code == httpx.codes.OK else []
    except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError):
        return []


def busy_slots(reply: list[dict]) -> list[LlamaSlot]:
    return [LlamaSlot(slot=slot["id"], task=slot["id_task"], decoded=decoded_tokens(slot)) for slot in reply if slot.get("is_processing")]


def decoded_tokens(slot: dict) -> int:
    """llama-server reports the tokens written so far under next_token, as one object or a list of one."""
    next_token = slot.get("next_token") or [{}]
    first = next_token[0] if isinstance(next_token, list) else next_token
    return int(first.get("n_decoded", 0))


async def check_mcp(client: httpx.AsyncClient, settings: Settings) -> Check:
    response = await client.get(f"{settings.mcp_url}/healthz")
    if response.status_code != 200:
        return Check(ok=False, detail=f"HTTP {response.status_code}")
    body = response.json()
    missing = sorted(REQUIRED_TOOL_NAMES - set(body.get("tools", [])))
    if missing:
        return Check(ok=False, detail=f"not our tool server: missing {', '.join(missing)}")
    return Check(ok=True, detail=f"{len(body['tools'])} tools")


async def check_harness(client: httpx.AsyncClient, settings: Settings) -> Check:
    """The harness answers its /health only with its key. It is healthy when it answers; whether llama-server and the tool server answer it is
    reported beside, since restarting the harness would not fix them and their own checks restart them."""
    response = await client.get(f"{settings.harness_url}{HEALTH_PATH}", headers={"authorization": f"Bearer {read_api_key(settings.harness_key_path)}"})
    if response.status_code != httpx.codes.OK:
        return Check(ok=False, detail=f"HTTP {response.status_code}")
    reported = HarnessHealth.model_validate(response.json())
    unreachable = [name for name, answers in (("llama-server", reported.llama_server), ("tool server", reported.tool_server)) if not answers]
    return Check(ok=True, detail=f"cannot reach {' or '.join(unreachable)}" if unreachable else "llama-server and tool server reachable")


async def check_tcp(host: str, port: int, timeout: float) -> Check:
    _reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    writer.close()
    await writer.wait_closed()
    return Check(ok=True, detail=f"port {port} open")


async def check_searxng(client: httpx.AsyncClient, settings: Settings, full: bool) -> Check:
    if not full:
        response = await client.get(settings.searxng_url)
        return Check(ok=response.status_code < 500, detail=f"HTTP {response.status_code}")
    response = await client.get(f"{settings.searxng_url}/search", params={"q": "test", "format": "json", "categories": "web"}, timeout=20)
    if response.status_code != 200:
        return Check(ok=False, detail=f"search HTTP {response.status_code}")
    return engines_answering_check(response.json())


def engines_answering_check(reply: dict) -> Check:
    """Healthy while any web engine answers. The detail says when only one is left, because search then has no fallback, which is how it ran
    unnoticed on DuckDuckGo alone until 2026-10-09."""
    answering = sorted({engine for result in reply.get("results", []) for engine in result.get("engines", [])})
    silent = reply.get("unresponsive_engines", [])
    detail = f"{len(reply.get('results', []))} results from {', '.join(answering) or 'no engine'}"
    if len(answering) == 1:
        detail += " (no fallback)"
    if silent:
        detail += f"; not answering: {describe_unresponsive_engines(silent)}"
    return Check(ok=bool(answering), detail=detail)


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


def check_browser_agent(path: Path, today: date) -> Check:
    """Which Chrome the page reader and the listings refreshes name. A record the nightly refresh stopped updating fails: sites start turning an agent
    away within weeks of its version going stale."""
    try:
        release = read_snapshot(path, ChromeRelease)
    except SnapshotMissing:
        return no_browser_record()
    days_old = (today - release.refreshed_at.astimezone().date()).days
    detail = f"sending Chrome {max(release.major, FALLBACK_CHROME_MAJOR)}; Chrome {release.version} recorded {days_old} days ago"
    return Check(ok=days_old <= CHROME_RELEASE_STALE_DAYS, detail=detail)


def no_browser_record() -> Check:
    """Before the first nightly refresh the fallback version is sent; that is expected only while the listings agent is not loaded."""
    if agent_loaded("listings"):
        return Check(ok=False, detail=f"no Chrome release recorded although the listings agent is loaded; sending the fallback Chrome {FALLBACK_CHROME_MAJOR}")
    return Check(ok=None, detail=f"listings agent not loaded, so no Chrome release recorded; sending the fallback Chrome {FALLBACK_CHROME_MAJOR}")


def agent_loaded(name: str) -> bool:
    result = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{LAUNCHD_PREFIX}.{name}"], capture_output=True, text=True)
    return result.returncode == 0


# ---------------------------------------------------------------- memory


def read_memory() -> Memory:
    memory = Memory()
    try:
        memory.free_percent = parse_memory_pressure(subprocess.run(["memory_pressure"], capture_output=True, text=True, timeout=10).stdout)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        memory.swap_used_mb = parse_swapusage(subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, timeout=10).stdout)
    except (OSError, subprocess.SubprocessError):
        pass
    add_llama_server_memory(memory)
    return memory


def add_llama_server_memory(memory: Memory) -> None:
    """llama-server's resident memory: the weights, the KV pool, and the prompt cache in RAM (design doc v2/08 section 3.3)."""
    try:
        pids = subprocess.run(["pgrep", "-x", LLAMA_SERVER_PROCESS], capture_output=True, text=True, timeout=10).stdout.split()
        if not pids:
            return
        resident_kb = sum(int(value) for value in subprocess.run(["ps", "-o", "rss=", "-p", ",".join(pids)], capture_output=True, text=True, timeout=10).stdout.split())
    except (OSError, subprocess.SubprocessError, ValueError):
        return
    memory.resident_models.append(LLAMA_SERVER_PROCESS)
    memory.resident_model_mb = round((memory.resident_model_mb or 0.0) + resident_kb / 1024, 1)


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


def decide_actions(checks: dict[str, Check], state: State, policy: Policy, now: float, maintenance: bool, llama_watch: LlamaWatch | None = None) -> list[Action]:
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
    vm_check = checks.get("vm") if policy.manage_vm else None
    if vm_check is not None and vm_check.ok is False and cooled("vm_start:vm", policy.vm_start_cooldown_seconds):
        actions.append(Action(kind="vm_start", target="vm", reason=f"vm is {vm_check.detail}"))
    elif vm_check is not None and vm_check.ok and failures.get("home_assistant", 0) >= policy.ha_failures and cooled("vm_restart:vm", policy.vm_restart_cooldown_seconds):
        actions.append(Action(kind="vm_restart", target="vm", reason=f"home assistant failed {failures['home_assistant']} checks while the vm runs"))
    restart = llama_restart(checks.get("llama"), llama_watch or LlamaWatch())
    if restart is not None and cooled(LLAMA_RESTART_KEY, policy.agent_cooldown_seconds) and LLAMA_RESTART_KEY not in {action.key for action in actions}:
        actions.append(restart)
    return actions


def llama_restart(llama: Check | None, watch: LlamaWatch) -> Action | None:
    """llama-server keeps answering /health while a slot is stuck, so its failure count never rises; a stuck slot, or the day's refresh, restarts it."""
    if llama is None or not llama.ok:
        return None
    if watch.stuck_slots:
        return Action(kind="kickstart", target="llama", reason=f"slot {watch.stuck_slots[0].slot} made no progress on one request since the last check")
    if watch.daily_restart_due:
        return Action(kind="kickstart", target="llama", reason="daily refresh while nobody is talking to the assistant")
    return None


def stuck_llama_slots(previous: list[LlamaSlot], current: list[LlamaSlot]) -> list[LlamaSlot]:
    """A slot still on the same request with no new token a whole check interval later, when a spoken request takes seconds (design doc v2/10 §3.4)."""
    return [slot for slot in current if slot in previous]


def daily_restart_due(state: State, policy: Policy, local_now: datetime, last_exchange_at: float | None) -> bool:
    """Once a day, in the early-morning window, at the first check that finds nobody has talked to the assistant for a while."""
    in_window = policy.daily_restart_hour <= local_now.hour < policy.daily_restart_hour + policy.daily_restart_window_hours
    if not in_window or state.last_daily_restart_day == local_now.date().isoformat():
        return False
    return last_exchange_at is None or local_now.timestamp() - last_exchange_at >= policy.daily_restart_quiet_seconds


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
    for log in (ExchangeLog(paths.exchanges_dir()), TraceLog(paths.traces_dir()), PipelineRunLog(paths.pipeline_runs_dir())):
        notes.extend(f"deleted {log.directory.name}/{deleted.name}" for deleted in log.prune(today=today))
    return notes


# ---------------------------------------------------------------- one run


def last_exchange_at() -> float | None:
    """When the assistant last answered anyone: the newest exchange day file's modification time."""
    day_files = ExchangeLog(paths.exchanges_dir()).day_files()
    return day_files[-1][1].stat().st_mtime if day_files else None


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
    async with httpx.AsyncClient(timeout=settings.probe_timeout_seconds) as client:
        busy = await read_busy_llama_slots(client, settings)
    maintenance = paths.maintenance_flag().exists()
    state = update_failure_counts(load_state(), checks)
    now = time.time()
    local_now = datetime.now().astimezone()
    snapshot = Snapshot(checked_at=datetime.now(UTC).isoformat(timespec="seconds"), checks=checks, memory=read_memory(), llama_busy_slots=busy, maintenance=maintenance, full=full)
    watch = LlamaWatch(stuck_slots=stuck_llama_slots(state.llama_busy_slots, busy), daily_restart_due=daily_restart_due(state, policy, local_now, last_exchange_at()))
    actions = decide_actions(checks, state, policy, now, maintenance, watch) if remediate else []
    for action in actions:
        if dry_run:
            snapshot.actions.append(f"would run {action.key} ({action.reason})")
            continue
        snapshot.actions.append(execute(action, settings))
        state.last_action_at[action.key] = now
        if action.key == LLAMA_RESTART_KEY:
            state.last_daily_restart_day = local_now.date().isoformat()  # any restart today is the day's refresh
    state.llama_busy_slots = [] if LLAMA_RESTART_KEY in {action.key for action in actions} else busy  # a restarted server starts its task count over
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
