"""The health policy is a pure function; these tests pin the thresholds and cooldowns from design doc 10 §3.5 and the housekeeping from §3.6."""

import json
from datetime import date

from ops import health, paths
from ops.health import Action, Check, Policy, State

OK = Check(ok=True)
DOWN = Check(ok=False, detail="refused")
VM_UP = Check(ok=True, detail="started")
VM_DOWN = Check(ok=False, detail="stopped")
NOW = 1_000_000.0


def healthy_checks() -> dict[str, Check]:
    return {name: OK for name in ("ollama", "mcp", "whisper", "kokoro", "searxng", "home_assistant")} | {"vm": VM_UP}


def after_failures(checks: dict[str, Check], runs: int, state: State | None = None) -> State:
    state = state or State()
    for _ in range(runs):
        state = health.update_failure_counts(state, checks)
    return state


def keys(actions: list[Action]) -> list[str]:
    return [action.key for action in actions]


def test_healthy_machine_needs_nothing() -> None:
    state = after_failures(healthy_checks(), 3)
    assert health.decide_actions(healthy_checks(), state, Policy(), NOW, maintenance=False) == []


def test_agent_is_kicked_only_after_two_consecutive_failures() -> None:
    checks = healthy_checks() | {"mcp": DOWN}
    assert health.decide_actions(checks, after_failures(checks, 1), Policy(), NOW, maintenance=False) == []
    assert keys(health.decide_actions(checks, after_failures(checks, 2), Policy(), NOW, maintenance=False)) == ["kickstart:mcp"]


def test_a_recovery_resets_the_count() -> None:
    checks = healthy_checks() | {"mcp": DOWN}
    state = after_failures(healthy_checks(), 1, after_failures(checks, 1))
    assert state.consecutive_failures["mcp"] == 0


def test_kickstart_respects_the_cooldown() -> None:
    checks = healthy_checks() | {"whisper": DOWN}
    state = after_failures(checks, 5)
    state.last_action_at["kickstart:whisper"] = NOW - 10 * 60
    assert health.decide_actions(checks, state, Policy(), NOW, maintenance=False) == []
    state.last_action_at["kickstart:whisper"] = NOW - 31 * 60
    assert keys(health.decide_actions(checks, state, Policy(), NOW, maintenance=False)) == ["kickstart:whisper"]


def test_unloaded_agent_is_skipped_not_failed() -> None:
    checks = healthy_checks() | {"kokoro": Check(ok=None, detail="not loaded")}
    state = after_failures(checks, 4)
    assert state.consecutive_failures["kokoro"] == 0
    assert health.decide_actions(checks, state, Policy(), NOW, maintenance=False) == []


def test_searxng_comes_back_after_two_failures() -> None:
    checks = healthy_checks() | {"searxng": DOWN}
    assert keys(health.decide_actions(checks, after_failures(checks, 2), Policy(), NOW, maintenance=False)) == ["searxng_up:searxng"]


def test_stopped_vm_is_started_at_once_and_ha_failures_do_not_restart_it() -> None:
    checks = healthy_checks() | {"vm": VM_DOWN, "home_assistant": DOWN}
    assert keys(health.decide_actions(checks, after_failures(checks, 1), Policy(), NOW, maintenance=False)) == ["vm_start:vm"]
    assert keys(health.decide_actions(checks, after_failures(checks, 9), Policy(), NOW, maintenance=False)) == ["vm_start:vm"]


def test_ha_down_while_vm_runs_restarts_the_vm_after_five_checks() -> None:
    checks = healthy_checks() | {"home_assistant": DOWN}
    assert health.decide_actions(checks, after_failures(checks, 4), Policy(), NOW, maintenance=False) == []
    actions = health.decide_actions(checks, after_failures(checks, 5), Policy(), NOW, maintenance=False)
    assert keys(actions) == ["vm_restart:vm"]
    state = after_failures(checks, 6)
    state.last_action_at["vm_restart:vm"] = NOW - 60 * 60
    assert health.decide_actions(checks, state, Policy(), NOW, maintenance=False) == []


def test_maintenance_flag_suspends_every_action() -> None:
    checks = {name: DOWN for name in healthy_checks()} | {"vm": VM_DOWN}
    assert health.decide_actions(checks, after_failures(checks, 10), Policy(), NOW, maintenance=True) == []


def test_parsers_read_macos_output() -> None:
    assert health.parse_memory_pressure("The system has 2048 pages free\nSystem-wide memory free percentage: 14%\n") == 14
    assert health.parse_swapusage("total = 13312.00M  used = 11628.25M  free = 1683.75M  (encrypted)") == 11628.25
    assert health.parse_swapusage("total = 2.00G  used = 1.50G  free = 0.50G") == 1536.0
    assert health.parse_vm_status(0, "stopped\n", "") == Check(ok=False, detail="stopped")
    assert health.parse_vm_status(0, "started\n", "").ok is True
    assert health.parse_vm_status(1, "", "no such vm").ok is None


def test_rotate_log_copy_truncates_and_keeps_three_generations(tmp_path) -> None:
    log = tmp_path / "ollama.log"
    log.write_text("small")
    assert health.rotate_log(log, over_bytes=100) is False
    for generation in ("first", "second", "third", "fourth"):
        log.write_text(generation * 50)
        assert health.rotate_log(log, over_bytes=100) is True
    assert log.read_text() == ""
    assert (tmp_path / "ollama.log.1").read_text().startswith("fourth")
    assert (tmp_path / "ollama.log.2").read_text().startswith("third")
    assert (tmp_path / "ollama.log.3").read_text().startswith("second")
    assert not (tmp_path / "ollama.log.4").exists()


def test_prune_history_drops_old_snapshots(tmp_path) -> None:
    path = tmp_path / "health.jsonl"
    lines = [json.dumps({"checked_at": day}) for day in ("2026-05-01T00:00:00+00:00", "2026-06-01T00:00:00+00:00", "2026-09-07T00:00:00+00:00")]
    path.write_text("\n".join(lines) + "\n")
    assert health.prune_history(path, retention_days=90, today=date(2026, 9, 7)) == 2
    assert path.read_text().count("\n") == 1


def test_housekeeping_touches_every_file_under_the_log_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STUDIO_LOG_DIR", str(tmp_path))
    paths.turns_dir().mkdir()
    (paths.turns_dir() / "2025-01-01.jsonl").write_text("{}\n")
    (paths.turns_dir() / "2026-09-01.jsonl").write_text("{}\n")
    paths.service_log("mcp").write_bytes(b"x" * (health.ROTATE_OVER_BYTES + 1))
    notes = health.housekeeping(today=date(2026, 9, 7))
    assert notes == ["rotated mcp.log", "deleted 2025-01-01.jsonl"]
    assert (paths.turns_dir() / "2026-09-01.jsonl").exists()
