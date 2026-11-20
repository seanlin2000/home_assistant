"""The speech lab's web app: the page, and the JSON and audio routes the page calls. Each model call runs in a worker thread so the server stays responsive
while a model loads or speaks."""

import asyncio
from pathlib import Path

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from speech_lab.catalog import catalog
from speech_lab.results import SpeechEngine, Synthesis
from speech_lab.settings import OmniVoiceRequest, SpeechRequest, TranscriptionRequest, VoiceModelChoice

STATIC_DIR = Path(__file__).parent / "static"
STATS_HEADER = "X-Synthesis-Stats"


def build_app(engine: SpeechEngine) -> Starlette:
    routes = [
        Route("/", lambda request: FileResponse(STATIC_DIR / "index.html")),
        Route("/api/catalog", lambda request: JSONResponse(catalog())),
        Route("/api/voice-model", voice_model_route(engine), methods=["POST"]),
        Route("/api/speak", speak_route(engine), methods=["POST"]),
        Route("/api/speak-omnivoice", omnivoice_speak_route(engine), methods=["POST"]),
        Route("/api/transcribe", transcribe_route(engine), methods=["POST"]),
        Route("/api/unload", unload_route(engine), methods=["POST"]),
        Mount("/static", StaticFiles(directory=STATIC_DIR), name="static"),
    ]
    return Starlette(routes=routes, exception_handlers={ValidationError: validation_failed, ValueError: request_refused})


def voice_model_route(engine: SpeechEngine):
    async def describe(request: Request) -> JSONResponse:
        choice = VoiceModelChoice.model_validate(await request.json())
        facts = await asyncio.to_thread(engine.describe_voice_model, choice)
        return JSONResponse(facts.model_dump())

    return describe


def speak_route(engine: SpeechEngine):
    async def speak(request: Request) -> Response:
        speech_request = SpeechRequest.model_validate(await request.json())
        synthesis = await asyncio.to_thread(engine.synthesize, speech_request)
        return audio_response(synthesis)

    return speak


def omnivoice_speak_route(engine: SpeechEngine):
    async def speak(request: Request) -> Response:
        omnivoice_request = OmniVoiceRequest.model_validate(await request.json())
        synthesis = await asyncio.to_thread(engine.synthesize_with_omnivoice, omnivoice_request)
        return audio_response(synthesis)

    return speak


def audio_response(synthesis: Synthesis) -> Response:
    return Response(synthesis.wav, media_type="audio/wav", headers={STATS_HEADER: synthesis.stats.model_dump_json()})


def transcribe_route(engine: SpeechEngine):
    async def transcribe(request: Request) -> JSONResponse:
        transcription_request = TranscriptionRequest.model_validate(await request.json())
        transcription = await asyncio.to_thread(engine.transcribe, transcription_request)
        return JSONResponse(transcription.model_dump())

    return transcribe


def unload_route(engine: SpeechEngine):
    async def unload(request: Request) -> JSONResponse:
        await asyncio.to_thread(engine.unload)
        return JSONResponse({"unloaded": True})

    return unload


async def validation_failed(request: Request, error: ValidationError) -> JSONResponse:
    problems = "; ".join(f"{'.'.join(str(part) for part in problem['loc']) or 'request'}: {problem['msg']}" for problem in error.errors())
    return JSONResponse({"error": problems}, status_code=422)


async def request_refused(request: Request, error: ValueError) -> JSONResponse:
    return JSONResponse({"error": str(error)}, status_code=400)
