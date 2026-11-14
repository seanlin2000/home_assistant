"""The Wyoming side: what the server tells Home Assistant it offers, and one handler per connection for speech to text and for text to speech."""

import asyncio
import logging

import numpy as np
from wyoming.asr import Transcript
from wyoming.audio import AudioChunk, AudioChunkConverter, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.info import AsrModel, AsrProgram, Attribution, Describe, Info, TtsProgram, TtsVoice
from wyoming.server import AsyncEventHandler
from wyoming.tts import Synthesize, SynthesizeChunk, SynthesizeStart, SynthesizeStop, SynthesizeStopped, SynthesizeVoice

from speech_server.audio import PCM_CHANNELS, PCM_WIDTH_BYTES, RECOGNIZER_SAMPLE_RATE, SentenceGain, loudest_frame_dbfs, pcm_samples
from speech_server.settings import LANGUAGE_TAGS, SpeechSettings
from speech_server.text import SentenceSplitter
from speech_server.worker import SpeechWorker

QWEN_ATTRIBUTION = Attribution(name="Qwen", url="https://github.com/QwenLM")

_LOGGER = logging.getLogger(__name__)


def recognizer_info(settings: SpeechSettings) -> Info:
    asr = settings.asr
    model = AsrModel(name=asr.source, attribution=QWEN_ATTRIBUTION, installed=True, description="Qwen3-ASR", version=asr.revision[:7], languages=asr.language_tags)
    return Info(asr=[AsrProgram(name="qwen3-asr", attribution=QWEN_ATTRIBUTION, installed=True, description="Qwen3-ASR on MLX", version=None, models=[model])])


def voice_info(settings: SpeechSettings) -> Info:
    tts = settings.tts
    voices = [
        TtsVoice(name=voice, attribution=QWEN_ATTRIBUTION, installed=True, description=f"{voice} ({language})", version=tts.revision[:7], languages=LANGUAGE_TAGS[language])
        for voice, language in tts.voices.items()
    ]
    program = TtsProgram(name="qwen3-tts", attribution=QWEN_ATTRIBUTION, installed=True, description="Qwen3-TTS CustomVoice on MLX", version=None, voices=voices)
    program.supports_synthesize_streaming = True
    return Info(tts=[program])


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


class VoiceHandler(AsyncEventHandler):
    """Speaks either one Synthesize event, or a stream of text (synthesize-start, chunks, synthesize-stop) sentence by sentence as each completes.

    A streamed sentence goes out as its own AudioStart, chunks and AudioStop, and SynthesizeStopped ends the stream, as Home Assistant expects. During
    a stream Home Assistant also sends the whole text as one Synthesize for older servers; that copy is ignored."""

    def __init__(self, worker: SpeechWorker, settings: SpeechSettings, info: Info, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        super().__init__(reader, writer)
        self._worker = worker
        self._tts = settings.tts
        self._info_event = info.event()
        self._splitter = SentenceSplitter()
        self._stream_voice: str | None = None

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            await self.write_event(self._info_event)
        elif SynthesizeStart.is_type(event.type):
            await self._start_stream(SynthesizeStart.from_event(event).voice)
        elif SynthesizeChunk.is_type(event.type) and self._stream_voice:
            await self._speak_sentences(self._splitter.add(SynthesizeChunk.from_event(event).text), self._stream_voice)
        elif SynthesizeStop.is_type(event.type) and self._stream_voice:
            await self._finish_stream(self._stream_voice)
        elif Synthesize.is_type(event.type) and not self._stream_voice:
            await self._speak_whole_text(Synthesize.from_event(event))
        return True

    async def _start_stream(self, voice: SynthesizeVoice | None) -> None:
        self._splitter = SentenceSplitter()
        self._stream_voice = self._chosen_voice(voice)

    async def _finish_stream(self, voice: str) -> None:
        await self._speak_sentences([self._splitter.finish()], voice)
        self._stream_voice = None
        await self.write_event(SynthesizeStopped().event())

    async def _speak_sentences(self, sentences: list[str], voice: str) -> None:
        for sentence in filter(None, sentences):
            await self._write_audio_start()
            await self._write_sentence_audio(sentence, voice)
            await self.write_event(AudioStop().event())

    async def _speak_whole_text(self, synthesize: Synthesize) -> None:
        splitter = SentenceSplitter()
        voice = self._chosen_voice(synthesize.voice)
        await self._write_audio_start()
        for sentence in filter(None, [*splitter.add(synthesize.text), splitter.finish()]):
            await self._write_sentence_audio(sentence, voice)
        await self.write_event(AudioStop().event())

    async def _write_audio_start(self) -> None:
        await self.write_event(AudioStart(rate=self._worker.sample_rate, width=PCM_WIDTH_BYTES, channels=PCM_CHANNELS).event())

    async def _write_sentence_audio(self, sentence: str, voice: str) -> None:
        gain = SentenceGain(self._tts.gain)
        async for samples in self._worker.speak(sentence, voice):
            chunk = AudioChunk(audio=gain.amplified_pcm(samples), rate=self._worker.sample_rate, width=PCM_WIDTH_BYTES, channels=PCM_CHANNELS)
            await self.write_event(chunk.event())

    def _chosen_voice(self, voice: SynthesizeVoice | None) -> str:
        requested = voice.name if voice else None
        chosen = self._tts.voice_or_default(requested)
        if requested and requested != chosen:
            _LOGGER.warning("unknown voice %r, speaking with %r", requested, chosen)
        return chosen
