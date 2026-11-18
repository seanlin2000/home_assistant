"""scripts/services.sh status and start, run for real against stand-ins for launchctl and lsof, so no launchd agent is touched. The stand-ins read
which agents are loaded, which ports listen, and which agents launchd refuses from environment variables."""

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

SERVICES_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "services.sh"
SERVICES = ("llama", "mcp", "harness", "dashboard", "speech", "kokoro", "health", "listings", "newsletters")
FAKE_LAUNCHCTL = """#!/bin/bash
# print TARGET | kickstart -k TARGET | bootstrap DOMAIN PLIST; the agent's name is the last dot-separated part of the label.
label="${@: -1}"
name="$(basename "$label" .plist)"
name="${name##*.}"
case "$1" in
print) [[ " $NOT_LOADED " != *" $name "* ]] ;;
kickstart | bootstrap) [[ " $REFUSED " != *" $name "* ]] || { echo "Bootstrap failed: 5: Input/output error" >&2; exit 5; } ;;
esac
"""
FAKE_LSOF = """#!/bin/bash
# lsof -nP -iTCP:PORT -sTCP:LISTEN
port="${2#-iTCP:}"
[[ " $DOWN_PORTS " != *" $port "* ]]
"""


@pytest.fixture
def mac(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("launchctl", FAKE_LAUNCHCTL), ("lsof", FAKE_LSOF)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod((bin_dir / name).stat().st_mode | stat.S_IEXEC)
    agents = tmp_path / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    for name in SERVICES:
        (agents / f"com.studio-assistant.{name}.plist").write_text("<plist/>")
    logs = tmp_path / "Library" / "Logs" / "studio-assistant"
    logs.mkdir(parents=True)
    return {"PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(tmp_path), "STUDIO_LOG_DIR": str(logs), "NOT_LOADED": "", "DOWN_PORTS": "", "REFUSED": ""}


def services(command: str, environment: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run([str(SERVICES_SCRIPT), command], env=environment, capture_output=True, text=True, timeout=60)


def test_status_passes_only_when_every_agent_is_loaded_and_every_port_listens(mac: dict[str, str]) -> None:
    assert services("status", mac).returncode == 0

    loading = services("status", mac | {"DOWN_PORTS": "8090"})
    assert (loading.returncode, "llama: NOT listening on 8090" in loading.stdout) == (1, True)

    unloaded = services("status", mac | {"NOT_LOADED": "speech"})
    assert (unloaded.returncode, "speech: agent NOT loaded" in unloaded.stdout) == (1, True)


def write_failing_snapshot(environment: dict[str, str]) -> None:
    """What the health agent records at load, while the agents beside it are still starting."""
    checks = {name: {"ok": False, "detail": "connection refused"} for name in ("llama", "mcp", "harness", "speech", "kokoro")}
    (Path(environment["STUDIO_LOG_DIR"]) / "health.json").write_text(json.dumps({"checked_at": "2026-11-15T01:00:00", "checks": checks}))


def test_status_shows_a_failing_health_snapshot_without_failing_on_it(mac: dict[str, str]) -> None:
    write_failing_snapshot(mac)

    shown = services("status", mac)

    assert (shown.returncode, "FAILING harness, kokoro, llama, mcp, speech" in shown.stdout) == (0, True)


def test_starting_the_agents_shows_what_is_still_loading_and_fails_only_when_launchd_refuses_one(mac: dict[str, str]) -> None:
    write_failing_snapshot(mac)  # the 2026-11-15 deploy: every agent loaded, and this snapshot failed the install
    still_loading = services("start", mac | {"DOWN_PORTS": "8090 10300 10210"})
    assert (still_loading.returncode, "speech: NOT listening on 10300" in still_loading.stdout) == (0, True)

    refused = services("start", mac | {"REFUSED": "kokoro"})
    assert refused.returncode == 1
    assert "failed to load: kokoro (Bootstrap failed: 5: Input/output error)" in refused.stderr
