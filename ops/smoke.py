"""The smoke test a deploy runs (design doc 10 §3.8): one calculator question through Home Assistant's conversation API, then one sentence from
the voice.

    uv run python -m ops.smoke            # "What is 12 percent of 250?" must come back with 30 within 60 s, and the voice must speak
    uv run python -m ops.smoke --full     # also one searched question, which needs SearXNG and the web

The question exercises Home Assistant, the component, the harness, the model server, and the tool server; the plain version never touches the
web, so it is safe to run as often as needed. The voice check asks the text-to-speech server on its Wyoming port for one sentence and needs audio
back, so a deploy that breaks the voice fails and rolls back like one that breaks the answers. Exit code 0 on pass, 1 on fail, with the answer
printed either way.
"""

import argparse
import asyncio
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel
from wyoming.audio import AudioChunk, AudioStop
from wyoming.client import AsyncTcpClient
from wyoming.info import Describe, Info
from wyoming.tts import Synthesize

from ops.ha_client import HomeAssistant, conversation_entity_id, converse, wait_for_api, wait_for_component
from voice_server.settings import active_voice_engine, load_voice_settings

PROJECT_DIR = Path(__file__).resolve().parent.parent
CALCULATOR_QUESTION = "What is 12 percent of 250?"
CALCULATOR_EXPECTED = re.compile(r"\b(30|thirty)\b", re.IGNORECASE)
SEARCH_QUESTION = "Search the web: what is the latest stable version of Home Assistant?"
SEARCH_EXPECTED = re.compile(r"\b(20\d\d|two thousand (twenty|thirty))\b", re.IGNORECASE)  # a year-style version, in digits or spoken, proves a search was read
LOCAL_HOST = "127.0.0.1"
VOICE_SENTENCE = "This is the voice check."
MINIMUM_VOICE_AUDIO_SECONDS = 0.5  # the sentence is about 1.5 s spoken; a server that answers with a click or silence stub fails
# A voice server that was just restarted loads its model (and OmniVoice encodes its reference clip and warms up) before it listens.
VOICE_READY_TIMEOUT_SECONDS = 300
VOICE_RETRY_SECONDS = 5
VOICE_REPLY_TIMEOUT_SECONDS = 60


async def smoke(ha: HomeAssistant, timeout_seconds: float, full: bool) -> list[tuple[str, bool, str, float]]:
    await wait_for_api(ha, timeout_seconds=300, ok_statuses=(200,), poll_seconds=5)
    await wait_for_component(ha)  # a restart still loading the component refuses the question
    agent = await conversation_entity_id(ha)
    questions = [(CALCULATOR_QUESTION, CALCULATOR_EXPECTED)] + ([(SEARCH_QUESTION, SEARCH_EXPECTED)] if full else [])
    results = []
    for question, expected in questions:
        started = time.monotonic()
        try:
            answer = await converse(ha, question, agent, timeout_seconds=timeout_seconds)
        except Exception as error:  # noqa: BLE001 - the smoke test reports, it does not crash
            answer = f"<{type(error).__name__}: {error}>"
        elapsed = time.monotonic() - started
        results.append((question, bool(expected.search(answer)), answer, elapsed))
    return results


class VoiceTarget(BaseModel):
    host: str
    port: int
    engine: str | None  # the program the voice must report (omnivoice or kokoro); None skips that check, for a voice on another Mac


async def voice_check(target: VoiceTarget, ready_timeout_seconds: float) -> tuple[str, bool, str, float]:
    """One sentence from the text-to-speech server, retried until it answers or the time runs out; a result in the questions' shape."""
    label = f"voice on {target.host}:{target.port}: {VOICE_SENTENCE}"
    started = time.monotonic()
    while True:
        try:
            program = await asyncio.wait_for(program_name(target), VOICE_REPLY_TIMEOUT_SECONDS)
            audio_seconds = await asyncio.wait_for(spoken_audio_seconds(target, VOICE_SENTENCE), VOICE_REPLY_TIMEOUT_SECONDS)
            return label, *voice_verdict(target, program, audio_seconds), time.monotonic() - started
        except (OSError, TimeoutError) as error:  # a refused or dropped connection is an OSError
            if time.monotonic() - started + VOICE_RETRY_SECONDS > ready_timeout_seconds:
                return label, False, f"<no audio: {type(error).__name__}: {error}>", time.monotonic() - started
            await asyncio.sleep(VOICE_RETRY_SECONDS)


def voice_verdict(target: VoiceTarget, program: str, audio_seconds: float) -> tuple[bool, str]:
    heard = f"{program}: {audio_seconds:.2f} s of audio"
    if target.engine is not None and program != target.engine:
        return False, f"{heard}, but this Mac should be speaking with {target.engine}"
    return audio_seconds >= MINIMUM_VOICE_AUDIO_SECONDS, heard


async def program_name(target: VoiceTarget) -> str:
    async with AsyncTcpClient(target.host, target.port) as client:
        await client.write_event(Describe().event())
        while (event := await client.read_event()) is not None:
            if Info.is_type(event.type):
                programs = Info.from_event(event).tts
                return programs[0].name if programs else "<no text-to-speech program>"
    raise ConnectionError("the voice server closed the connection before describing itself")


async def spoken_audio_seconds(target: VoiceTarget, text: str) -> float:
    audio_bytes, bytes_per_second = 0, 0
    async with AsyncTcpClient(target.host, target.port) as client:
        await client.write_event(Synthesize(text=text).event())
        while True:
            event = await client.read_event()
            if event is None:
                raise ConnectionError("the voice server closed the connection before the audio ended")
            if AudioChunk.is_type(event.type):
                chunk = AudioChunk.from_event(event)
                audio_bytes += len(chunk.audio)
                bytes_per_second = chunk.rate * chunk.width * chunk.channels
            elif AudioStop.is_type(event.type):
                return audio_bytes / bytes_per_second if bytes_per_second else 0.0


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_DIR / ".env")
    parser = argparse.ArgumentParser(description="Ask Home Assistant one calculator question and check the answer.")
    parser.add_argument("--full", action="store_true", help="add one searched question")
    parser.add_argument("--timeout", type=float, default=60.0, help="seconds to wait for each answer (default 60)")
    parser.add_argument("--host", default=os.environ.get("HA_HOST"), help="Home Assistant host (default HA_HOST from .env)")
    parser.add_argument("--voice-host", default=LOCAL_HOST, help="the text-to-speech server's host (default this Mac, where a deploy runs)")
    parser.add_argument("--voice-port", type=int, help="its Wyoming port (default [voice] port in config/voice.toml)")
    args = parser.parse_args(argv)
    if not args.host:
        print("HA_HOST is not set", file=sys.stderr)
        return 2
    ha = HomeAssistant(args.host, os.environ.get("HA_TOKEN", ""), os.environ.get("HA_BASE"))
    try:
        results = asyncio.run(run(ha, args.timeout, args.full))
        results.append(asyncio.run(voice_check(voice_target(args.voice_host, args.voice_port), VOICE_READY_TIMEOUT_SECONDS)))
    except Exception as error:  # noqa: BLE001
        print(f"smoke: FAIL before asking anything: {type(error).__name__}: {error}")
        return 1
    passed = all(ok for _, ok, _, _ in results)
    for question, ok, answer, elapsed in results:
        print(f"smoke: {'pass' if ok else 'FAIL'} {elapsed:5.1f}s  {question!r} -> {answer!r}")
    return 0 if passed else 1


def voice_target(host: str, port: int | None) -> VoiceTarget:
    """On this Mac the engine it should run is known (config/voice.toml and its override); another Mac's override cannot be read from here."""
    settings = load_voice_settings()
    engine = active_voice_engine(settings) if host == LOCAL_HOST else None
    return VoiceTarget(host=host, port=port or settings.voice.port, engine=engine)


async def run(ha: HomeAssistant, timeout_seconds: float, full: bool):
    try:
        return await smoke(ha, timeout_seconds, full)
    finally:
        await ha.close()


if __name__ == "__main__":
    sys.exit(main())
