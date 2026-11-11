"""The setup script is loaded by file path because scripts/ is not a package."""

import argparse
import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = Path("scripts/ha_setup.py")
spec = importlib.util.spec_from_file_location("ha_setup", SCRIPT_PATH)
ha_setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ha_setup)


def parsed(monkeypatch: pytest.MonkeyPatch, *flags: str) -> argparse.Namespace:
    monkeypatch.setattr("sys.argv", ["ha_setup.py", "--host", "192.168.1.60", *flags])
    return ha_setup.parse_args()


def test_the_pipeline_speaks_with_kokoros_fable_voice_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    args = parsed(monkeypatch)

    assert (args.tts, args.tts_language, args.tts_voice) == ("kokoro", "en_GB", "bm_fable")


def test_piper_keeps_its_add_on_voice_and_us_english(monkeypatch: pytest.MonkeyPatch) -> None:
    args = parsed(monkeypatch, "--tts", "piper")

    assert (args.tts, args.tts_language, args.tts_voice) == ("piper", "en_US", None)


def test_a_named_voice_and_language_override_the_engine_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    args = parsed(monkeypatch, "--tts-voice", "af_heart", "--tts-language", "en_US")

    assert (args.tts, args.tts_language, args.tts_voice) == ("kokoro", "en_US", "af_heart")


def test_the_payload_carries_the_text_to_speech_choice_with_a_region_code() -> None:
    payload = ha_setup.pipeline_payload("stt.mlx_whisper", "conversation.studio_assistant", ha_setup.TextToSpeech("tts.kokoro", "en_GB", "bm_fable"))

    assert (payload["tts_engine"], payload["tts_language"], payload["tts_voice"]) == ("tts.kokoro", "en_GB", "bm_fable")
    assert (payload["stt_engine"], payload["conversation_engine"], payload["name"]) == ("stt.mlx_whisper", "conversation.studio_assistant", "Jarvis")


@pytest.mark.parametrize("engine", sorted(ha_setup.TTS_DEFAULTS))
def test_every_engine_default_language_is_a_region_code(engine: str) -> None:
    language, _ = ha_setup.TTS_DEFAULTS[engine]

    assert language.startswith("en_"), "a bare 'en' is accepted by the pipeline editor and then fails every run with tts-not-supported"


# The entries a move from the laptop found on 2026-11-11: two of each Wyoming service, the second left behind by an earlier setup run.
LAPTOP_ENTRIES = [
    {"entry_id": "whisper-1", "domain": "wyoming", "title": "mlx-whisper"},
    {"entry_id": "kokoro-1", "domain": "wyoming", "title": "kokoro"},
    {"entry_id": "whisper-2", "domain": "wyoming", "title": "mlx-whisper"},
    {"entry_id": "kokoro-2", "domain": "wyoming", "title": "kokoro"},
    {"entry_id": "piper", "domain": "wyoming", "title": "Piper"},
    {"entry_id": "agent", "domain": "studio_assistant", "title": "Studio Assistant"},
]


def test_an_entry_made_for_this_address_is_kept() -> None:
    saved = {"HA_WYOMING_WHISPER_ENTRY": "whisper-2", "HA_WYOMING_HOST": "192.168.1.162"}

    assert ha_setup.wyoming_entry_is_current(LAPTOP_ENTRIES, saved, "HA_WYOMING_WHISPER_ENTRY", "192.168.1.162")


def test_an_entry_made_for_another_address_is_replaced() -> None:
    saved = {"HA_WYOMING_WHISPER_ENTRY": "whisper-2", "HA_WYOMING_HOST": "192.168.1.152"}

    assert not ha_setup.wyoming_entry_is_current(LAPTOP_ENTRIES, saved, "HA_WYOMING_WHISPER_ENTRY", "192.168.1.162")


def test_an_entry_from_before_the_address_was_recorded_is_replaced_once() -> None:
    saved = {"HA_WYOMING_WHISPER_ENTRY": "whisper-2"}

    assert not ha_setup.wyoming_entry_is_current(LAPTOP_ENTRIES, saved, "HA_WYOMING_WHISPER_ENTRY", "192.168.1.162")


def test_replacing_an_entry_removes_its_duplicates_but_no_other_service() -> None:
    assert ha_setup.stale_wyoming_entry_ids(LAPTOP_ENTRIES, "whisper-2") == ["whisper-1", "whisper-2"]
    assert ha_setup.stale_wyoming_entry_ids(LAPTOP_ENTRIES, "kokoro-1") == ["kokoro-1", "kokoro-2"]


def test_an_unknown_recorded_entry_removes_nothing() -> None:
    assert ha_setup.stale_wyoming_entry_ids(LAPTOP_ENTRIES, "gone") == []
    assert ha_setup.stale_wyoming_entry_ids(LAPTOP_ENTRIES, None) == []
