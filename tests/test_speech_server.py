import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager

import numpy as np
import pytest
from pydantic import ValidationError
from wyoming.asr import Transcript
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncTcpClient
from wyoming.event import Event
from wyoming.info import Describe, Info
from wyoming.server import AsyncEventHandler

from speech_server.audio import RECOGNIZER_SAMPLE_RATE, loudest_frame_dbfs, pcm_bytes
from speech_server.handlers import RecognizerHandler, recognizer_info
from speech_server.settings import SpeechSettings, load_speech_settings
from speech_server.worker import ModelThread, SpeechWorker

SETTINGS = load_speech_settings()


class FakeRecognizer:
    def __init__(self) -> None:
        self.heard: list[np.ndarray] = []

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


def recognizer_handler(recognizer: FakeRecognizer) -> Callable[[asyncio.StreamReader, asyncio.StreamWriter], AsyncEventHandler]:
    return lambda reader, writer: RecognizerHandler(SpeechWorker(recognizer, ModelThread()), SETTINGS, recognizer_info(SETTINGS), reader, writer)


def tone(seconds: float, amplitude: float) -> np.ndarray:
    times = np.arange(int(seconds * RECOGNIZER_SAMPLE_RATE)) / RECOGNIZER_SAMPLE_RATE
    return (amplitude * np.sin(2 * np.pi * 220 * times)).astype(np.float32)


async def send_recording(client: AsyncTcpClient, samples: np.ndarray) -> None:
    await client.write_event(AudioStart(rate=RECOGNIZER_SAMPLE_RATE, width=2, channels=1).event())
    for start in range(0, len(samples), 1600):
        await client.write_event(AudioChunk(audio=pcm_bytes(samples[start : start + 1600]), rate=RECOGNIZER_SAMPLE_RATE, width=2, channels=1).event())
    await client.write_event(AudioStop().event())


async def test_a_question_is_transcribed_when_its_audio_stops() -> None:
    recognizer = FakeRecognizer()
    async with connected(recognizer_handler(recognizer)) as client:
        await send_recording(client, tone(seconds=1.5, amplitude=0.3))
        events = await events_until(client, Transcript(text="").event().type)

    assert Transcript.from_event(events[-1]).text == "Turn off the kitchen lights."
    assert len(recognizer.heard[0]) == int(1.5 * RECOGNIZER_SAMPLE_RATE)


async def test_a_recording_with_no_speech_gets_an_empty_transcript_without_the_model() -> None:
    recognizer = FakeRecognizer()
    async with connected(recognizer_handler(recognizer)) as client:
        await send_recording(client, tone(seconds=1.0, amplitude=0.001))
        events = await events_until(client, Transcript(text="").event().type)

    assert Transcript.from_event(events[-1]).text == ""
    assert recognizer.heard == []


async def test_the_port_describes_qwen3_asr_in_english() -> None:
    async with connected(recognizer_handler(FakeRecognizer())) as client:
        await client.write_event(Describe().event())
        recognizer_program = Info.from_event((await events_until(client, Info().event().type))[-1]).asr[0]

    assert recognizer_program.models[0].languages == ["en"]


def test_loudness_is_the_loudest_moment_not_the_average() -> None:
    question = np.concatenate([np.zeros(RECOGNIZER_SAMPLE_RATE * 3, dtype=np.float32), tone(seconds=0.2, amplitude=0.1)])

    assert loudest_frame_dbfs(question, RECOGNIZER_SAMPLE_RATE) == pytest.approx(-23.0, abs=0.2)
    assert loudest_frame_dbfs(np.zeros(RECOGNIZER_SAMPLE_RATE, dtype=np.float32), RECOGNIZER_SAMPLE_RATE) == -120.0
    assert loudest_frame_dbfs(np.zeros(10, dtype=np.float32), RECOGNIZER_SAMPLE_RATE) == -120.0


def test_the_checked_in_config_serves_qwen3_asr_on_whispers_port() -> None:
    assert SETTINGS.server.asr_port == 10300
    assert SETTINGS.asr.source.endswith("Qwen3-ASR-1.7B-8bit") and SETTINGS.asr.language == "English"


def test_a_config_mistake_stops_the_server() -> None:
    good = SETTINGS.model_dump()
    with pytest.raises(ValidationError, match="Extra inputs"):
        SpeechSettings.model_validate(good | {"asr": good["asr"] | {"lanugage": "English"}})
    with pytest.raises(ValidationError, match="asr.language"):
        SpeechSettings.model_validate(good | {"asr": good["asr"] | {"language": "Klingon"}})
