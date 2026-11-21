"""What the Wyoming handler asks for: one sentence, spoken as one or more pieces of audio, each ready as soon as it is made.

A sentence over 150 characters is cut at its commas first (utils/spoken_sentence_utils.py), since OmniVoice makes a whole piece before any of it
can play. Each piece is respelled from the voice's pronunciation dictionary, made on the model thread, and levelled to Kokoro's loudness. The
filler and notice phrases are made once at start-up and replayed from memory, since they are spoken while the user waits for the first tool.
"""

import logging
import time
from collections.abc import AsyncIterator, Iterable
from typing import Protocol

import numpy as np

from speech_server.worker import ModelThread
from utils.pronunciation_utils import LivePronunciations
from utils.spoken_sentence_utils import split_long_sentence

PEAK_CEILING = 0.95  # as Kokoro's server caps its peaks
VOICED_SAMPLE_FLOOR = 0.01  # samples quieter than this are pauses, left out of the loudness

_LOGGER = logging.getLogger(__name__)


class Synthesizer(Protocol):
    @property
    def sample_rate(self) -> int: ...

    def synthesize(self, text: str) -> np.ndarray: ...


def levelled(samples: np.ndarray, loudness_dbfs: float) -> np.ndarray:
    """The samples scaled so their voiced part has the target RMS, with the peak kept under PEAK_CEILING."""
    voiced = samples[np.abs(samples) > VOICED_SAMPLE_FLOOR]
    if voiced.size == 0:
        return samples
    gain = 10 ** (loudness_dbfs / 20) / float(np.sqrt(np.mean(voiced**2)))
    return samples * min(gain, PEAK_CEILING / float(np.abs(samples).max()))


class SentenceSpeaker:
    def __init__(self, synthesizer: Synthesizer, thread: ModelThread, pronunciations: LivePronunciations, loudness_dbfs: float) -> None:
        self._synthesizer = synthesizer
        self._thread = thread
        self._pronunciations = pronunciations
        self._loudness_dbfs = loudness_dbfs
        self._made_ahead: dict[str, np.ndarray] = {}

    @property
    def sample_rate(self) -> int:
        return self._synthesizer.sample_rate

    def make_ahead(self, phrases: Iterable[str]) -> None:
        """Makes each phrase's pieces now, blocking, so they are replayed when a sentence asks for exactly that text."""
        self._pronunciations.refresh()
        for phrase in phrases:
            for piece in split_long_sentence(phrase):
                spoken = self._pronunciations.matcher.respelled(piece)
                self._made_ahead[spoken] = self._thread.run(self._levelled_audio, spoken)
        _LOGGER.info("made %d filler pieces ahead", len(self._made_ahead))

    async def pieces(self, sentence: str) -> AsyncIterator[np.ndarray]:
        self._pronunciations.refresh()
        for piece in split_long_sentence(sentence):
            yield await self._audio_for(self._pronunciations.matcher.respelled(piece))

    async def verbatim_pieces(self, sentence: str) -> AsyncIterator[np.ndarray]:
        """For the dashboard's previews, which respell the text themselves."""
        for piece in split_long_sentence(sentence):
            yield await self._audio_for(piece)

    async def _audio_for(self, spoken: str) -> np.ndarray:
        started = time.perf_counter()
        made_ahead = spoken in self._made_ahead
        audio = self._made_ahead[spoken] if made_ahead else await self._thread.run_async(self._levelled_audio, spoken)
        source = "made ahead" if made_ahead else f"made in {time.perf_counter() - started:.2f} s"
        _LOGGER.info("%d characters, %.2f s of audio, %s: %s", len(spoken), len(audio) / self.sample_rate, source, spoken)
        return audio

    def _levelled_audio(self, spoken: str) -> np.ndarray:
        return levelled(self._synthesizer.synthesize(spoken), self._loudness_dbfs)
