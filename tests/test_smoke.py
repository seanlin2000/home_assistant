"""The smoke test's voice check (ops/smoke.py): one sentence from a stand-in Wyoming text-to-speech server on a loopback port."""

import asyncio
from collections.abc import Callable

import pytest
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.info import Attribution, Describe, Info, TtsProgram
from wyoming.server import AsyncEventHandler
from wyoming.tts import Synthesize

from ops import smoke

VOICE_RATE = 24000
BYTES_PER_SECOND = VOICE_RATE * 2


class StandInVoice(AsyncEventHandler):
    """Describes itself as `program`, and answers a Synthesize with `audio_seconds` of silence in 1,024-sample chunks, as the voice servers do."""

    def __init__(self, audio_seconds: float, *args: object, program: str = "kokoro") -> None:
        super().__init__(*args)
        self.audio_seconds = audio_seconds
        self.program = program

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            nobody = Attribution(name="", url="")
            await self.write_event(Info(tts=[TtsProgram(name=self.program, attribution=nobody, installed=True, description=None, version=None, voices=[])]).event())
            return False
        if not Synthesize.is_type(event.type):
            return True
        await self.write_event(AudioStart(rate=VOICE_RATE, width=2, channels=1).event())
        remaining = int(self.audio_seconds * BYTES_PER_SECOND)
        while remaining > 0:
            chunk = min(remaining, 2048)
            await self.write_event(AudioChunk(audio=bytes(chunk), rate=VOICE_RATE, width=2, channels=1).event())
            remaining -= chunk
        await self.write_event(AudioStop().event())
        return False


async def serving(make_handler: Callable[..., AsyncEventHandler]) -> tuple[asyncio.Server, int]:
    async def accept(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await make_handler(reader, writer).run()

    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


async def test_a_voice_that_speaks_the_sentence_passes() -> None:
    server, port = await serving(lambda reader, writer: StandInVoice(1.5, reader, writer))
    label, passed, answer, _ = await smoke.voice_check(smoke.VoiceTarget(host="127.0.0.1", port=port, engine="kokoro"), ready_timeout_seconds=10)
    server.close()  # not wait_closed: it waits for the handler's side of the connection, which the stand-in leaves open

    assert passed and answer == "kokoro: 1.50 s of audio" and label.startswith(f"voice on 127.0.0.1:{port}")


async def test_a_voice_that_answers_with_a_click_fails() -> None:
    server, port = await serving(lambda reader, writer: StandInVoice(0.1, reader, writer))
    _, passed, answer, _ = await smoke.voice_check(smoke.VoiceTarget(host="127.0.0.1", port=port, engine="kokoro"), ready_timeout_seconds=10)
    server.close()  # not wait_closed: it waits for the handler's side of the connection, which the stand-in leaves open

    assert not passed and answer == "kokoro: 0.10 s of audio"


async def test_a_voice_still_loading_is_waited_for(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smoke, "VOICE_RETRY_SECONDS", 0.05)
    placeholder = await asyncio.start_server(lambda reader, writer: None, "127.0.0.1", 0)
    port = placeholder.sockets[0].getsockname()[1]
    placeholder.close()
    await placeholder.wait_closed()

    async def start_late() -> asyncio.Server:
        await asyncio.sleep(0.2)
        return await asyncio.start_server(lambda reader, writer: StandInVoice(1.5, reader, writer).run(), "127.0.0.1", port)

    late_start = asyncio.create_task(start_late())
    _, passed, _, elapsed = await smoke.voice_check(smoke.VoiceTarget(host="127.0.0.1", port=port, engine="kokoro"), ready_timeout_seconds=10)
    (await late_start).close()

    assert passed and elapsed >= 0.2


async def test_no_voice_server_fails_once_the_time_runs_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smoke, "VOICE_RETRY_SECONDS", 0.05)
    placeholder = await asyncio.start_server(lambda reader, writer: None, "127.0.0.1", 0)
    port = placeholder.sockets[0].getsockname()[1]
    placeholder.close()
    await placeholder.wait_closed()

    _, passed, answer, _ = await smoke.voice_check(smoke.VoiceTarget(host="127.0.0.1", port=port, engine="kokoro"), ready_timeout_seconds=0.3)

    assert not passed and answer.startswith("<no audio: ConnectionRefusedError")


async def test_a_voice_that_is_not_the_engine_this_mac_should_run_fails() -> None:
    server, port = await serving(lambda reader, writer: StandInVoice(1.5, reader, writer, program="kokoro"))
    _, passed, answer, _ = await smoke.voice_check(smoke.VoiceTarget(host="127.0.0.1", port=port, engine="omnivoice"), ready_timeout_seconds=10)
    server.close()

    assert not passed and answer == "kokoro: 1.50 s of audio, but this Mac should be speaking with omnivoice"


def test_only_a_voice_on_this_mac_is_held_to_the_engine_this_macs_settings_name() -> None:
    assert smoke.voice_target("127.0.0.1", None).engine in ("omnivoice", "kokoro")
    assert smoke.voice_target("192.168.1.162", 10211) == smoke.VoiceTarget(host="192.168.1.162", port=10211, engine=None)
