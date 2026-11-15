"""Kokoro is in the voice group, which CI does not install, so this file runs only where Kokoro is."""

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("wyoming_kokoro_torch")

from wyoming.tts import Synthesize  # noqa: E402

from utils.pronunciation_utils import LivePronunciations, Pronunciation, PronunciationStore  # noqa: E402
from voice import kokoro_server  # noqa: E402


async def test_kokoro_reads_each_sentence_respelled_from_its_voices_dictionary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
    await kokoro_server.handle_synthesize_respelled(SimpleNamespace(cli_args=SimpleNamespace(voice="bm_fable")), Synthesize(text="Xi Jinping met Jokic."))

    assert read_by_kokoro == ["She Jin Ping met Yo-Kich."]
    assert voices_asked_for == ["bm_fable"]
