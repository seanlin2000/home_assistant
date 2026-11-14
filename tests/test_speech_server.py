import asyncio
from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError
from wyoming.asr import Transcript
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncTcpClient
from wyoming.event import Event
from wyoming.info import Describe, Info
from wyoming.server import AsyncEventHandler
from wyoming.tts import Synthesize, SynthesizeChunk, SynthesizeStart, SynthesizeStop, SynthesizeStopped, SynthesizeVoice

from speech_server.audio import RECOGNIZER_SAMPLE_RATE, SentenceGain, loudest_frame_dbfs, pcm_bytes
from speech_server.handlers import RecognizerHandler, VoiceHandler, recognizer_info, voice_info
from speech_server.settings import SpeechLength, SpeechSettings, load_speech_settings
from speech_server.text import SentenceSplitter, max_audio_tokens
from speech_server.worker import ModelThread, SpeechWorker

SETTINGS = load_speech_settings()
PIECE_AMPLITUDES = (0.1, 0.2)


class FakeModels:
    sample_rate = 24000

    def __init__(self) -> None:
        self.spoken: list[tuple[str, str]] = []
        self.heard: list[np.ndarray] = []

    def speak(self, sentence: str, voice: str) -> Iterator[np.ndarray]:
        self.spoken.append((sentence, voice))
        for amplitude in PIECE_AMPLITUDES:
            yield np.full(2400, amplitude, dtype=np.float32)

    def transcribe(self, audio: np.ndarray) -> str:
        self.heard.append(audio)
        return "Turn off the kitchen lights."


@asynccontextmanager
async def connected(make_handler: Callable[[asyncio.StreamReader, asyncio.StreamWriter], AsyncEventHandler]):
    async def accept(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await make_handler(reader, writer).run()

    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    client = AsyncTcpClient("127.0.0.1", server.sockets[0].getsockname()[1])
    await client.connect()
    try:
        yield client
    finally:
        await client.disconnect()
        server.close()


async def events_until(client: AsyncTcpClient, last_type: str) -> list[Event]:
    events = []
    while (event := await asyncio.wait_for(client.read_event(), timeout=5)) is not None:
        events.append(event)
        if event.type == last_type:
            break
    return events


def voice_handler(models: FakeModels) -> Callable[[asyncio.StreamReader, asyncio.StreamWriter], AsyncEventHandler]:
    return lambda reader, writer: VoiceHandler(SpeechWorker(models, ModelThread()), SETTINGS, voice_info(SETTINGS), reader, writer)


def recognizer_handler(models: FakeModels) -> Callable[[asyncio.StreamReader, asyncio.StreamWriter], AsyncEventHandler]:
    return lambda reader, writer: RecognizerHandler(SpeechWorker(models, ModelThread()), SETTINGS, recognizer_info(SETTINGS), reader, writer)


def tone(seconds: float, amplitude: float) -> np.ndarray:
    times = np.arange(int(seconds * RECOGNIZER_SAMPLE_RATE)) / RECOGNIZER_SAMPLE_RATE
    return (amplitude * np.sin(2 * np.pi * 220 * times)).astype(np.float32)


async def send_recording(client: AsyncTcpClient, samples: np.ndarray) -> None:
    await client.write_event(AudioStart(rate=RECOGNIZER_SAMPLE_RATE, width=2, channels=1).event())
    for start in range(0, len(samples), 1600):
        await client.write_event(AudioChunk(audio=pcm_bytes(samples[start : start + 1600]), rate=RECOGNIZER_SAMPLE_RATE, width=2, channels=1).event())
    await client.write_event(AudioStop().event())


async def test_streamed_text_is_spoken_sentence_by_sentence_in_the_requested_voice() -> None:
    models = FakeModels()
    async with connected(voice_handler(models)) as client:
        await client.write_event(SynthesizeStart(voice=SynthesizeVoice(name="serena")).event())
        for text in ("Let me pull some sources on that.", "\n\n", "It is fifty", " eight degrees."):
            await client.write_event(SynthesizeChunk(text=text).event())
        await client.write_event(Synthesize(text="Let me pull some sources on that.\n\nIt is fifty eight degrees.").event())
        await client.write_event(SynthesizeStop().event())
        events = await events_until(client, SynthesizeStopped().event().type)

    assert models.spoken == [("Let me pull some sources on that.", "serena"), ("It is fifty eight degrees.", "serena")]
    assert sum(AudioStart.is_type(event.type) for event in events) == 2
    assert sum(AudioChunk.is_type(event.type) for event in events) == 4


async def test_one_synthesize_event_is_one_audio_stream_and_an_unknown_voice_falls_back_to_ryan() -> None:
    models = FakeModels()
    async with connected(voice_handler(models)) as client:
        await client.write_event(Synthesize(text="Hello there. How are you?", voice=SynthesizeVoice(name="bm_fable")).event())
        events = await events_until(client, AudioStop().event().type)

    assert models.spoken == [("Hello there.", "ryan"), ("How are you?", "ryan")]
    assert sum(AudioStart.is_type(event.type) for event in events) == 1


async def test_speech_goes_out_twice_as_loud_as_the_model_made_it() -> None:
    async with connected(voice_handler(FakeModels())) as client:
        await client.write_event(Synthesize(text="Hello there.").event())
        chunks = [AudioChunk.from_event(event) for event in await events_until(client, AudioStop().event().type) if AudioChunk.is_type(event.type)]

    loudness = [int(np.frombuffer(chunk.audio, dtype=np.int16)[0]) for chunk in chunks]
    assert loudness == [int(2 * amplitude * 32767) for amplitude in PIECE_AMPLITUDES]
    assert chunks[0].rate == FakeModels.sample_rate


async def test_a_question_is_transcribed_when_its_audio_stops() -> None:
    models = FakeModels()
    async with connected(recognizer_handler(models)) as client:
        await send_recording(client, tone(seconds=1.5, amplitude=0.3))
        events = await events_until(client, Transcript(text="").event().type)

    assert Transcript.from_event(events[-1]).text == "Turn off the kitchen lights."
    assert len(models.heard[0]) == int(1.5 * RECOGNIZER_SAMPLE_RATE)


async def test_a_recording_with_no_speech_gets_an_empty_transcript_without_the_model() -> None:
    models = FakeModels()
    async with connected(recognizer_handler(models)) as client:
        await send_recording(client, tone(seconds=1.0, amplitude=0.001))
        events = await events_until(client, Transcript(text="").event().type)

    assert Transcript.from_event(events[-1]).text == ""
    assert models.heard == []


async def test_each_port_describes_what_it_offers() -> None:
    async with connected(voice_handler(FakeModels())) as client:
        await client.write_event(Describe().event())
        voice_program = Info.from_event((await events_until(client, Info().event().type))[-1]).tts[0]
    async with connected(recognizer_handler(FakeModels())) as client:
        await client.write_event(Describe().event())
        recognizer_program = Info.from_event((await events_until(client, Info().event().type))[-1]).asr[0]

    assert {voice.name: voice.languages for voice in voice_program.voices} == {"ryan": ["en"], "serena": ["zh"], "uncle_fu": ["zh"]}
    assert voice_program.supports_synthesize_streaming
    assert recognizer_program.models[0].languages == ["en"]


def test_a_sentence_is_handed_back_as_soon_as_it_ends() -> None:
    splitter = SentenceSplitter()

    assert splitter.add("Let me pull some sources on that.") == []
    assert splitter.add("\n\nIt costs $3.50 at St. Mark's, said Dr. Lee of the U.S. team") == ["Let me pull some sources on that."]
    assert splitter.add(". Next") == ["It costs $3.50 at St. Mark's, said Dr. Lee of the U.S. team."]
    assert splitter.finish() == "Next"


def test_chinese_sentences_end_without_a_space_and_punctuation_alone_is_never_spoken() -> None:
    splitter = SentenceSplitter()

    assert splitter.add("你好。今天很冷！还有") == ["你好。", "今天很冷！"]
    assert splitter.add("…\n\n") == ["还有…"]
    assert SentenceSplitter().add("... \n\n") == []


def test_a_sentence_may_last_only_as_long_as_its_text_needs() -> None:
    length = SpeechLength(minimum_seconds=2.0, seconds_per_latin_character=0.12, seconds_per_cjk_character=0.5)

    assert max_audio_tokens("Hi.", length) == 25
    assert max_audio_tokens("Turn off the kitchen lights.", length) == 35
    assert max_audio_tokens("今天很冷", length) == 25
    assert max_audio_tokens("今天很冷，明天会更冷", length) == 57


def test_a_piece_that_would_clip_lowers_the_gain_for_the_rest_of_the_sentence() -> None:
    gain = SentenceGain(2.0)

    gain.amplified_pcm(np.array([0.1], dtype=np.float32))
    assert gain.gain == 2.0
    loud = np.frombuffer(gain.amplified_pcm(np.array([0.95], dtype=np.float32)), dtype=np.int16)
    assert loud[0] == int(0.95 * 32767) and gain.gain == pytest.approx(1.0)
    gain.amplified_pcm(np.array([0.1], dtype=np.float32))
    assert gain.gain == pytest.approx(1.0)


def test_loudness_is_the_loudest_moment_not_the_average() -> None:
    question = np.concatenate([np.zeros(RECOGNIZER_SAMPLE_RATE * 3, dtype=np.float32), tone(seconds=0.2, amplitude=0.1)])

    assert loudest_frame_dbfs(question, RECOGNIZER_SAMPLE_RATE) == pytest.approx(-23.0, abs=0.2)
    assert loudest_frame_dbfs(np.zeros(RECOGNIZER_SAMPLE_RATE, dtype=np.float32), RECOGNIZER_SAMPLE_RATE) == -120.0
    assert loudest_frame_dbfs(np.zeros(10, dtype=np.float32), RECOGNIZER_SAMPLE_RATE) == -120.0


def test_the_checked_in_config_serves_ryan_on_whispers_and_kokoros_ports() -> None:
    assert (SETTINGS.server.asr_port, SETTINGS.server.tts_port) == (10300, 10210)
    assert SETTINGS.tts.default_voice == "ryan" and set(SETTINGS.tts.voices) == {"ryan", "serena", "uncle_fu"}
    assert SETTINGS.asr.source.endswith("Qwen3-ASR-1.7B-8bit") and SETTINGS.tts.source.endswith("Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit")


def test_a_config_mistake_stops_the_server(tmp_path: Path) -> None:
    good = SETTINGS.model_dump()
    with pytest.raises(ValidationError, match="default_voice"):
        SpeechSettings.model_validate(good | {"tts": good["tts"] | {"default_voice": "vivian"}})
    with pytest.raises(ValidationError, match="Extra inputs"):
        SpeechSettings.model_validate(good | {"asr": good["asr"] | {"lanugage": "English"}})
    with pytest.raises(ValidationError, match="asr.language"):
        SpeechSettings.model_validate(good | {"asr": good["asr"] | {"language": "Klingon"}})
