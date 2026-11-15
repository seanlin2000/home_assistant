"""The Wyoming side: what the server tells Home Assistant it offers, and one handler per connection, each transcribing one question."""

import asyncio
import logging

import numpy as np
from wyoming.asr import Transcript
from wyoming.audio import AudioChunk, AudioChunkConverter, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.info import AsrModel, AsrProgram, Attribution, Describe, Info
from wyoming.server import AsyncEventHandler

from speech_server.audio import PCM_CHANNELS, PCM_WIDTH_BYTES, RECOGNIZER_SAMPLE_RATE, loudest_frame_dbfs, pcm_samples
from speech_server.settings import SpeechSettings
from speech_server.worker import SpeechWorker

QWEN_ATTRIBUTION = Attribution(name="Qwen", url="https://github.com/QwenLM")

_LOGGER = logging.getLogger(__name__)


def recognizer_info(settings: SpeechSettings) -> Info:
    asr = settings.asr
    model = AsrModel(name=asr.source, attribution=QWEN_ATTRIBUTION, installed=True, description="Qwen3-ASR", version=asr.revision[:7], languages=asr.language_tags)
    return Info(asr=[AsrProgram(name="qwen3-asr", attribution=QWEN_ATTRIBUTION, installed=True, description="Qwen3-ASR on MLX", version=None, models=[model])])


class RecognizerHandler(AsyncEventHandler):
    """One question: audio arrives in chunks, and its transcript goes back when the audio stops."""

    def __init__(self, worker: SpeechWorker, settings: SpeechSettings, info: Info, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        super().__init__(reader, writer)
        self._worker = worker
        self._speech_floor_dbfs = settings.asr.speech_floor_dbfs
        self._info_event = info.event()
        self._converter = AudioChunkConverter(rate=RECOGNIZER_SAMPLE_RATE, width=PCM_WIDTH_BYTES, channels=PCM_CHANNELS)
        self._audio = bytearray()

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            await self.write_event(self._info_event)
        elif AudioStart.is_type(event.type):
            self._audio.clear()
        elif AudioChunk.is_type(event.type):
            self._audio += self._converter.convert(AudioChunk.from_event(event)).audio
        elif AudioStop.is_type(event.type):
            await self.write_event(Transcript(text=await self._transcript(pcm_samples(bytes(self._audio)))).event())
            return False
        return True

    async def _transcript(self, samples: np.ndarray) -> str:
        loudness = loudest_frame_dbfs(samples, RECOGNIZER_SAMPLE_RATE)
        if loudness < self._speech_floor_dbfs:
            _LOGGER.info("no speech: the loudest moment is %.1f dBFS, under the %.1f dBFS floor", loudness, self._speech_floor_dbfs)
            return ""
        return await self._worker.transcribe(samples)
