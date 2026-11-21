"""The voice agent's launcher (voice_server/launcher.py) and the dashboard's guard on hearing a voice that is not running."""

from pathlib import Path

import pytest

from dashboard import speech_preview
from dashboard.pronunciation_views import Refused
from voice_server import launcher
from voice_server import settings as voice_settings
from voice_server.settings import load_voice_settings

SETTINGS = load_voice_settings()


@pytest.fixture
def override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "voice_engine"
    monkeypatch.setattr(voice_settings, "VOICE_ENGINE_OVERRIDE_PATH", path)
    return path


def test_kokoro_is_launched_with_the_arguments_its_agent_had(override: Path) -> None:
    override.write_text("kokoro")
    command = launcher.server_command(SETTINGS)
    assert Path(command[0]).name == "kokoro-server"
    assert command[1:] == ["--uri", "tcp://0.0.0.0:10210", "--voice", "bm_fable", "--data-dir", str(Path.home() / ".cache/wyoming-kokoro"), "--streaming", "--volume", "2", "--device", "cpu"]


def test_omnivoice_is_launched_from_the_speech_environment_with_its_settings_read_there(override: Path) -> None:
    override.write_text("omnivoice")
    assert launcher.server_command(SETTINGS) == [str(launcher.OMNIVOICE_SERVER)]


def test_the_check_names_what_omnivoice_lacks(monkeypatch: pytest.MonkeyPatch, override: Path, tmp_path: Path) -> None:
    override.write_text("omnivoice")
    monkeypatch.setattr(launcher, "OMNIVOICE_SERVER", tmp_path / "no-voice-server")
    monkeypatch.setattr(launcher, "omnivoice_model_downloaded", lambda settings: False)

    missing = launcher.missing_for_launch(SETTINGS)

    assert [item.split(" (")[0] for item in missing] == [str(tmp_path / "no-voice-server"), "mlx-community/OmniVoice-bf16 at 8fb0b75"]
    assert launcher.check(SETTINGS) == 1


def test_the_check_names_a_missing_kokoro_model(monkeypatch: pytest.MonkeyPatch, override: Path, tmp_path: Path) -> None:
    override.write_text("kokoro")
    kokoro = SETTINGS.voice.kokoro.model_copy(update={"data_dir": str(tmp_path)})
    settings = SETTINGS.model_copy(update={"voice": SETTINGS.voice.model_copy(update={"kokoro": kokoro})})

    assert launcher.missing_for_launch(settings) == [f"Kokoro's model {tmp_path / 'kokoro-v1_0.pth'} (scripts/services.sh install fetches it)"]


async def test_the_dashboard_refuses_to_preview_a_voice_that_is_not_running(override: Path) -> None:
    override.write_text("kokoro")
    with pytest.raises(Refused, match="kokoro is the voice on this Mac, so omnivoice cannot be heard"):
        await speech_preview.preview_in("omnivoice")("Jokic scored.", "jarvis")
