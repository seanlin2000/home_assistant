"""The voice server's start cache (voice_server/start_cache.py): what an earlier start made is reused only while everything that shaped it is
unchanged, and a later start makes only what is new."""

from pathlib import Path

import numpy as np
import pytest

from speech_server.worker import ModelThread
from tests.test_voice_server import ENGINE, StandInSynthesizer
from utils.pronunciation_utils import LivePronunciations, PronunciationStore
from voice_server.settings import OmniVoiceSettings, load_voice_settings
from voice_server.speaker import PieceFinish, SentenceSpeaker
from voice_server.start_cache import StartCache

OMNIVOICE = load_voice_settings().voice.omnivoice
FILLERS = ["One moment.", "Let me look that up."]


def dictionary_saying(folder: Path, say_as: str) -> PronunciationStore:
    dictionary = folder / "versioned" / "omnivoice" / "jarvis.json"
    dictionary.parent.mkdir(parents=True, exist_ok=True)
    dictionary.write_text(f'{{"model": "omnivoice", "voice": "jarvis", "revision": 0, "entries": [{{"written": "look", "say_as": "{say_as}"}}]}}')
    return PronunciationStore("omnivoice", "jarvis", live_dir=folder / "live", versioned_dir=folder / "versioned")


def started(tmp_path: Path, fillers: list[str], settings: OmniVoiceSettings = OMNIVOICE, say_as: str = "look", engine: str = ENGINE) -> list[str]:
    """One start's filler make-ahead; returns what the model was asked to make."""
    synthesizer = StandInSynthesizer()
    speaker = SentenceSpeaker(synthesizer, ModelThread(), LivePronunciations(dictionary_saying(tmp_path / "dictionary", say_as)), PieceFinish.from_settings(settings))
    speaker.make_ahead(fillers, StartCache(settings, tmp_path / "cache", engine))
    return synthesizer.made


def test_a_second_start_with_nothing_changed_makes_nothing(tmp_path: Path) -> None:
    assert started(tmp_path, FILLERS) == FILLERS
    assert started(tmp_path, FILLERS) == []


def test_a_new_filler_is_the_only_one_made_and_a_dropped_one_is_deleted(tmp_path: Path) -> None:
    started(tmp_path, FILLERS)

    assert started(tmp_path, ["One moment.", "Bear with me."]) == ["Bear with me."]
    assert len(list((tmp_path / "cache" / "fillers").rglob("*.npy"))) == 2
    assert started(tmp_path, FILLERS) == ["Let me look that up."]


def test_a_filler_the_dictionary_now_respells_is_made_again(tmp_path: Path) -> None:
    started(tmp_path, FILLERS)
    assert started(tmp_path, FILLERS, say_as="Luke") == ["Let me Luke that up."]


@pytest.mark.parametrize(
    "change",
    [{"steps": 16}, {"loudness_dbfs": -18.0}, {"reference_text": "Allow me to introduce myself."}, {"revision": "0" * 40}, {"reference_max_seconds": 10.0}],
)
def test_a_change_to_what_shapes_the_sound_makes_every_filler_again(tmp_path: Path, change: dict[str, object]) -> None:
    started(tmp_path, FILLERS)
    assert started(tmp_path, FILLERS, settings=OMNIVOICE.model_copy(update=change)) == FILLERS
    assert len(list((tmp_path / "cache" / "fillers").iterdir())) == 1  # the old fingerprint's folder is gone


def test_a_new_engine_or_clip_makes_the_tokens_and_fillers_again(tmp_path: Path) -> None:
    cache = StartCache(OMNIVOICE, tmp_path, ENGINE)
    cache.save_reference_tokens(np.arange(16, dtype=np.int32).reshape(2, 8))
    other_clip = tmp_path / "other.wav"
    other_clip.write_bytes(OMNIVOICE.reference_clip_path.read_bytes() + b"\0")

    assert np.array_equal(StartCache(OMNIVOICE, tmp_path, ENGINE).saved_reference_tokens(), np.arange(16).reshape(2, 8))
    assert StartCache(OMNIVOICE, tmp_path, "mlx-audio==0.6.6 mlx==0.32.4").saved_reference_tokens() is None
    assert StartCache(OMNIVOICE.model_copy(update={"reference_clip": str(other_clip)}), tmp_path, ENGINE).saved_reference_tokens() is None
    assert StartCache(OMNIVOICE, tmp_path, "mlx-audio==0.6.6 mlx==0.32.4").speech_key != cache.speech_key


def test_a_saved_filler_plays_back_exactly_as_it_was_made(tmp_path: Path) -> None:
    cache = StartCache(OMNIVOICE, tmp_path, ENGINE)
    audio = StandInSynthesizer().synthesize("One moment.")
    cache.save_filler("One moment.", audio)
    assert np.array_equal(cache.saved_filler("One moment."), audio) and cache.saved_filler("Bear with me.") is None
    assert not list(tmp_path.rglob(".*.partial"))
