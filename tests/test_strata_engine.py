"""Serving with Strata: the engine setting and its override, the run config built from serving.toml, the install check that holds Strata to its
pinned commit and our patches, and the launcher's dispatch (design doc v2/02 section 3.10). No test touches a real Strata install or ~/Library."""

import json
import os
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from serving import cli as serving_cli
from serving import settings as serving_settings
from serving import strata as strata_engine
from serving.model_file import file_sha256
from serving.settings import ServingConfig, StrataSettings, active_engine, load_serving_config
from serving.strata import git_environment, strata_install_problems, strata_run_config, write_strata_run_config

ORIGINAL_SOURCE = "int release_host_weights = 0;\n"
PATCHED_SOURCE = "int release_host_weights = 1;\n"
SETUP_ARGUMENTS = ["--pack", "/packs/iq3_xxs", "--suffix-draft", "0", "--max-context", "4096", "--mmap-experts"]


@pytest.fixture(autouse=True)
def no_engine_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test starts on serving.toml's own engine, whatever this Mac's override says, and writes its run config under tmp_path."""
    override = tmp_path / "engine-override"
    monkeypatch.setattr(serving_settings, "ENGINE_OVERRIDE_PATH", override)
    monkeypatch.setattr(strata_engine, "STRATA_RUN_CONFIG_PATH", tmp_path / "support" / "strata.json")
    return override


def git(repository: Path, *arguments: str) -> str:
    command = ["git", "-C", str(repository), "-c", "user.name=test", "-c", "user.email=test@example.invalid", *arguments]
    return subprocess.run(command, check=True, capture_output=True, text=True, env=git_environment()).stdout.strip()


@pytest.fixture
def strata_install(tmp_path: Path) -> StrataSettings:
    """A Strata checkout in miniature: one source file at a commit, our patch applied, setup's config, the server, and an engine built after both."""
    install = tmp_path / "strata"
    (install / "engine" / "src").mkdir(parents=True)
    (install / "engine" / "src" / "window.cpp").write_text(ORIGINAL_SOURCE)
    git(install, "init", "--quiet")
    git(install, "add", ".")
    git(install, "commit", "--quiet", "-m", "v0.2.16")
    patch = tmp_path / "release_host_weights.patch"
    (install / "engine" / "src" / "window.cpp").write_text(PATCHED_SOURCE)
    patch.write_text(git(install, "diff") + "\n")
    for relative_path, text in (("terminal/.venv/bin/python", ""), ("terminal/serve/server.py", ""), ("engine/strata-iq3_xxs.json", json.dumps({"args": SETUP_ARGUMENTS}))):
        (install / relative_path).parent.mkdir(parents=True, exist_ok=True)
        (install / relative_path).write_text(text)
    build_engine(install, b"STRATA_METAL_RELEASE_HOST_WEIGHTS STRATA_METAL_RELEASE_PROJECTIONS")
    return StrataSettings(
        install_dir=str(install),
        commit=git(install, "rev-parse", "HEAD"),
        release="v0.2.16",
        setup_config="engine/strata-iq3_xxs.json",
        patches=[str(patch)],
        drafting="dflash2",
        conversation_cache_mib=0,
        env={"STRATA_METAL_STREAM": "0"},
    )


def build_engine(install: Path, contents: bytes) -> None:
    binary = install / "engine" / "build-metal" / "strata"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(contents)
    newer = (install / "engine" / "src" / "window.cpp").stat().st_mtime + 10
    os.utime(binary, (newer, newer))


def config_serving_with(strata: StrataSettings, key_file: Path) -> ServingConfig:
    config = load_serving_config()
    key_file.write_text("secret-key\n")
    model = config.served_model.model_copy(update={"strata": strata})
    server = config.server.model_copy(update={"api_key_file": str(key_file)})
    return config.model_copy(update={"server": server, "models": {**config.models, config.server.model: model}})


def test_the_checked_in_file_serves_flash_next_with_strata_at_its_pinned_commit() -> None:
    config = load_serving_config()
    strata = config.served_model.strata
    assert (config.server.engine, active_engine(config)) == ("strata", "strata")
    assert (strata.commit, strata.release) == ("64524fb9fc82222ddce554c0643b64f056ec8366", "v0.2.16")
    assert all(path.is_file() for path in strata.patch_paths)
    assert strata.env["STRATA_UPDATE_CHECK"] == "0" and strata.env["STRATA_NO_ACQUIRE"] == "1"


def test_strata_needs_its_table_and_a_whole_commit_rather_than_a_tag() -> None:
    raw = load_serving_config().model_dump()
    raw["models"]["qwen3.8-flash-next"]["strata"] = None
    with pytest.raises(ValidationError, match="strata] table"):
        ServingConfig.model_validate(raw)
    raw["server"]["engine"] = "llama-server"
    assert ServingConfig.model_validate(raw).server.engine == "llama-server"
    with pytest.raises(ValidationError, match="commit"):
        StrataSettings.model_validate({**load_serving_config().served_model.strata.model_dump(), "commit": "v0.2.16"})


def test_the_override_file_picks_the_engine_on_this_mac_and_a_misspelt_one_is_refused(no_engine_override: Path) -> None:
    config = load_serving_config()
    no_engine_override.write_text("llama-server\n")
    assert active_engine(config) == "llama-server"
    no_engine_override.write_text("llamacpp\n")
    with pytest.raises(ValueError, match="llamacpp"):
        active_engine(config)


def test_the_run_config_is_setups_with_serving_tomls_context_budget_port_key_and_switches(strata_install: StrataSettings, tmp_path: Path) -> None:
    run_config = strata_run_config(config_serving_with(strata_install, tmp_path / "key"))
    assert run_config["args"] == ["--pack", "/packs/iq3_xxs", "--mmap-experts", "--max-context", "34816", "--conversation-cache-mib", "0"]
    expected = {"host": "127.0.0.1", "port": 8090, "api_key": "secret-key", "reasoning_budget_tokens": 3072, "parallel": 1, "drafting": "dflash2"}
    assert {key: run_config[key] for key in expected} == expected
    assert (run_config["env"], run_config["open_browser"]) == ({"STRATA_METAL_STREAM": "0"}, False)


def test_the_run_config_is_written_for_its_owner_alone(tmp_path: Path) -> None:
    written = write_strata_run_config({"api_key": "secret-key"})
    assert (json.loads(written.read_text()), written.stat().st_mode & 0o777) == ({"api_key": "secret-key"}, 0o600)


def test_the_pinned_commit_with_our_patch_and_an_engine_built_from_it_passes(strata_install: StrataSettings) -> None:
    assert strata_install_problems(strata_install) == []


def test_another_commit_is_refused_and_pointed_at_update(strata_install: StrataSettings) -> None:
    other = strata_install.model_copy(update={"commit": "0" * 40})
    assert "not the pinned 000000000000 (v0.2.16); run scripts/strata.sh update" in strata_install_problems(other)[0]


def test_a_missing_patch_or_a_change_of_anyones_else_is_refused(strata_install: StrataSettings) -> None:
    window = strata_install.install_path / "engine" / "src" / "window.cpp"
    window.write_text(ORIGINAL_SOURCE)
    build_engine(strata_install.install_path, b"STRATA_METAL_RELEASE_HOST_WEIGHTS STRATA_METAL_RELEASE_PROJECTIONS")
    assert "exactly our patches" in strata_install_problems(strata_install)[0]
    window.write_text(PATCHED_SOURCE + "int stray = 1;\n")
    build_engine(strata_install.install_path, b"STRATA_METAL_RELEASE_HOST_WEIGHTS STRATA_METAL_RELEASE_PROJECTIONS")
    assert "exactly our patches" in strata_install_problems(strata_install)[0]


def test_an_engine_built_before_the_patches_is_refused(strata_install: StrataSettings) -> None:
    binary = strata_install.install_path / "engine" / "build-metal" / "strata"
    binary.write_bytes(b"STRATA_METAL_RELEASE_HOST_WEIGHTS STRATA_METAL_RELEASE_PROJECTIONS")
    os.utime(binary, (0, 0))
    assert strata_install_problems(strata_install) == ["engine/build-metal/strata is older than the patched sources; rebuild it (scripts/strata.sh install)"]
    build_engine(strata_install.install_path, b"an engine from before the patches")
    assert strata_install_problems(strata_install) == ["engine/build-metal/strata was built without our patches; rebuild it (scripts/strata.sh install)"]


def config_with_verified_model_files(config: ServingConfig, tmp_path: Path) -> ServingConfig:
    model_file, draft_file = tmp_path / "model.gguf", tmp_path / "draft.gguf"
    model_file.write_bytes(b"the model")
    draft_file.write_bytes(b"the drafter")
    flash_next = config.served_model
    draft = flash_next.draft.model_copy(update={"gguf": str(draft_file), "sha256": file_sha256(draft_file)})
    model = flash_next.model_copy(update={"gguf": str(model_file), "sha256": file_sha256(model_file), "draft": draft})
    return config.model_copy(update={"models": {**config.models, config.server.model: model}})


def test_launch_writes_the_run_config_and_becomes_strata_s_server_from_its_folder(strata_install: StrataSettings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = config_with_verified_model_files(config_serving_with(strata_install, tmp_path / "key"), tmp_path)
    started = {}
    monkeypatch.setattr(serving_cli.os, "chdir", lambda folder: started.update(folder=folder))
    monkeypatch.setattr(serving_cli.os, "execv", lambda program, command: started.update(command=command))

    serving_cli.launch(config)

    run_config_path = tmp_path / "support" / "strata.json"
    assert started["folder"] == strata_install.install_path / "terminal"
    assert started["command"] == [str(strata_install.install_path / "terminal/.venv/bin/python"), "serve/server.py", "--engine", "strata", "--config", str(run_config_path), "--port", "8090"]
    assert json.loads(run_config_path.read_text())["api_key"] == "secret-key"


def test_check_and_launch_refuse_an_install_that_is_not_the_pin(strata_install: StrataSettings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wrong_commit = strata_install.model_copy(update={"commit": "0" * 40})
    config = config_with_verified_model_files(config_serving_with(wrong_commit, tmp_path / "key"), tmp_path)
    monkeypatch.setattr(serving_cli.os, "execv", lambda program, command: pytest.fail("the launch went ahead"))
    with pytest.raises(SystemExit, match="scripts/strata.sh update"):
        serving_cli.check(config)
    with pytest.raises(SystemExit, match="scripts/strata.sh update"):
        serving_cli.launch(config)


def test_with_the_override_on_llama_server_the_launch_runs_llama_server_and_ignores_strata(
    strata_install: StrataSettings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_engine_override: Path
) -> None:
    no_engine_override.write_text("llama-server\n")
    config = config_with_verified_model_files(config_serving_with(strata_install.model_copy(update={"commit": "0" * 40}), tmp_path / "key"), tmp_path)
    started = {}
    monkeypatch.setattr(serving_cli.os, "execv", lambda program, command: started.update(command=command))

    serving_cli.launch(config)

    assert started["command"][0].endswith("llama-server") and "--spec-type" in started["command"]


def test_show_prints_the_engine_and_strata_s_run_config_without_the_key(strata_install: StrataSettings, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    serving_cli.show(config_serving_with(strata_install, tmp_path / "key"))
    printed = capsys.readouterr().out
    assert printed.startswith("engine: strata\n")
    assert '"api_key": "<redacted>"' in printed and "secret-key" not in printed


def test_serving_engine_names_the_active_engine_without_reading_strata_s_install(no_engine_override: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(serving_cli.sys, "argv", ["serving", "engine"])
    monkeypatch.setattr(serving_cli, "strata_run_config", lambda config: pytest.fail("the deploy asks before Strata is installed"))
    serving_cli.main()
    no_engine_override.write_text("llama-server\n")
    serving_cli.main()
    assert capsys.readouterr().out == "strata\nllama-server\n"


def test_the_checked_in_strata_folder_sits_beside_the_other_checkouts() -> None:
    assert load_serving_config().served_model.strata.install_path == Path("~/Code/strata").expanduser()
