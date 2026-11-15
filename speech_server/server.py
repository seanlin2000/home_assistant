"""Serve the speech-to-text port."""

from functools import partial

from wyoming.server import AsyncTcpServer

from speech_server.handlers import RecognizerHandler, recognizer_info
from speech_server.settings import SpeechSettings
from speech_server.worker import SpeechWorker


async def serve(worker: SpeechWorker, settings: SpeechSettings) -> None:
    recognizer_server = AsyncTcpServer(settings.server.host, settings.server.asr_port)
    await recognizer_server.run(partial(RecognizerHandler, worker, settings, recognizer_info(settings)))
