"""The deploy rules table from design doc 10 §3.8 and the manifest-versus-lock preflight from doc 09 §4."""

import ast
import json
from pathlib import Path

import pytest

from ops import deploy
from ops.paths import VENDORED_CORE_FILES


def actions(*paths: str) -> list[str]:
    return deploy.plan_actions(paths).actions


def test_docs_tests_and_ops_change_nothing() -> None:
    assert actions("design_docs/v1/10_operations.md", "tests/test_health.py", "ops/health.py", "benchmark/config.yaml", "README.md") == []


def test_tool_server_code_restarts_only_the_tool_server() -> None:
    assert actions("web_search_mcp/server.py") == ["restart:mcp"]
    assert actions("calculator_mcp/tools.py") == ["restart:mcp"]
    assert actions("weather_mcp/forecast.py") == ["restart:mcp"]


def test_shared_utilities_restart_both_services_that_import_them() -> None:
    assert actions("utils/jsonl_utils.py") == ["restart:mcp", "restart:harness"]


def test_shared_core_restarts_the_harness_and_redeploys_the_component_only_for_vendored_files() -> None:
    assert actions("assistant_core/prompts.py") == ["restart:mcp", "restart:harness", "deploy_component"]
    assert actions("assistant_core/agent_loop.py") == ["restart:mcp", "restart:harness"]


def test_harness_code_or_settings_restart_only_the_harness() -> None:
    assert actions("assistant_service/app.py", "config/harness.toml") == ["restart:harness"]


def test_component_only_change_redeploys_the_component() -> None:
    assert actions("custom_components/studio_assistant/conversation.py") == ["deploy_component"]


def test_lock_change_syncs_first_and_restarts_every_python_service() -> None:
    assert actions("uv.lock") == ["sync_env", "restart:mcp", "restart:harness", "restart:kokoro", "restart:whisper"]
    assert actions("pyproject.toml", "voice/kokoro_server.py")[0] == "sync_env"


def test_services_script_change_reinstalls_agents_instead_of_individual_restarts() -> None:
    assert actions("scripts/services.sh", "web_search_mcp/server.py", "voice/kokoro_server.py") == ["reinstall_agents"]
    assert actions("scripts/services.sh", "uv.lock") == ["sync_env", "reinstall_agents"]


def test_searxng_config_restarts_the_container_and_component_deploy_runs_last() -> None:
    assert actions("docker/searxng/settings.yml", "custom_components/studio_assistant/adapter.py", "web_search_mcp/settings.py") == ["restart:mcp", "restart_searxng", "deploy_component"]


def test_plan_records_why_each_action_was_chosen() -> None:
    plan = deploy.plan_actions(["assistant_core/models.py", "web_search_mcp/server.py"])
    assert plan.reasons["restart:mcp"].startswith("assistant_core/models.py")
    assert "component" in plan.reasons["deploy_component"]
    assert plan.changed == ["assistant_core/models.py", "web_search_mcp/server.py"]


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


def test_serving_settings_or_launcher_restart_llama_server() -> None:
    assert deploy.plan_actions(["config/serving.toml"]).actions == ["restart:llama", "restart:harness"]
    assert deploy.plan_actions(["serving/command.py"]).actions == ["restart:llama", "restart:harness"]


def test_vendored_core_files_import_only_each_other() -> None:
    vendored_modules = {Path(relative_path).with_suffix("").as_posix().replace("/", ".") for relative_path in VENDORED_CORE_FILES}
    vendored_modules.add("assistant_core")
    for relative_path in VENDORED_CORE_FILES:
        tree = ast.parse((deploy.PROJECT_DIR / relative_path).read_text())
        imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
        assert {module for module in imported if module.startswith("assistant_core")} <= vendored_modules, relative_path
