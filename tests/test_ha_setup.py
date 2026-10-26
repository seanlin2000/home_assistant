"""The setup script is loaded by file path because scripts/ is not a package."""

import argparse
import importlib.util
import re
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


def test_only_phones_with_the_home_assistant_app_are_notified() -> None:
    services = [
        {"domain": "light", "services": {"turn_on": {}}},
        {"domain": "notify", "services": {"notify": {}, "persistent_notification": {}, "send_message": {}, "mobile_app_seans_iphone": {}, "mobile_app_ipad": {}}},
    ]

    assert ha_setup.phone_notify_services(services) == ["mobile_app_ipad", "mobile_app_seans_iphone"]


@pytest.mark.parametrize(("title", "is_stable"), [("26.9.0", True), ("26.10.0", True), ("26.10.0b1", False), ("26.10.0-beta.1", False), ("Release notes", False)])
def test_only_stable_release_titles_are_announced(title: str, is_stable: bool) -> None:
    assert bool(re.match(ha_setup.STABLE_RELEASE_TITLE, title)) is is_stable


def test_a_release_is_announced_on_every_phone_and_in_the_notification_bell() -> None:
    automation = ha_setup.firmware_release_automation(["mobile_app_seans_iphone"])

    assert [action["action"] for action in automation["actions"]] == ["notify.mobile_app_seans_iphone", "persistent_notification.create"]
    assert automation["triggers"] == [{"trigger": "event", "event_type": "feedreader", "event_data": {"feed_url": ha_setup.FIRMWARE_RELEASES_FEED}}]


def test_the_conditions_hold_the_stable_title_pattern_and_the_recent_release_window() -> None:
    templates = [condition["value_template"] for condition in ha_setup.firmware_release_automation([])["conditions"]]

    assert templates[0] == "{{ trigger.event.data.title is match('" + ha_setup.STABLE_RELEASE_TITLE + "') }}"
    assert templates[1] == "{{ as_timestamp(trigger.event.data.updated, 0) > as_timestamp(now()) - 172800 }}"
