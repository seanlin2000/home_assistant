"""The Wyoming side: what the server tells Home Assistant it offers, and one handler per connection.

The events and their order follow wyoming-kokoro-torch, which Home Assistant already drives. A whole text arrives as one Synthesize and is
answered with one AudioStart, the audio of each sentence, and one AudioStop. A streamed text arrives as SynthesizeStart, SynthesizeChunks and
SynthesizeStop: each sentence is spoken as soon as the splitter finds its end, as its own AudioStart ... AudioStop, and SynthesizeStopped ends
the stream. Home Assistant also sends the whole text as a Synthesize inside a stream, for older servers; that copy is ignored.
"""

import asyncio
import logging
from collections.abc import AsyncIterator

import numpy as np
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.error import Error
from wyoming.event import Event
from wyoming.info import Attribution, Describe, Info, TtsProgram, TtsVoice
from wyoming.server import AsyncEventHandler
from wyoming.tts import Synthesize, SynthesizeChunk, SynthesizeStart, SynthesizeStop, SynthesizeStopped, SynthesizeVoice

from speech_server.audio import PCM_CHANNELS, PCM_WIDTH_BYTES, pcm_bytes
from utils.pronunciation_utils import VERBATIM_SPEAKER
from voice_server.settings import VoiceSettings
from voice_server.speaker import SentenceSpeaker
from voice_server.vendored.sentence_boundaries import SentenceBoundaryDetector

OMNIVOICE = "omnivoice"
JARVIS = "jarvis"
# The voice Home Assistant's pipeline saved while Kokoro spoke. It is listed, and spoken in the JARVIS voice, so the pipeline needs no change
# when the voice switches either way.
KOKORO_PIPELINE_VOICE = "bm_fable"
# Home Assistant matches a pipeline's language exactly, so both English tags are offered (#91: an en_GB pipeline found no en_US voice).
LANGUAGES = ["en_GB", "en_US"]
SAMPLES_PER_CHUNK = 1024
OMNIVOICE_ATTRIBUTION = Attribution(name="k2-fsa", url="https://github.com/k2-fsa/OmniVoice")

_LOGGER = logging.getLogger(__name__)


def voice_info(settings: VoiceSettings) -> Info:
    voices = [
        TtsVoice(name=JARVIS, description="JARVIS", attribution=OMNIVOICE_ATTRIBUTION, installed=True, version=None, languages=LANGUAGES),
        TtsVoice(name=KOKORO_PIPELINE_VOICE, description="JARVIS, under the name the pipeline saved", attribution=OMNIVOICE_ATTRIBUTION, installed=True, version=None, languages=LANGUAGES),
    ]
    program = TtsProgram(
        name=OMNIVOICE,
        description=f"OmniVoice on MLX ({settings.voice.omnivoice.source})",
        attribution=OMNIVOICE_ATTRIBUTION,
        installed=True,
        version=settings.voice.omnivoice.revision[:7],
        voices=voices,
        supports_synthesize_streaming=True,
    )
    return Info(tts=[program])


def is_verbatim(voice: SynthesizeVoice | None) -> bool:
    return voice is not None and voice.speaker == VERBATIM_SPEAKER


def one_line(text: str) -> str:
    return " ".join(text.strip().splitlines())


class VoiceHandler(AsyncEventHandler):
    def __init__(self, speaker: SentenceSpeaker, info: Info, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        super().__init__(reader, writer)
        self._speaker = speaker
        self._info_event = info.event()
        self._streaming = False
        self._verbatim = False
        self._splitter = SentenceBoundaryDetector()

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            await self.write_event(self._info_event)
            return True
        try:
            await self._handle_text_event(event)
        except Exception as error:
            await self.write_event(Error(text=str(error), code=error.__class__.__name__).event())
            raise
        return True

    async def _handle_text_event(self, event: Event) -> None:
        if Synthesize.is_type(event.type) and not self._streaming:
            await self._speak_whole_text(Synthesize.from_event(event))
        elif SynthesizeStart.is_type(event.type):
            self._start_stream(SynthesizeStart.from_event(event).voice)
        elif SynthesizeChunk.is_type(event.type):
            for sentence in self._splitter.add_chunk(SynthesizeChunk.from_event(event).text):
                await self._speak_sentence_alone(sentence)
        elif SynthesizeStop.is_type(event.type):
            await self._speak_sentence_alone(self._splitter.finish())
            await self.write_event(SynthesizeStopped().event())

    def _start_stream(self, voice: SynthesizeVoice | None) -> None:
        self._streaming = True
        self._verbatim = is_verbatim(voice)
        self._splitter = SentenceBoundaryDetector()

    async def _speak_whole_text(self, synthesize: Synthesize) -> None:
        self._verbatim = is_verbatim(synthesize.voice)
        splitter = SentenceBoundaryDetector()
        sentences = [*splitter.add_chunk(synthesize.text), splitter.finish()]
        await self._write_audio_start()
        for sentence in sentences:
            await self._write_sentence_audio(sentence)
        await self.write_event(AudioStop().event())

    async def _speak_sentence_alone(self, sentence: str) -> None:
        if not one_line(sentence):
            return
        await self._write_audio_start()
        await self._write_sentence_audio(sentence)
        await self.write_event(AudioStop().event())

    async def _write_audio_start(self) -> None:
        await self.write_event(AudioStart(rate=self._speaker.sample_rate, width=PCM_WIDTH_BYTES, channels=PCM_CHANNELS).event())

    async def _write_sentence_audio(self, sentence: str) -> None:
        text = one_line(sentence)
        if not text:
            return
        async for piece in self._pieces(text):
            await self._write_chunks(piece)

    def _pieces(self, text: str) -> AsyncIterator[np.ndarray]:
        return self._speaker.verbatim_pieces(text) if self._verbatim else self._speaker.pieces(text)

    async def _write_chunks(self, samples: np.ndarray) -> None:
        for start in range(0, len(samples), SAMPLES_PER_CHUNK):
            audio = pcm_bytes(samples[start : start + SAMPLES_PER_CHUNK])
            await self.write_event(AudioChunk(audio=audio, rate=self._speaker.sample_rate, width=PCM_WIDTH_BYTES, channels=PCM_CHANNELS).event())
