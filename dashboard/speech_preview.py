"""Hear a sentence in a voice before it goes into the pronunciation dictionary: one Wyoming request to the voice's server on this Mac, returned as a
WAV for the page to play. The request names the verbatim speaker, so the server reads the text exactly as sent."""

import asyncio
import io
import wave

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncTcpClient
from wyoming.tts import Synthesize, SynthesizeVoice

from utils.pronunciation_utils import VERBATIM_SPEAKER

KOKORO_HOST = "127.0.0.1"
KOKORO_PORT = 10210
PREVIEW_TIMEOUT_SECONDS = 30.0


async def kokoro_wav(text: str, voice: str) -> bytes:
    async with asyncio.timeout(PREVIEW_TIMEOUT_SECONDS), AsyncTcpClient(KOKORO_HOST, KOKORO_PORT) as client:
        await client.write_event(Synthesize(text=text, voice=SynthesizeVoice(name=voice, speaker=VERBATIM_SPEAKER)).event())
        return await wav_until_audio_stops(client)


async def wav_until_audio_stops(client: AsyncTcpClient) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        while (event := await client.read_event()) is not None and not AudioStop.is_type(event.type):
            if AudioStart.is_type(event.type):
                start = AudioStart.from_event(event)
                wav.setnchannels(start.channels)
                wav.setsampwidth(start.width)
                wav.setframerate(start.rate)
            elif AudioChunk.is_type(event.type):
                wav.writeframes(AudioChunk.from_event(event).audio)
    return buffer.getvalue()
