"""Speak each benchmark answer through a Wyoming voice the way Home Assistant does, and time the audio.

The answer's events go through the component's own adapter (custom_components/studio_assistant/adapter.py), so the voice is sent exactly the text
Home Assistant is sent: the filler with its blank line, the answer as it streams, the fallback for an empty reply. Home Assistant's pipeline then
holds that text until it passes 60 characters, or until a tool call follows some text, and only then opens a stream to the voice; a reply that
never gets there is streamed whole at the end. Audio is read on its own task while the text is still being sent, as the speaker would play it.

Every time is in seconds from the moment the exchange was sent, on the same clock as the transcript's time to first spoken word.
"""

import asyncio
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from wyoming.audio import AudioChunk, AudioStart
from wyoming.client import AsyncTcpClient
from wyoming.tts import SynthesizeChunk, SynthesizeStart, SynthesizeStop, SynthesizeStopped

from assistant_core.models import AgentEvent, AnswerDelta, FillerSpoken, Transcript
from utils.module_utils import module_from_file

ADAPTER = module_from_file("studio_assistant_adapter", Path(__file__).resolve().parents[1] / "custom_components" / "studio_assistant" / "adapter.py")
STREAMING_START_CHARACTERS = 60  # Home Assistant's assist pipeline, STREAM_RESPONSE_CHARS
REPLY_AUDIO_TIMEOUT_SECONDS = 300  # a long answer is made sentence by sentence after its text has all arrived


class VoiceAddress(BaseModel):
    host: str
    port: int

    @classmethod
    def from_text(cls, text: str) -> "VoiceAddress":
        host, _, port = text.rpartition(":")
        return cls(host=host or "127.0.0.1", port=int(port))


class SpokenTimings(BaseModel):
    time_to_first_audio_seconds: float | None = None
    time_to_first_answer_audio_seconds: float | None = None
    audio_done_seconds: float | None = None
    spoken_audio_seconds: float = 0.0


class ExchangeVoice:
    """One exchange's connection to the voice: the text side Home Assistant's pipeline plays, and the audio side its speaker plays."""

    def __init__(self, client: AsyncTcpClient, started: float) -> None:
        self.client = client
        self.started = started
        self.held_text = ""
        self.streaming = False
        self.lines_before_answer = 0
        self.answer_began = False
        self.utterance_starts: list[float] = []
        self.awaiting_first_chunk = False
        self.last_chunk: float | None = None
        self.audio_bytes = 0
        self.bytes_per_second = 0

    async def noted(self, events: AsyncIterator[AgentEvent]) -> AsyncIterator[AgentEvent]:
        """Pass the events on, counting the filler and notice lines spoken before the answer: each is a sentence of its own, so its own utterance."""
        async for event in events:
            self.lines_before_answer += isinstance(event, FillerSpoken) and not self.answer_began
            self.answer_began = self.answer_began or isinstance(event, AnswerDelta)
            yield event

    async def say(self, delta: dict[str, Any]) -> None:
        if "tool_calls" in delta and self.held_text:
            await self.open_stream()
        text = delta.get("content")
        if text and self.streaming:
            await self.client.write_event(SynthesizeChunk(text=text).event())
        elif text:
            self.held_text += text
            await self.open_stream_past_the_threshold()

    async def open_stream_past_the_threshold(self) -> None:
        if len(self.held_text) >= STREAMING_START_CHARACTERS:
            await self.open_stream()

    async def open_stream(self) -> None:
        await self.client.write_event(SynthesizeStart().event())
        await self.client.write_event(SynthesizeChunk(text=self.held_text).event())
        self.held_text, self.streaming = "", True

    async def finish(self) -> bool:
        """End the text; False when there was nothing to say, so no audio will come."""
        if not self.streaming and not self.held_text:
            return False
        if not self.streaming:
            await self.open_stream()
        await self.client.write_event(SynthesizeStop().event())
        return True

    async def listen(self) -> None:
        while (event := await self.client.read_event()) is not None and not SynthesizeStopped.is_type(event.type):
            if AudioStart.is_type(event.type):
                self.hear_utterance_start(AudioStart.from_event(event))
            elif AudioChunk.is_type(event.type):
                self.hear_chunk(AudioChunk.from_event(event))

    def hear_utterance_start(self, start: AudioStart) -> None:
        self.awaiting_first_chunk = True
        self.bytes_per_second = start.rate * start.width * start.channels

    def hear_chunk(self, chunk: AudioChunk) -> None:
        self.last_chunk = time.perf_counter() - self.started
        if self.awaiting_first_chunk:
            self.utterance_starts.append(self.last_chunk)
            self.awaiting_first_chunk = False
        self.audio_bytes += len(chunk.audio)

    def timings(self) -> SpokenTimings:
        starts = self.utterance_starts
        return SpokenTimings(
            time_to_first_audio_seconds=starts[0] if starts else None,
            time_to_first_answer_audio_seconds=starts[self.lines_before_answer] if len(starts) > self.lines_before_answer else None,
            audio_done_seconds=self.last_chunk,
            spoken_audio_seconds=self.audio_bytes / self.bytes_per_second if self.bytes_per_second else 0.0,
        )


async def spoken_transcript(events: AsyncIterator[AgentEvent], address: VoiceAddress, started: float) -> Transcript:
    """The exchange's transcript, with the audio timings of speaking it."""
    finished: list[Transcript] = []
    async with AsyncTcpClient(address.host, address.port) as client:
        voice = ExchangeVoice(client, started)
        listening = asyncio.create_task(voice.listen())
        try:
            await say_every_delta(voice, events, finished)
            if await voice.finish():
                await asyncio.wait_for(listening, REPLY_AUDIO_TIMEOUT_SECONDS)
        finally:
            listening.cancel()
            await asyncio.gather(listening, return_exceptions=True)
    if not finished:
        raise RuntimeError("the agent's stream ended without a Done event")
    return finished[0].model_copy(update=voice.timings().model_dump())


async def say_every_delta(voice: ExchangeVoice, events: AsyncIterator[AgentEvent], finished: list[Transcript]) -> None:
    async for delta in ADAPTER.agent_events_to_deltas(voice.noted(events), lambda call: call, finished.append):
        await voice.say(delta)
