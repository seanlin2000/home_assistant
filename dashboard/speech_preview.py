"""Hear a sentence in a voice before it goes into the pronunciation dictionary: one Wyoming request to the voice on this Mac, returned as a WAV for
the page to play. The request names the verbatim speaker, so the server reads the text exactly as sent."""

import asyncio
import io
import wave

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncTcpClient
from wyoming.tts import Synthesize, SynthesizeVoice

from dashboard.pronunciation_views import Refused, Speak
from utils.pronunciation_utils import VERBATIM_SPEAKER
from voice_server.settings import VoiceEngine, active_voice_engine, load_voice_settings

VOICE_HOST = "127.0.0.1"
PREVIEW_TIMEOUT_SECONDS = 30.0  # OmniVoice makes a sentence whole before sending any of it


def voice_in_use() -> VoiceEngine:
    """Read at every request, so a switch with scripts/services.sh voice-engine shows without restarting the dashboard."""
    return active_voice_engine(load_voice_settings())


def preview_in(engine: VoiceEngine) -> Speak:
    """Both voices answer on the one port, so only the running one can be heard; asking for the other is refused, not answered wrongly."""

    async def wav(text: str, voice: str) -> bytes:
        settings = load_voice_settings()
        running = active_voice_engine(settings)
        if running != engine:
            raise Refused(503, f"{running} is the voice on this Mac, so {engine} cannot be heard (scripts/services.sh voice-engine {engine} switches)")
        return await voice_wav(settings.voice.port, text, voice)

    return wav


async def voice_wav(port: int, text: str, voice: str) -> bytes:
    async with asyncio.timeout(PREVIEW_TIMEOUT_SECONDS), AsyncTcpClient(VOICE_HOST, port) as client:
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
