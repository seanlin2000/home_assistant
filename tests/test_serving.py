from pathlib import Path

import pytest
from pydantic import ValidationError

from serving.command import build_command, refuse_dangerous_flags
from serving.model_file import ModelFileMismatch, file_sha256, verify_model_file
from serving.settings import SERVING_CONFIG_PATH, load_serving_config


def test_the_checked_in_file_builds_the_documented_command() -> None:
    command = build_command(load_serving_config())
    for flag, value in (("--host", "127.0.0.1"), ("--port", "8090"), ("-c", "18432"), ("-np", "2"), ("-cram", "1024"), ("--reasoning", "off"), ("-fa", "on")):
        assert command[command.index(flag) + 1] == value
    assert {"--kv-unified", "--no-cache-idle-slots", "--no-ui", "--jinja", "--metrics"} <= set(command)
    assert "--swa-full" not in command


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
