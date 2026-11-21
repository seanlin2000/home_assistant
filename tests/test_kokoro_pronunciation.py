"""Kokoro is in the voice group, which CI does not install, so this file runs only where Kokoro is."""

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("wyoming_kokoro_torch")

from wyoming.tts import Synthesize, SynthesizeVoice  # noqa: E402

from utils.pronunciation_utils import VERBATIM_SPEAKER, LivePronunciations, Pronunciation, PronunciationStore  # noqa: E402
from voice import kokoro_server  # noqa: E402


async def test_kokoro_reads_each_sentence_respelled_except_a_dashboard_preview_asking_for_it_verbatim(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = PronunciationStore("kokoro", "bm_fable", live_dir=tmp_path / "live", versioned_dir=tmp_path / "git")
    store.save([Pronunciation(written="Xi Jinping", say_as="She Jin Ping"), Pronunciation(written="Jokic", say_as="Yo-Kich")])
    voices_asked_for, read_by_kokoro = [], []

    async def upstream(handler: object, synthesize: Synthesize, send_start: bool, send_stop: bool) -> bool:
        read_by_kokoro.append(synthesize.text)
        return True

    def pronunciations_for(voice: str) -> LivePronunciations:
        voices_asked_for.append(voice)
        return LivePronunciations(store)

    monkeypatch.setattr(kokoro_server, "_ORIGINAL_HANDLE_SYNTHESIZE", upstream)
    monkeypatch.setattr(kokoro_server, "pronunciations_for", pronunciations_for)
    handler = SimpleNamespace(cli_args=SimpleNamespace(voice="bm_fable"), voices_info={"bm_fable": {}})
    await kokoro_server.handle_synthesize_respelled(handler, Synthesize(text="Xi Jinping met Jokic."))
    await kokoro_server.handle_synthesize_respelled(handler, Synthesize(text="Xi Jinping met Jokic.", voice=SynthesizeVoice(name="bm_fable", speaker=VERBATIM_SPEAKER)))

    assert read_by_kokoro == ["She Jin Ping met Yo-Kich.", "Xi Jinping met Jokic."]
    assert voices_asked_for == ["bm_fable"]


def test_a_voice_kokoro_does_not_have_is_spoken_with_its_configured_one() -> None:
    """The pipeline may still name OmniVoice's voice after a switch back to Kokoro, which would otherwise stay silent."""
    handler = SimpleNamespace(cli_args=SimpleNamespace(voice="bm_fable"), voices_info={"bm_fable": {}, "af_heart": {}})

    assert kokoro_server.with_a_voice_kokoro_has(handler, Synthesize(text="Hi.", voice=SynthesizeVoice(name="jarvis"))).voice.name == "bm_fable"
    assert kokoro_server.with_a_voice_kokoro_has(handler, Synthesize(text="Hi.", voice=SynthesizeVoice(name="af_heart"))).voice.name == "af_heart"
    assert kokoro_server.with_a_voice_kokoro_has(handler, Synthesize(text="Hi.")).voice is None
