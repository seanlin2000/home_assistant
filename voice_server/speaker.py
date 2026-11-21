"""What the Wyoming handler asks for: one sentence, spoken as one or more pieces of audio, each ready as soon as it is made.

A sentence over 150 characters is cut at its commas first (utils/spoken_sentence_utils.py), since OmniVoice makes a whole piece before any of it
can play. Each piece is respelled from the voice's pronunciation dictionary, made on the model thread, levelled to Kokoro's loudness, and given
even edges of silence. The filler and notice phrases are ready at start-up and replayed from memory, since they are spoken while the user waits for the first tool; each is
read from the start cache (voice_server/start_cache.py) when an earlier start made it, and made and saved there when not.
"""

import logging
import time
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from speech_server.worker import ModelThread
from utils.pronunciation_utils import LivePronunciations
from utils.spoken_sentence_utils import split_long_sentence
from voice_server.settings import OmniVoiceSettings
from voice_server.start_cache import StartCache

PEAK_CEILING = 0.95  # as Kokoro's server caps its peaks
VOICED_SAMPLE_FLOOR = 0.01  # samples quieter than this are pauses, left out of the loudness
QUIET_WINDOW_SECONDS = 0.01
QUIET_DBFS = -45.0  # a 10 ms window quieter than this is silence or breath, not speech
FADE_OUT_SECONDS = 0.015  # the last sound eases out instead of stopping mid-wave

_LOGGER = logging.getLogger(__name__)


class Synthesizer(Protocol):
    @property
    def sample_rate(self) -> int: ...

    def synthesize(self, text: str) -> np.ndarray: ...


@dataclass(frozen=True)
class PieceFinish:
    """What is done to each piece after the model makes it: levelled to Kokoro's loudness, then trimmed to its speech and given set silence."""

    loudness_dbfs: float
    lead_silence_seconds: float
    trail_silence_seconds: float

    @classmethod
    def from_settings(cls, settings: OmniVoiceSettings) -> "PieceFinish":
        return cls(settings.loudness_dbfs, settings.lead_silence_seconds, settings.trail_silence_seconds)


def levelled(samples: np.ndarray, loudness_dbfs: float) -> np.ndarray:
    """The samples scaled so their voiced part has the target RMS, with the peak kept under PEAK_CEILING."""
    voiced = samples[np.abs(samples) > VOICED_SAMPLE_FLOOR]
    if voiced.size == 0:
        return samples
    gain = 10 ** (loudness_dbfs / 20) / float(np.sqrt(np.mean(voiced**2)))
    return samples * min(gain, PEAK_CEILING / float(np.abs(samples).max()))


def with_even_edges(samples: np.ndarray, sample_rate: int, finish: PieceFinish) -> np.ndarray:
    """OmniVoice ends a piece on its last sound and may start it after up to a second of near-silence. The puck holds back the last moment of
    audio when its stream runs dry, as it does after every filler while the answer is made, and plays it only when the answer arrives: so a piece
    must end in silence, as Kokoro's did (about 0.2 s), or its last word stalls and stutters. Trimmed to its speech, faded out, and padded."""
    span = speech_span(samples, sample_rate)
    if span is None:
        return samples
    speech = samples[span[0] : span[1]].astype(np.float32)
    fade_length = min(len(speech), int(FADE_OUT_SECONDS * sample_rate))
    speech[len(speech) - fade_length :] *= np.linspace(1.0, 0.0, fade_length, dtype=np.float32)
    lead = np.zeros(round(finish.lead_silence_seconds * sample_rate), dtype=np.float32)
    trail = np.zeros(round(finish.trail_silence_seconds * sample_rate), dtype=np.float32)
    return np.concatenate([lead, speech, trail])


def speech_span(samples: np.ndarray, sample_rate: int) -> tuple[int, int] | None:
    """From the first to the end of the last 10 ms window louder than QUIET_DBFS; None when the piece is silent throughout."""
    window = int(QUIET_WINDOW_SECONDS * sample_rate)
    padded = np.pad(samples, (0, -len(samples) % window))
    loudness = np.sqrt(np.mean(padded.reshape(-1, window) ** 2, axis=1))
    loud_windows = np.nonzero(loudness > 10 ** (QUIET_DBFS / 20))[0]
    if loud_windows.size == 0:
        return None
    return int(loud_windows[0]) * window, min(len(samples), (int(loud_windows[-1]) + 1) * window)


class SentenceSpeaker:
    def __init__(self, synthesizer: Synthesizer, thread: ModelThread, pronunciations: LivePronunciations, finish: PieceFinish) -> None:
        self._synthesizer = synthesizer
        self._thread = thread
        self._pronunciations = pronunciations
        self._finish = finish
        self._made_ahead: dict[str, np.ndarray] = {}

    @property
    def sample_rate(self) -> int:
        return self._synthesizer.sample_rate

    def make_ahead(self, phrases: Iterable[str], cache: StartCache) -> None:
        """Readies each phrase's pieces now, blocking, so they are replayed when a sentence asks for exactly that text."""
        self._pronunciations.refresh()
        spoken_pieces = list(dict.fromkeys(self._pronunciations.matcher.respelled(piece) for phrase in phrases for piece in split_long_sentence(phrase)))
        newly_made = [spoken for spoken in spoken_pieces if not self._ready_from(cache, spoken)]
        cache.forget_all_but(set(spoken_pieces))
        _LOGGER.info("filler pieces ready: %d from the start cache, %d made now", len(spoken_pieces) - len(newly_made), len(newly_made))

    def _ready_from(self, cache: StartCache, spoken: str) -> bool:
        """Whether the piece was already in the cache; when not, it is made and saved there."""
        saved = cache.saved_filler(spoken)
        self._made_ahead[spoken] = saved if saved is not None else self._thread.run(self._levelled_audio, spoken)
        if saved is None:
            cache.save_filler(spoken, self._made_ahead[spoken])
        return saved is not None

    async def pieces(self, sentence: str) -> AsyncIterator[np.ndarray]:
        self._pronunciations.refresh()
        for piece in split_long_sentence(sentence):
            yield await self._audio_for(self._pronunciations.matcher.respelled(piece))

    async def verbatim_pieces(self, sentence: str) -> AsyncIterator[np.ndarray]:
        """For the dashboard's previews, which respell the text themselves."""
        for piece in split_long_sentence(sentence):
            yield await self._audio_for(piece)

    async def _audio_for(self, spoken: str) -> np.ndarray:
        """The edges are added here, not before caching, so the made-ahead fillers and the start cache hold the levelled audio and a change to
        the edge settings needs no filler made again."""
        started = time.perf_counter()
        made_ahead = spoken in self._made_ahead
        levelled_audio = self._made_ahead[spoken] if made_ahead else await self._thread.run_async(self._levelled_audio, spoken)
        audio = with_even_edges(levelled_audio, self.sample_rate, self._finish)
        source = "made ahead" if made_ahead else f"made in {time.perf_counter() - started:.2f} s"
        _LOGGER.info("%d characters, %.2f s of audio, %s: %s", len(spoken), len(audio) / self.sample_rate, source, spoken)
        return audio

    def _levelled_audio(self, spoken: str) -> np.ndarray:
        return levelled(self._synthesizer.synthesize(spoken), self._finish.loudness_dbfs)
