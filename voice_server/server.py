"""Serve the text-to-speech port."""

from functools import partial

from wyoming.server import AsyncTcpServer

from voice_server.handlers import VoiceHandler, voice_info
from voice_server.settings import VoiceSettings
from voice_server.speaker import SentenceSpeaker


async def serve(speaker: SentenceSpeaker, settings: VoiceSettings) -> None:
    voice_server = AsyncTcpServer(settings.voice.host, settings.voice.port)
    await voice_server.run(partial(VoiceHandler, speaker, voice_info(settings)))
