"""Exercise the Wyoming speech services directly from the Mac, without Home Assistant, to check they work and how fast they are.

    uv run python scripts/voice_check.py tts --host 127.0.0.1 --port 10210 --text "Let me pull some sources on that." --out /tmp/reply.wav
    uv run python scripts/voice_check.py stt --host 127.0.0.1 --port 10300 --wav /tmp/reply.wav
    uv run python scripts/voice_check.py info --host 127.0.0.1 --port 10300

The tts command reports time to first audio and whether the server streamed audio before finishing synthesis, which is what lets the assistant's
filler sentence play while the search runs (design_docs/v1/05, section 4).
"""

import argparse
import asyncio
import sys
import time
import wave
from pathlib import Path

from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncTcpClient
from wyoming.info import Describe, Info
from wyoming.tts import Synthesize, SynthesizeVoice


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Wyoming speech services.")
    parser.add_argument("command", choices=["tts", "stt", "info"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--text", default="Let me pull some sources on that.")
    parser.add_argument("--voice", default=None)
    parser.add_argument("--out", default="voice_check.wav")
    parser.add_argument("--wav", help="16-bit PCM WAV to transcribe")
    return parser.parse_args()


async def info(args: argparse.Namespace) -> None:
    async with AsyncTcpClient(args.host, args.port) as client:
        await client.write_event(Describe().event())
        event = await client.read_event()
    description = Info.from_event(event)
    for program in description.asr:
        print(f"asr: {program.name} models={[model.name for model in program.models]}")
    for program in description.tts:
        voices = [voice.name for voice in program.voices]
        print(f"tts: {program.name} supports_synthesize_streaming={getattr(program, 'supports_synthesize_streaming', None)} voices={voices[:12]}{'...' if len(voices) > 12 else ''}")


async def tts(args: argparse.Namespace) -> None:
    voice = SynthesizeVoice(name=args.voice) if args.voice else None
    started = time.perf_counter()
    first_audio_at: float | None = None
    chunks: list[AudioChunk] = []
    async with AsyncTcpClient(args.host, args.port) as client:
        await client.write_event(Synthesize(text=args.text, voice=voice).event())
        while True:
            event = await client.read_event()
            if event is None:
                break
            if AudioChunk.is_type(event.type):
                first_audio_at = first_audio_at or time.perf_counter()
                chunks.append(AudioChunk.from_event(event))
            elif AudioStop.is_type(event.type):
                break
    total = time.perf_counter() - started
    if not chunks:
        raise SystemExit("no audio returned")
    write_wav(Path(args.out), chunks)
    seconds_of_audio = sum(len(chunk.audio) for chunk in chunks) / (chunks[0].rate * chunks[0].width * chunks[0].channels)
    print(f"tts: first audio after {first_audio_at - started:.2f}s, {seconds_of_audio:.1f}s of audio in {total:.2f}s ({seconds_of_audio / total:.1f}x real time), {len(chunks)} chunks -> {args.out}")


def write_wav(path: Path, chunks: list[AudioChunk]) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(chunks[0].channels)
        handle.setsampwidth(chunks[0].width)
        handle.setframerate(chunks[0].rate)
        for chunk in chunks:
            handle.writeframes(chunk.audio)


async def stt(args: argparse.Namespace) -> None:
    if not args.wav:
        raise SystemExit("--wav is required for stt")
    with wave.open(args.wav, "rb") as handle:
        rate, width, channels = handle.getframerate(), handle.getsampwidth(), handle.getnchannels()
        frames = handle.readframes(handle.getnframes())
    started = time.perf_counter()
    async with AsyncTcpClient(args.host, args.port) as client:
        await client.write_event(Transcribe(language="en").event())
        await client.write_event(AudioStart(rate=rate, width=width, channels=channels).event())
        step = rate * width * channels // 10
        for offset in range(0, len(frames), step):
            await client.write_event(AudioChunk(rate=rate, width=width, channels=channels, audio=frames[offset : offset + step]).event())
        await client.write_event(AudioStop().event())
        while True:
            event = await client.read_event()
            if event is None:
                raise SystemExit("connection closed before a transcript arrived")
            if Transcript.is_type(event.type):
                text = Transcript.from_event(event).text
                break
    print(f"stt: {time.perf_counter() - started:.2f}s for {len(frames) / (rate * width * channels):.1f}s of audio -> {text!r}")


def main() -> None:
    args = parse_args()
    asyncio.run({"tts": tts, "stt": stt, "info": info}[args.command](args))


if __name__ == "__main__":
    sys.exit(main())
