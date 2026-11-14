"""Serve both Wyoming ports from one process, so the two models share one Python and one MLX runtime."""

import asyncio
from functools import partial

from wyoming.server import AsyncTcpServer

from speech_server.handlers import RecognizerHandler, VoiceHandler, recognizer_info, voice_info
from speech_server.settings import SpeechSettings
from speech_server.worker import SpeechWorker


async def serve(worker: SpeechWorker, settings: SpeechSettings) -> None:
    server = settings.server
    recognizer_server = AsyncTcpServer(server.host, server.asr_port)
    voice_server = AsyncTcpServer(server.host, server.tts_port)
    await asyncio.gather(
        recognizer_server.run(partial(RecognizerHandler, worker, settings, recognizer_info(settings))),
        voice_server.run(partial(VoiceHandler, worker, settings, voice_info(settings))),
    )
