from pathlib import Path

import pytest
from pydantic import ValidationError

from serving import cli as serving_cli
from serving.command import build_command, refuse_dangerous_flags
from serving.model_file import ModelFileMismatch, file_sha256, model_file_matches, verify_model_file
from serving.settings import SERVING_CONFIG_PATH, load_serving_config


def test_the_checked_in_file_builds_the_documented_command() -> None:
    command = build_command(load_serving_config())
    for flag, value in (("--host", "127.0.0.1"), ("--port", "8090"), ("-c", "18432"), ("-np", "2"), ("-cram", "2048"), ("--reasoning", "off"), ("-fa", "on")):
        assert command[command.index(flag) + 1] == value
    assert {"--kv-unified", "--no-cache-idle-slots", "--no-ui", "--jinja", "--metrics"} <= set(command)
    assert "--swa-full" not in command
    assert command[command.index("--spec-type") + 1] == "draft-mtp"


def test_a_model_without_a_draft_layer_gets_no_speculative_flag() -> None:
    config = load_serving_config()
    gemma = config.model_copy(update={"server": config.server.model_copy(update={"model": "gemma-4-e4b"})})
    assert "--spec-type" not in build_command(gemma)


def test_an_unknown_key_stops_the_launch(tmp_path: Path) -> None:
    misspelt = tmp_path / "serving.toml"
    misspelt.write_text(SERVING_CONFIG_PATH.read_text().replace("swa_full = false", "swa_ful = false"))
    with pytest.raises(ValidationError, match="swa_ful"):
        load_serving_config(misspelt)


def test_dangerous_flags_are_refused() -> None:
    with pytest.raises(ValueError, match="--props"):
        refuse_dangerous_flags(["llama-server", "--props"])


def test_a_model_file_that_differs_from_its_pinned_hash_is_refused(tmp_path: Path) -> None:
    config = load_serving_config()
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"not the model")
    model = config.served_model.model_copy(update={"gguf": str(model_file)})
    with pytest.raises(ModelFileMismatch, match="pins"):
        verify_model_file(model)
    verify_model_file(model.model_copy(update={"sha256": file_sha256(model_file)}))


def test_a_model_file_matches_only_when_it_exists_with_its_pinned_hash(tmp_path: Path) -> None:
    model_file = tmp_path / "model.gguf"
    model = load_serving_config().served_model.model_copy(update={"gguf": str(model_file)})
    assert not model_file_matches(model)
    model_file.write_bytes(b"the model")
    assert not model_file_matches(model)
    assert model_file_matches(model.model_copy(update={"sha256": file_sha256(model_file)}))


def test_fetch_keeps_a_file_that_already_matches_instead_of_downloading_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"the model")
    model = load_serving_config().served_model.model_copy(update={"gguf": str(model_file), "sha256": file_sha256(model_file)})

    def refuse_download(_model: object) -> Path:
        raise AssertionError("downloaded a model that was already in place")

    monkeypatch.setattr(serving_cli, "fetch_model_file", refuse_download)
    serving_cli.fetch(model)


def test_thinking_takes_the_models_thinking_sampling_and_no_thinking_its_plain_set() -> None:
    qwen = load_serving_config().models["qwen3.8-27b"]
    assert qwen.sampling_for("medium").temperature == 1.0 and qwen.sampling_for("medium").presence_penalty == 0.0
    assert qwen.sampling_for(False).temperature == 0.7 and qwen.sampling_for(None).presence_penalty == 1.5
    gemma = load_serving_config().models["gemma-4-e4b"]
    assert gemma.sampling_for("medium") == gemma.sampling
