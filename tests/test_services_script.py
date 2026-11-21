"""scripts/services.sh status, start, restart and engine, run for real against stand-ins for launchctl, lsof, pgrep, pkill and the serving CLI, so
no launchd agent or process is touched. The stand-ins read which agents are loaded, which ports listen, which agents launchd refuses, whether
Strata's engine runs and whether `serving check` passes from environment variables, and log what they were asked to do."""

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

SERVICES_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "services.sh"
SERVICES = ("llama", "mcp", "harness", "dashboard", "speech", "voice", "health", "listings", "newsletters")
FAKE_LAUNCHCTL = """#!/bin/bash
# print TARGET | bootout TARGET | kickstart -k TARGET | bootstrap DOMAIN PLIST; the agent's name is the last dot-separated part of the label.
label="${@: -1}"
name="$(basename "$label" .plist)"
name="${name##*.}"
echo "$1 $name" >>"$HOME/calls.log"
case "$1" in
print) [[ -n "$STILL_UNLOADING" || (" $NOT_LOADED " != *" $name "* && ! -f "$HOME/unloaded.$name") ]] ;;
bootout) touch "$HOME/unloaded.$name" ;;
kickstart | bootstrap)
    [[ " $REFUSED " != *" $name "* ]] || { echo "Bootstrap failed: 5: Input/output error" >&2; exit 5; }
    rm -f "$HOME/unloaded.$name"
    ;;
esac
"""
FAKE_PGREP = """#!/bin/bash
# pgrep -x NAME: Strata's engine runs while ENGINE_RUNNING is set, until pkill stops it
[[ -n "$ENGINE_RUNNING" && ! -f "$HOME/engine_killed" ]]
"""
FAKE_PKILL = """#!/bin/bash
echo "pkill $*" >>"$HOME/calls.log"
touch "$HOME/engine_killed"
"""
FAKE_SERVING = """#!/bin/bash
# serving engine names the override, or serving.toml's engine from DEFAULT_ENGINE; serving check logs which engine it saw and fails on CHECK_FAILS
if [[ "$1" == engine ]]; then cat "$HOME/Library/Application Support/studio-assistant/engine" 2>/dev/null || echo "${DEFAULT_ENGINE:-llama-server}"; exit; fi
echo "serving $1 sees $(cat "$HOME/Library/Application Support/studio-assistant/engine" 2>/dev/null || echo default)" >>"$HOME/calls.log"
[[ -z "$CHECK_FAILS" ]]
"""
FAKE_VOICE = """#!/bin/bash
# voice port prints 10210; voice check logs which voice it saw and fails on VOICE_CHECK_FAILS; voice handoff is logged
override="$HOME/Library/Application Support/studio-assistant/voice_engine"
case "$1" in
port) echo 10210 ;;
check) echo "voice check sees $(cat "$override" 2>/dev/null || echo default)" >>"$HOME/calls.log"; [[ -z "$VOICE_CHECK_FAILS" ]] ;;
handoff) echo "voice handoff" >>"$HOME/calls.log" ;;
esac
"""
FAKE_STRATA_SCRIPT = """#!/bin/bash
echo "strata.sh $1" >>"$HOME/calls.log"
[[ -z "$ENSURE_FAILS" ]]
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
    for name, body in (
        ("launchctl", FAKE_LAUNCHCTL),
        ("lsof", FAKE_LSOF),
        ("pgrep", FAKE_PGREP),
        ("pkill", FAKE_PKILL),
        ("serving", FAKE_SERVING),
        ("strata.sh", FAKE_STRATA_SCRIPT),
        ("voice", FAKE_VOICE),
    ):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod((bin_dir / name).stat().st_mode | stat.S_IEXEC)
    agents = tmp_path / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    for name in SERVICES:
        (agents / f"com.studio-assistant.{name}.plist").write_text("<plist/>")
    logs = tmp_path / "Library" / "Logs" / "studio-assistant"
    logs.mkdir(parents=True)
    environment = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(tmp_path), "STUDIO_LOG_DIR": str(logs), "NOT_LOADED": "", "DOWN_PORTS": "", "REFUSED": ""}
    return environment | {
        "SERVING_CLI": str(bin_dir / "serving"),
        "VOICE_CLI": str(bin_dir / "voice"),
        "VOICE_CHECK_FAILS": "",
        "STRATA_SCRIPT": str(bin_dir / "strata.sh"),
        "ENSURE_FAILS": "",
        "DEFAULT_ENGINE": "",
        "ENGINE_RUNNING": "",
        "CHECK_FAILS": "",
        "ENGINE_EXIT_TIMEOUT_SECONDS": "1",
        "UNLOAD_TIMEOUT_SECONDS": "1",
        "STILL_UNLOADING": "",
    }


def services(command: str, environment: dict[str, str], *arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(SERVICES_SCRIPT), command, *arguments], env=environment, capture_output=True, text=True, timeout=60)


def calls(environment: dict[str, str]) -> list[str]:
    log = Path(environment["HOME"]) / "calls.log"
    return [line for line in log.read_text().splitlines() if not line.startswith("print ")] if log.exists() else []


def engine_override(environment: dict[str, str]) -> Path:
    return Path(environment["HOME"]) / "Library" / "Application Support" / "studio-assistant" / "engine"


def test_status_passes_only_when_every_agent_is_loaded_and_every_port_listens(mac: dict[str, str]) -> None:
    assert services("status", mac).returncode == 0

    loading = services("status", mac | {"DOWN_PORTS": "8090"})
    assert (loading.returncode, "llama: NOT listening on 8090" in loading.stdout) == (1, True)

    unloaded = services("status", mac | {"NOT_LOADED": "speech"})
    assert (unloaded.returncode, "speech: agent NOT loaded" in unloaded.stdout) == (1, True)


def write_failing_snapshot(environment: dict[str, str]) -> None:
    """What the health agent records at load, while the agents beside it are still starting."""
    checks = {name: {"ok": False, "detail": "connection refused"} for name in ("llama", "mcp", "harness", "speech", "voice")}
    (Path(environment["STUDIO_LOG_DIR"]) / "health.json").write_text(json.dumps({"checked_at": "2026-11-15T01:00:00", "checks": checks}))


def test_status_shows_a_failing_health_snapshot_without_failing_on_it(mac: dict[str, str]) -> None:
    write_failing_snapshot(mac)

    shown = services("status", mac)

    assert (shown.returncode, "FAILING harness, llama, mcp, speech, voice" in shown.stdout) == (0, True)


def test_starting_the_agents_shows_what_is_still_loading_and_fails_only_when_launchd_refuses_one(mac: dict[str, str]) -> None:
    write_failing_snapshot(mac)  # the 2026-11-15 deploy: every agent loaded, and this snapshot failed the install
    still_loading = services("start", mac | {"DOWN_PORTS": "8090 10300 10210"})
    assert (still_loading.returncode, "speech: NOT listening on 10300" in still_loading.stdout) == (0, True)

    refused = services("start", mac | {"REFUSED": "voice"})
    assert refused.returncode == 1
    assert "failed to load: voice (Bootstrap failed: 5: Input/output error)" in refused.stderr


def test_restarting_the_engine_stops_its_agent_and_waits_for_strata_to_exit_before_loading_it_again(mac: dict[str, str]) -> None:
    restarted = services("restart", mac | {"ENGINE_RUNNING": "1"}, "llama")

    assert restarted.returncode == 0
    assert calls(mac) == ["bootout llama", "pkill -9 -x strata", "bootstrap llama"]  # the engine outlived the 1 s allowed, so it was stopped first
    assert "still runs 1 s after its server stopped" in restarted.stderr


def test_switching_the_engine_checks_the_choice_then_restarts_the_engine_and_the_harness(mac: dict[str, str]) -> None:
    switched = services("engine", mac, "llama-server")

    assert switched.returncode == 0
    assert engine_override(mac).read_text().strip() == "llama-server"
    assert calls(mac) == ["serving check sees llama-server", "bootout llama", "bootstrap llama", "kickstart harness"]

    services("engine", mac, "default")
    assert not engine_override(mac).exists()


def test_a_switch_the_check_refuses_is_undone_and_nothing_restarts(mac: dict[str, str]) -> None:
    services("engine", mac, "llama-server")
    (Path(mac["HOME"]) / "calls.log").unlink()

    refused = services("engine", mac | {"CHECK_FAILS": "1"}, "strata")

    assert (refused.returncode, engine_override(mac).read_text().strip()) == (1, "llama-server")
    assert calls(mac) == ["strata.sh ensure", "serving check sees strata"]


def test_an_engine_agent_slow_to_unload_is_still_loaded_again_so_a_health_check_restart_never_leaves_it_down(mac: dict[str, str]) -> None:
    restarted = services("restart", mac | {"STILL_UNLOADING": "1"}, "llama")
    assert calls(mac) == ["bootout llama", "bootstrap llama"]
    assert "llama still unloading after 1 s" in restarted.stderr


def test_under_strata_an_engine_restart_first_brings_strata_to_the_checkouts_pin_while_the_old_engine_still_runs(mac: dict[str, str]) -> None:
    restarted = services("restart", mac | {"DEFAULT_ENGINE": "strata"}, "llama")
    assert (restarted.returncode, calls(mac)) == (0, ["strata.sh ensure", "bootout llama", "bootstrap llama"])


def test_a_strata_install_that_fails_leaves_the_running_engine_alone(mac: dict[str, str]) -> None:
    restarted = services("restart", mac | {"DEFAULT_ENGINE": "strata", "ENSURE_FAILS": "1"}, "llama")
    assert (restarted.returncode, calls(mac)) == (1, ["strata.sh ensure"])
    assert "the running engine was left alone" in restarted.stderr


def voice_override(environment: dict[str, str]) -> Path:
    return Path(environment["HOME"]) / "Library" / "Application Support" / "studio-assistant" / "voice_engine"


def test_switching_the_voice_checks_the_choice_restarts_the_voice_and_tells_home_assistant(mac: dict[str, str]) -> None:
    switched = services("voice-engine", mac, "omnivoice")

    assert switched.returncode == 0
    assert voice_override(mac).read_text().strip() == "omnivoice"
    assert calls(mac) == ["voice check sees omnivoice", "kickstart voice", "voice handoff"]

    services("voice-engine", mac, "default")
    assert not voice_override(mac).exists()


def test_a_voice_switch_the_check_refuses_is_undone_and_nothing_restarts(mac: dict[str, str]) -> None:
    services("voice-engine", mac, "kokoro")
    (Path(mac["HOME"]) / "calls.log").unlink()

    refused = services("voice-engine", mac | {"VOICE_CHECK_FAILS": "1"}, "omnivoice")

    assert (refused.returncode, voice_override(mac).read_text().strip()) == (1, "kokoro")
    assert calls(mac) == ["voice check sees omnivoice"]
    assert services("voice-engine", mac, "piper").returncode == 1


def test_status_reads_the_voices_port_from_its_settings(mac: dict[str, str]) -> None:
    assert "voice: listening on 10210" in services("status", mac).stdout
