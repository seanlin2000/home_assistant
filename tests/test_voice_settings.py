"""config/voice.toml and its loader (voice_server/settings.py), and the per-Mac engine overrides both the voice and the model server read."""

import wave
from pathlib import Path

import pytest
from pydantic import ValidationError

from utils.engine_override_utils import EngineOverride
from voice_server import settings as voice_settings
from voice_server.settings import active_voice_engine, load_voice_settings

SETTINGS = load_voice_settings()


def test_the_committed_settings_are_the_ones_the_load_test_measured() -> None:
    omnivoice = SETTINGS.voice.omnivoice
    assert (omnivoice.source, omnivoice.revision) == ("mlx-community/OmniVoice-bf16", "8fb0b754cad788aaefec690cd55c207e8a628f85")
    assert (omnivoice.steps, omnivoice.reference_max_seconds, omnivoice.mlx_wired_limit_mib, omnivoice.mlx_cache_limit_mib) == (32, 20.0, 3400, 256)
    assert SETTINGS.voice.port == 10210


def test_the_reference_clip_is_in_the_repository_and_shorter_than_the_encoding_limit() -> None:
    with wave.open(str(SETTINGS.voice.omnivoice.reference_clip_path)) as clip:
        seconds = clip.getnframes() / clip.getframerate()
    assert 8 < seconds < SETTINGS.voice.omnivoice.reference_max_seconds


def test_a_misspelt_setting_stops_the_voice(tmp_path: Path) -> None:
    config = tmp_path / "voice.toml"
    config.write_text(Path(voice_settings.VOICE_CONFIG_PATH).read_text().replace("steps = 32", "step = 32"))
    with pytest.raises(ValidationError, match="step"):
        load_voice_settings(config)


def test_an_unknown_engine_is_refused(tmp_path: Path) -> None:
    config = tmp_path / "voice.toml"
    config.write_text(Path(voice_settings.VOICE_CONFIG_PATH).read_text().replace('engine = "kokoro"', 'engine = "piper"'))
    with pytest.raises(ValidationError, match="engine"):
        load_voice_settings(config)


def test_the_override_file_picks_the_voice_on_one_mac(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    override = tmp_path / "voice_engine"
    monkeypatch.setattr(voice_settings, "VOICE_ENGINE_OVERRIDE_PATH", override)
    assert active_voice_engine(SETTINGS) == SETTINGS.voice.engine
    override.write_text("omnivoice\n")
    assert active_voice_engine(SETTINGS) == "omnivoice"


def test_an_override_naming_no_engine_says_how_to_remove_it(tmp_path: Path) -> None:
    override = EngineOverride(path=tmp_path / "engine", engines=("strata", "llama-server"), reset_command="scripts/services.sh engine default")
    (tmp_path / "engine").write_text("ollama")
    with pytest.raises(ValueError, match=r"names 'ollama'; expected one of strata, llama-server \(scripts/services.sh engine default removes it\)"):
        override.engine_or("strata")
