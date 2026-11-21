"""The deploy rules table from design doc 10 §3.8 and the manifest-versus-lock preflight from doc 09 §4."""

import ast
import json
import os
import subprocess
from pathlib import Path

import pytest

from ops import deploy, paths
from ops.paths import VENDORED_CORE_FILES


def actions(*paths: str) -> list[str]:
    return deploy.plan_actions(paths).actions


def test_docs_tests_and_ops_change_nothing() -> None:
    assert actions("design_docs/v1/10_operations.md", "tests/test_health.py", "ops/health.py", "benchmark/config.yaml", "README.md") == []


def test_tool_server_code_restarts_only_the_tool_server() -> None:
    assert actions("assistant_mcp/server.py") == ["restart:mcp"]
    assert actions("calculator_mcp/tools.py") == ["restart:mcp"]
    assert actions("weather_mcp/forecast.py") == ["restart:mcp"]
    assert actions("broadway_mcp/shows.py") == ["restart:mcp"]


def test_shared_utilities_restart_every_service_that_imports_them() -> None:
    assert actions("utils/jsonl_utils.py") == ["restart:mcp", "restart:harness", "restart:dashboard"]


def test_shared_core_restarts_the_harness_and_redeploys_the_component_only_for_vendored_files() -> None:
    assert actions("assistant_core/prompts.py") == ["restart:mcp", "restart:harness", "restart:dashboard", "deploy_component"]
    assert actions("assistant_core/agent_loop.py") == ["restart:mcp", "restart:harness", "restart:dashboard"]


def test_harness_settings_restart_only_the_harness_and_its_code_also_the_dashboard_that_imports_it() -> None:
    assert actions("config/harness.toml") == ["restart:harness"]
    assert actions("assistant_service/app.py") == ["restart:harness", "restart:dashboard"]


def test_the_tools_the_harness_may_call_restart_the_harness() -> None:
    assert actions("config/tools.toml") == ["restart:harness"]


def test_dashboard_code_restarts_only_the_dashboard() -> None:
    assert actions("dashboard/app.py", "dashboard/static/app.js") == ["restart:dashboard"]
    assert actions("ops/paths.py") == ["restart:dashboard"]


def test_component_only_change_redeploys_the_component() -> None:
    assert actions("custom_components/studio_assistant/conversation.py") == ["deploy_component"]


def test_a_lock_change_only_syncs_until_the_sync_shows_which_environments_changed() -> None:
    assert actions("uv.lock") == ["sync_env"]
    assert actions("pyproject.toml", "voice/kokoro_server.py") == ["sync_env", "restart:kokoro"]


def test_after_the_sync_only_the_services_of_a_changed_environment_restart() -> None:
    project, speech = deploy.ENVIRONMENTS
    plan = deploy.plan_actions(["uv.lock"])

    assert deploy.plan_after_sync(plan, []).actions == ["sync_env"]
    assert deploy.plan_after_sync(plan, [speech]).actions == ["sync_env", "restart:speech"]
    assert deploy.plan_after_sync(plan, [project]).actions == ["sync_env", "restart:mcp", "restart:harness", "restart:dashboard", "restart:kokoro"]
    assert deploy.plan_after_sync(plan, [speech]).reasons["restart:speech"] == ".venv-speech: the sync changed its installed packages"
    assert deploy.plan_after_sync(deploy.plan_actions(["uv.lock", "scripts/services.sh"]), [project, speech]).actions == ["sync_env", "reinstall_agents"]


def test_an_environment_counts_as_changed_when_its_installed_packages_differ() -> None:
    before = {".venv": frozenset({"httpx-0.28.1.dist-info"}), ".venv-speech": frozenset({"mlx_audio-0.6.5.dist-info"})}
    after = {".venv": frozenset({"httpx-0.28.1.dist-info"}), ".venv-speech": frozenset({"mlx_audio-0.6.6.dist-info"})}

    assert [environment.folder for environment in deploy.environments_changed(before, after)] == [".venv-speech"]
    assert deploy.environments_changed(before, before) == []


def test_a_speech_server_change_restarts_only_the_speech_server() -> None:
    assert actions("speech_server/handlers.py") == ["restart:speech"]
    assert actions("config/speech.toml") == ["restart:speech"]


def test_services_script_change_reinstalls_agents_instead_of_individual_restarts() -> None:
    assert actions("scripts/services.sh", "assistant_mcp/server.py", "voice/kokoro_server.py", "speech_server/models.py") == ["reinstall_agents"]
    assert actions("scripts/services.sh", "uv.lock") == ["sync_env", "reinstall_agents"]


def test_searxng_config_restarts_the_container_and_component_deploy_runs_last() -> None:
    assert actions("docker/searxng/settings.yml", "custom_components/studio_assistant/adapter.py", "web_search_mcp/settings.py") == ["restart:mcp", "restart_searxng", "deploy_component"]


def test_plan_records_why_each_action_was_chosen() -> None:
    plan = deploy.plan_actions(["assistant_core/models.py", "assistant_mcp/server.py"])
    assert plan.reasons["restart:mcp"].startswith("assistant_core/models.py")
    assert "component" in plan.reasons["deploy_component"]
    assert plan.changed == ["assistant_core/models.py", "assistant_mcp/server.py"]


LOCK = """
[[package]]
name = "ollama"
version = "0.6.2"

[[package]]
name = "pydantic"
version = "2.13.5"
"""


def manifest(*requirements: str) -> str:
    return json.dumps({"domain": "studio_assistant", "requirements": list(requirements)})


def test_manifest_matching_the_lock_passes() -> None:
    assert deploy.manifest_lock_mismatches(manifest("ollama==0.6.2", "pydantic>=2.0"), LOCK) == []


def test_manifest_pin_that_drifted_from_the_lock_is_reported() -> None:
    problems = deploy.manifest_lock_mismatches(manifest("ollama==0.5.1", "pydantic>=3.0", "httpx>=0.27"), LOCK)
    assert problems == ["ollama==0.5.1: uv.lock has 0.6.2", "pydantic>=3.0: uv.lock has 2.13.5", "httpx>=0.27: not in uv.lock"]


def test_the_real_manifest_matches_the_real_lock() -> None:
    assert deploy.manifest_lock_mismatches(deploy.MANIFEST.read_text(), deploy.LOCK.read_text()) == []


def test_cli_status_reports_head_and_flags(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("STUDIO_LOG_DIR", str(tmp_path))
    assert deploy.main(["status"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert len(report["head"]) == 40
    assert report["maintenance"] is False and report["last_good_ref"] is None


def test_serving_settings_launcher_or_strata_patches_restart_the_engine() -> None:
    assert deploy.plan_actions(["config/serving.toml"]).actions == ["restart:llama", "restart:harness"]
    assert deploy.plan_actions(["serving/command.py"]).actions == ["restart:llama", "restart:harness"]
    assert deploy.plan_actions(["scripts/strata_patches/release_projections.patch"]).actions == ["restart:llama", "restart:harness"]


class EngineDeploy:
    """A deploy of a serving.toml change with git, the steps and the restarts faked: records checkouts, the commands run, and the restarts. The
    step named in `failing` exits 1, or runs out of time when the name ends in " (hangs)"."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, engine: str, failing: str = "") -> None:
        monkeypatch.setenv("STUDIO_LOG_DIR", str(tmp_path))
        self.checkouts: list[str] = []
        self.ran: list[str] = []
        self.restarted: list[str] = []
        self.failing = failing
        monkeypatch.setattr(deploy, "tree_is_dirty", lambda: False)
        monkeypatch.setattr(deploy, "git", self.git)
        monkeypatch.setattr(deploy, "run", self.run)
        monkeypatch.setattr(deploy, "check_manifest_matches_lock", lambda: None)
        monkeypatch.setattr(deploy, "carry_out", self.restarted.extend)
        monkeypatch.setattr(deploy, "active_engine_here", lambda: engine)

    def git(self, *args: str) -> str:
        if args[0] == "checkout":
            self.checkouts.append(args[-1])
        answers = {("rev-parse", "HEAD"): "old", ("rev-parse", "--verify", "new^{commit}"): "new", ("diff", "--name-only", "old", "new"): "config/serving.toml"}
        return answers.get(args, "")

    def run(self, command: list[str], timeout: int = 0) -> None:
        step = "tests" if "pytest" in command else f"{Path(command[0]).name} {command[-1]}@{self.checkouts[-1]}"
        self.ran.append(step)
        if step == self.failing:
            raise subprocess.CalledProcessError(1, command)
        if f"{step} (hangs)" == self.failing:
            raise subprocess.TimeoutExpired(command, timeout)


def test_an_engine_the_launch_would_refuse_aborts_the_deploy_before_any_restart(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    deploying = EngineDeploy(monkeypatch, tmp_path, engine="llama-server", failing="serving check@new")

    summary = deploy.switch_to("new", run_tests=True, dry_run=False)

    assert summary["note"].startswith("aborted before any restart; checkout returned to old")
    assert (deploying.checkouts, deploying.ran, deploying.restarted) == (["new", "old"], ["tests", "serving check@new"], [])
    assert "strata" not in summary  # under llama-server the deploy never touches Strata


def test_under_strata_the_deployed_commits_strata_sh_brings_strata_to_its_pin_before_the_check(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    deploying = EngineDeploy(monkeypatch, tmp_path, engine="strata")

    summary = deploy.switch_to("new", run_tests=False, dry_run=False)

    assert deploying.ran == ["strata.sh ensure@new", "serving check@new"]
    assert summary["applied"] and deploying.restarted == ["restart:llama", "restart:harness"]


def test_a_strata_install_that_fails_aborts_and_the_old_commits_strata_sh_puts_strata_back(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    deploying = EngineDeploy(monkeypatch, tmp_path, engine="strata", failing="strata.sh ensure@new")
    monkeypatch.setattr(deploy, "STRATA_SCRIPT", tmp_path / "strata.sh")
    (tmp_path / "strata.sh").write_text("")

    summary = deploy.switch_to("new", run_tests=False, dry_run=False)

    assert deploying.ran == ["strata.sh ensure@new", "strata.sh ensure@old"]
    assert (summary["strata"], deploying.restarted) == ("matches the old pin", [])


def test_a_strata_install_that_runs_out_of_time_aborts_like_one_that_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    deploying = EngineDeploy(monkeypatch, tmp_path, engine="strata", failing="strata.sh ensure@new (hangs)")

    summary = deploy.switch_to("new", run_tests=False, dry_run=False)

    assert summary["note"].startswith("aborted before any restart") and deploying.restarted == []


def test_an_old_commit_from_before_strata_has_nothing_to_put_back(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    EngineDeploy(monkeypatch, tmp_path, engine="strata", failing="serving check@new")
    monkeypatch.setattr(deploy, "STRATA_SCRIPT", tmp_path / "no-strata.sh")

    summary = deploy.switch_to("new", run_tests=False, dry_run=False)

    assert summary["strata"] == "the old commit has no scripts/strata.sh; nothing to put back"


class PulledCheckout:
    """The Studio on 2026-11-20: 3761220 deployed, then `git pull` moved the checkout to the target without restarting anything."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failing: str = "") -> None:
        monkeypatch.setenv("STUDIO_LOG_DIR", str(tmp_path))
        (tmp_path / "last_good_ref").write_text("deployed\n")
        self.checkouts: list[str] = []
        self.restarted: list[str] = []
        self.failing = failing
        monkeypatch.setattr(deploy, "tree_is_dirty", lambda: False)
        monkeypatch.setattr(deploy, "git", self.git)
        monkeypatch.setattr(deploy, "run", self.run)
        monkeypatch.setattr(deploy, "check_manifest_matches_lock", lambda: None)
        monkeypatch.setattr(deploy, "carry_out", self.restarted.extend)
        monkeypatch.setattr(deploy, "active_engine_here", lambda: "llama-server")

    def git(self, *args: str) -> str:
        if args[0] == "checkout":
            self.checkouts.append(args[-1])
        answers = {("rev-parse", "HEAD"): "new", ("rev-parse", "--verify", "new^{commit}"): "new", ("diff", "--name-only", "deployed", "new"): "config/serving.toml"}
        return answers.get(args, "")

    def run(self, command: list[str], timeout: int = 0) -> None:
        if command[-1] == self.failing:
            raise subprocess.CalledProcessError(1, command)


def test_a_checkout_pulled_to_the_target_still_gets_the_restarts_since_the_last_deploy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pulled = PulledCheckout(monkeypatch, tmp_path)

    summary = deploy.switch_to("new", run_tests=False, dry_run=False)

    assert (summary["from"], summary["applied"]) == ("deployed", True)
    assert pulled.restarted == ["restart:llama", "restart:harness"]
    assert summary["checkout_moved"] == "the checkout was at new, but deployed is what was last deployed; planned from deployed"


def test_an_abort_after_a_pull_returns_the_checkout_to_what_is_running(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pulled = PulledCheckout(monkeypatch, tmp_path, failing="check")

    summary = deploy.switch_to("new", run_tests=False, dry_run=False)

    assert (pulled.checkouts, pulled.restarted) == (["new", "deployed"], [])
    assert "checkout returned to deployed, the deployed commit" in summary["note"]


def test_only_a_checkout_at_the_deployed_target_has_nothing_to_do(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    PulledCheckout(monkeypatch, tmp_path)
    (tmp_path / "last_good_ref").write_text("new\n")

    summary = deploy.switch_to("new", run_tests=False, dry_run=False)

    assert (summary["note"], "checkout_moved" in summary) == ("already at this commit", False)


def test_vendored_core_files_import_only_each_other() -> None:
    vendored_modules = {Path(relative_path).with_suffix("").as_posix().replace("/", ".") for relative_path in VENDORED_CORE_FILES}
    vendored_modules.add("assistant_core")
    for relative_path in VENDORED_CORE_FILES:
        tree = ast.parse((deploy.PROJECT_DIR / relative_path).read_text())
        imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
        assert {module for module in imported if module.startswith("assistant_core")} <= vendored_modules, relative_path


def test_one_failed_step_does_not_stop_the_steps_after_it(monkeypatch: pytest.MonkeyPatch) -> None:
    executed = []

    def execute(action: str) -> None:
        executed.append(action)
        if action == "reinstall_agents":
            raise subprocess.CalledProcessError(1, ["scripts/services.sh", "install"])

    monkeypatch.setattr(deploy, "execute", execute)

    assert deploy.carry_out(["reinstall_agents", "restart_searxng", "deploy_component"]) == ["reinstall_agents exited 1"]
    assert executed == ["reinstall_agents", "restart_searxng", "deploy_component"]


def test_a_rollback_retires_the_agents_its_older_services_script_does_not_list(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    agents = tmp_path / "LaunchAgents"
    agents.mkdir()
    for name in ("llama", "whisper", "speech"):
        (agents / f"com.studio-assistant.{name}.plist").write_text("<plist/>")
    older_services_script = tmp_path / "services.sh"
    older_services_script.write_text("#!/usr/bin/env bash\nSERVICES=(llama mcp whisper kokoro)\nRETIRED_SERVICES=(ollama)\n")
    booted_out = []
    monkeypatch.setattr(paths, "LAUNCH_AGENTS_DIR", agents)
    monkeypatch.setattr(deploy, "SERVICES_SCRIPT", older_services_script)

    def launchctl(command: list[str], **_: object) -> subprocess.CompletedProcess:
        if command[1] == "bootout":
            booted_out.append(command[-1])
        return subprocess.CompletedProcess(command, 113)  # `launchctl print` of a job that is gone

    monkeypatch.setattr(deploy.subprocess, "run", launchctl)

    deploy.retire_agents_the_checkout_does_not_list()

    assert booted_out == [f"gui/{os.getuid()}/com.studio-assistant.speech"]
    assert sorted(path.name for path in agents.iterdir()) == ["com.studio-assistant.llama.plist", "com.studio-assistant.whisper.plist"]


def test_a_services_script_without_its_list_is_refused_rather_than_guessed() -> None:
    assert deploy.services_listed_in("SERVICES=(llama mcp)\n") == {"llama", "mcp"}
    with pytest.raises(SystemExit, match="no SERVICES"):
        deploy.services_listed_in("#!/usr/bin/env bash\n")


class DeployThenRollBack:
    """last_good is the running commit; a deploy of `failed` changes config/serving.toml, then its test question fails and the rollback switches
    back to last_good. git answers from a checkout that moves with each checkout; the restarts are recorded per switch."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("STUDIO_LOG_DIR", str(tmp_path))
        (tmp_path / "last_good_ref").write_text("good\n")
        self.head = "good"
        self.restarts: list[list[str]] = []
        monkeypatch.setattr(deploy, "tree_is_dirty", lambda: False)
        monkeypatch.setattr(deploy, "git", self.git)
        monkeypatch.setattr(deploy, "run", lambda command, timeout=0: None)
        monkeypatch.setattr(deploy, "check_manifest_matches_lock", lambda: None)
        monkeypatch.setattr(deploy, "carry_out", lambda actions: self.restarts.append(actions) or [])
        monkeypatch.setattr(deploy, "active_engine_here", lambda: "llama-server")

    def git(self, *args: str) -> str:
        if args[0] == "checkout":
            self.head = args[-1]
        if args[:2] == ("rev-parse", "HEAD"):
            return self.head
        if args[:2] == ("rev-parse", "--verify"):
            return args[-1].removesuffix("^{commit}")
        if args[:2] == ("diff", "--name-only"):
            return "" if args[2] == args[3] else "config/serving.toml"
        return ""


def test_a_rollback_after_a_failed_test_question_restarts_what_the_failed_deploy_restarted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mac = DeployThenRollBack(monkeypatch, tmp_path)

    forward = deploy.switch_to("failed", run_tests=False, dry_run=False)
    back = deploy.switch_to(paths.last_good_ref().read_text().strip(), run_tests=False, dry_run=False)

    assert (forward["from"], forward["to"], back["from"], back["to"]) == ("good", "failed", "failed", "good")
    assert mac.restarts == [["restart:llama", "restart:harness"], ["restart:llama", "restart:harness"]]
    assert (mac.head, paths.applied_ref().read_text().strip()) == ("good", "good")


def test_a_mac_deployed_before_the_applied_commit_was_recorded_plans_from_its_last_good_commit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STUDIO_LOG_DIR", str(tmp_path))
    assert deploy.deployed_commit("checkout") == "checkout"
    (tmp_path / "last_good_ref").write_text("good\n")
    assert deploy.deployed_commit("checkout") == "good"
    (tmp_path / "applied_ref").write_text("applied\n")
    assert deploy.deployed_commit("checkout") == "applied"


def test_retiring_an_agent_waits_until_launchd_has_let_it_go(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    agents = tmp_path / "LaunchAgents"
    agents.mkdir()
    (agents / "com.studio-assistant.voice.plist").write_text("<plist/>")
    services_script = tmp_path / "services.sh"
    services_script.write_text("SERVICES=(llama kokoro)\n")
    still_loaded_for = iter([True, True, False])
    commands: list[str] = []

    def launchctl(command: list[str], **_: object) -> subprocess.CompletedProcess:
        commands.append(command[1])
        loaded = command[1] == "print" and next(still_loaded_for)
        return subprocess.CompletedProcess(command, 0 if loaded else 113)

    monkeypatch.setattr(paths, "LAUNCH_AGENTS_DIR", agents)
    monkeypatch.setattr(deploy, "SERVICES_SCRIPT", services_script)
    monkeypatch.setattr(deploy.subprocess, "run", launchctl)
    monkeypatch.setattr(deploy.time, "sleep", lambda seconds: None)

    deploy.retire_agents_the_checkout_does_not_list()

    assert commands == ["bootout", "print", "print", "print"]
    assert list(agents.iterdir()) == []
