"""Spoken benchmark questions through Home Assistant's own Assist pipeline (speech to text, our agent, text to speech), the way the puck asks them,
timed from the end of the question's speech. The Strata trial uses it to compare what the user hears under llama-server and under Strata.

    uv run voice-latency prepare --run R                      # each question's text, spoken once by Kokoro, as 16 kHz WAVs in the run's audio folder
    uv run voice-latency ask --run R --label llama-1 A11 A77  # stream each WAV into the pipeline in real time; one row per question in voice_latency.jsonl
    uv run voice-latency summarize --run R                    # per label: the median of every stage, and the averages of the 5-second samples (samples.tsv)

Home Assistant's address and token come from the environment (HA_HOST, HA_TOKEN, HA_BASE), as for ops.smoke, or from ask's --env-file.
"""

import argparse
import asyncio
import csv
import json
import os
import statistics
import time
import wave
from pathlib import Path

import httpx
import numpy
import websockets
from dotenv import load_dotenv
from pydantic import BaseModel
from wyoming.audio import AudioChunk, AudioStop
from wyoming.client import AsyncTcpClient
from wyoming.tts import Synthesize

from benchmark.records import append_jsonl, load_config, load_questions, read_jsonl
from ops.ha_client import discover_base

CONFIG_PATH = Path("benchmark/config.yaml")
QUESTIONS_PATH = Path("benchmark/questions.yaml")
PIPELINE_NAME = "Jarvis"
PIPELINE_RATE = 16000  # Home Assistant's speech-to-text stage takes 16 kHz, 16-bit, mono
CHUNK_SAMPLES = 1024
TRAILING_SILENCE_SECONDS = 3.0  # an upper bound: streaming stops as soon as the pipeline hears the end of speech, as the puck's does
MAX_PAUSE_SECONDS = 0.25  # Kokoro's pauses between sentences are long enough for the pipeline to take them as the end of the question
SILENCE_FRAME_SAMPLES = 320  # 20 ms
SILENCE_LEVEL = 0.02  # a frame quieter than this share of the loudest sample counts as a pause
FIRST_AUDIO_BYTES = 4096  # a stream's header arrives before any speech; the reply counts as started once this much has come
RUN_TIMEOUT_SECONDS = 300
KOKORO_HOST, KOKORO_PORT = "127.0.0.1", 10210
PAGE_BYTES = 16384
LIST_PIPELINES_MESSAGE_ID, RUN_MESSAGE_ID = 1, 2  # Home Assistant refuses a websocket message whose id is not above the last one
PROCESS_COLUMNS = {"engine": "Engine", "speech": "Qwen3-ASR", "kokoro": "Kokoro", "vm": "HA VM"}


class VoiceAnswer(BaseModel):
    label: str
    question_id: str
    transcript: str = ""
    answer: str = ""
    stt_seconds: float | None = None  # the end of the question's speech to the transcript, including the wait for end-of-speech detection
    first_words_seconds: float | None = None  # to the agent's first streamed words (the filler or the answer's first sentence)
    answer_seconds: float | None = None  # to the agent's whole answer
    first_audio_seconds: float | None = None  # to the first sound of the spoken reply: what the user waits for
    error: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Time spoken benchmark questions through the Assist pipeline.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "ask", "summarize"):
        command = commands.add_parser(name)
        command.add_argument("--run", required=True, help="results folder under benchmark/results")
        if name == "ask":
            command.add_argument("--label", required=True, help="the setup and round, e.g. llama-1")
            command.add_argument("--env-file", type=Path, help="a .env holding HA_HOST and HA_TOKEN, e.g. the live checkout's")
            command.add_argument("question_ids", nargs="+")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dir = Path(load_config(CONFIG_PATH).services.results_dir) / args.run
    if args.command == "prepare":
        asyncio.run(prepare(run_dir))
    elif args.command == "ask":
        load_dotenv(args.env_file)
        asyncio.run(ask(run_dir, args.label, args.question_ids))
    else:
        print(summarize(run_dir))


async def prepare(run_dir: Path) -> None:
    audio_dir = run_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    for question in load_questions(QUESTIONS_PATH).questions:
        samples = shorten_pauses(await kokoro_samples(question.exchanges[0]))
        write_wav(audio_dir / f"{question.id}.wav", samples)
        print(f"{question.id}: {len(samples) / PIPELINE_RATE:.1f} s")


async def kokoro_samples(text: str) -> numpy.ndarray:
    """The text in Kokoro's voice, resampled to the pipeline's 16 kHz."""
    chunks: list[AudioChunk] = []
    async with AsyncTcpClient(KOKORO_HOST, KOKORO_PORT) as client:
        await client.write_event(Synthesize(text=text).event())
        while (event := await client.read_event()) is not None and not AudioStop.is_type(event.type):
            if AudioChunk.is_type(event.type):
                chunks.append(AudioChunk.from_event(event))
    samples = numpy.frombuffer(b"".join(chunk.audio for chunk in chunks), dtype=numpy.int16).astype(numpy.float64)
    source_times = numpy.arange(len(samples)) / chunks[0].rate
    target_times = numpy.arange(int(len(samples) * PIPELINE_RATE / chunks[0].rate)) / PIPELINE_RATE
    return numpy.interp(target_times, source_times, samples).astype(numpy.int16)


def shorten_pauses(samples: numpy.ndarray) -> numpy.ndarray:
    """Every run of quiet 20 ms frames longer than MAX_PAUSE_SECONDS cut down to that length, so the question reaches the pipeline in one breath."""
    frame_count = len(samples) // SILENCE_FRAME_SAMPLES
    frames = samples[: frame_count * SILENCE_FRAME_SAMPLES].reshape(frame_count, SILENCE_FRAME_SAMPLES)
    quiet = numpy.abs(frames).max(axis=1) < SILENCE_LEVEL * max(int(numpy.abs(samples).max()), 1)
    longest_pause_frames = int(MAX_PAUSE_SECONDS * PIPELINE_RATE / SILENCE_FRAME_SAMPLES)
    kept, quiet_run = [], 0
    for frame, is_quiet in zip(frames, quiet):
        quiet_run = quiet_run + 1 if is_quiet else 0
        if quiet_run <= longest_pause_frames:
            kept.append(frame)
    return numpy.concatenate(kept) if kept else samples


def write_wav(path: Path, samples: numpy.ndarray) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(PIPELINE_RATE)
        handle.writeframes(samples.tobytes())


async def ask(run_dir: Path, label: str, question_ids: list[str]) -> None:
    base = os.environ.get("HA_BASE") or discover_base(os.environ["HA_HOST"])
    for question_id in question_ids:
        answer = await timed_pipeline_run(base, os.environ["HA_TOKEN"], VoiceAnswer(label=label, question_id=question_id), run_dir / "audio" / f"{question_id}.wav")
        append_jsonl(run_dir / "voice_latency.jsonl", answer)
        print(
            f"{label} {question_id}: stt {answer.stt_seconds}, first words {answer.first_words_seconds}, answer {answer.answer_seconds}, " f"first audio {answer.first_audio_seconds} {answer.error}",
            flush=True,
        )


async def timed_pipeline_run(base: str, token: str, answer: VoiceAnswer, wav_path: Path) -> VoiceAnswer:
    try:
        async with websockets.connect(base.replace("http", "ws", 1) + "/api/websocket", max_size=None) as socket:
            await authenticate(socket, token)
            run_request = {"type": "assist_pipeline/run", "start_stage": "stt", "end_stage": "tts", "input": {"sample_rate": PIPELINE_RATE}, "timeout": RUN_TIMEOUT_SECONDS}
            await socket.send(json.dumps({"id": RUN_MESSAGE_ID, "pipeline": await pipeline_id(socket), **run_request}))
            await follow_run(socket, base, wav_path, answer)
    except Exception as error:  # noqa: BLE001 - one failed question is a row with its error, not the end of the comparison
        answer.error = f"{type(error).__name__}: {error}"
    return answer


async def authenticate(socket: websockets.ClientConnection, token: str) -> None:
    await socket.recv()
    await socket.send(json.dumps({"type": "auth", "access_token": token}))
    reply = json.loads(await socket.recv())
    if reply.get("type") != "auth_ok":
        raise RuntimeError(f"websocket auth failed: {reply}")


async def pipeline_id(socket: websockets.ClientConnection) -> str:
    await socket.send(json.dumps({"id": LIST_PIPELINES_MESSAGE_ID, "type": "assist_pipeline/pipeline/list"}))
    while (reply := json.loads(await socket.recv())).get("id") != LIST_PIPELINES_MESSAGE_ID:
        pass
    return next(pipeline["id"] for pipeline in reply["result"]["pipelines"] if pipeline["name"] == PIPELINE_NAME)


class QuestionStream:
    """The question's audio going out while the run's events come in. The user's wait starts when the speech itself ends (speech_end); the stream
    then sends silence until the pipeline hears the end of speech, as the puck does, and an event before speech_end means the question was cut short."""

    def __init__(self, socket: websockets.ClientConnection, handler_id: int, wav_path: Path) -> None:
        with wave.open(str(wav_path), "rb") as handle:
            self.speech = handle.readframes(handle.getnframes())
        self.started = time.monotonic()
        self.speech_end = self.started + len(self.speech) / (2 * PIPELINE_RATE)
        self.end_of_speech_heard = asyncio.Event()
        self.task = asyncio.create_task(self.send(socket, bytes([handler_id])))

    async def send(self, socket: websockets.ClientConnection, prefix: bytes) -> None:
        frames = self.speech + bytes(2 * int(TRAILING_SILENCE_SECONDS * PIPELINE_RATE))
        chunk_bytes, chunk_seconds = 2 * CHUNK_SAMPLES, CHUNK_SAMPLES / PIPELINE_RATE
        for index, offset in enumerate(range(0, len(frames), chunk_bytes)):
            if self.end_of_speech_heard.is_set():
                break
            await socket.send(prefix + frames[offset : offset + chunk_bytes])
            await asyncio.sleep(max(0.0, self.started + (index + 1) * chunk_seconds - time.monotonic()))
        await socket.send(prefix)

    def seconds_since_speech_end(self) -> float:
        return time.monotonic() - self.speech_end


async def follow_run(socket: websockets.ClientConnection, base: str, wav_path: Path, answer: VoiceAnswer) -> None:
    """Times each event from the end of the question's speech, reading events while the question streams. The spoken reply is fetched as a satellite
    fetches it: as soon as the agent starts streaming text to speech, or at the end of text to speech when it does not."""
    stream: QuestionStream | None = None
    audio_task: asyncio.Task | None = None
    tts_url = ""
    async for raw in socket:
        message = json.loads(raw)
        if message.get("type") == "result" and not message.get("success", True):
            raise RuntimeError(f"pipeline refused the run: {message.get('error')}")
        if message.get("type") != "event":
            continue
        event, data = message["event"]["type"], message["event"].get("data") or {}
        if event == "run-start":
            tts_url = (data.get("tts_output") or {}).get("url", "")
            stream = QuestionStream(socket, data["runner_data"]["stt_binary_handler_id"], wav_path)
        elif event in ("stt-vad-end", "stt-end"):
            note_end_of_question(stream, event, data, answer)
        elif event == "intent-progress":
            if answer.first_words_seconds is None and (data.get("chat_log_delta") or {}).get("content"):
                answer.first_words_seconds = stream.seconds_since_speech_end()
            if data.get("tts_start_streaming") and audio_task is None and tts_url:
                audio_task = asyncio.create_task(first_audio_seconds(base + tts_url, stream.speech_end))
        elif event == "intent-end":
            answer.answer_seconds = stream.seconds_since_speech_end()
            answer.answer = spoken_answer(data)
        elif event == "tts-end" and audio_task is None:
            audio_task = asyncio.create_task(first_audio_seconds(base + ((data.get("tts_output") or {}).get("url") or tts_url), stream.speech_end))
        elif event == "error":
            raise RuntimeError(f"{data.get('code')}: {data.get('message')}")
        elif event == "run-end":
            break
    if stream is not None:
        await stream.task
    if audio_task is not None:
        answer.first_audio_seconds = await audio_task


def note_end_of_question(stream: QuestionStream, event: str, data: dict, answer: VoiceAnswer) -> None:
    stream.end_of_speech_heard.set()
    if stream.seconds_since_speech_end() < 0 and not answer.error:
        answer.error = f"cut short: {event} {-stream.seconds_since_speech_end():.1f} s before the question's speech ended"
    if event == "stt-end":
        answer.transcript = data["stt_output"]["text"]
        answer.stt_seconds = stream.seconds_since_speech_end()


def spoken_answer(intent_end_data: dict) -> str:
    response = (intent_end_data.get("intent_output") or {}).get("response") or {}
    return response.get("speech", {}).get("plain", {}).get("speech", "")


async def first_audio_seconds(url: str, speech_end: float) -> float | None:
    """The time until the spoken reply's first audio arrives, reading the rest so the stream finishes as a speaker's would."""
    first: float | None = None
    received = 0
    async with httpx.AsyncClient(timeout=RUN_TIMEOUT_SECONDS) as client, client.stream("GET", url) as response:
        async for chunk in response.aiter_bytes():
            received += len(chunk)
            if first is None and received >= FIRST_AUDIO_BYTES:
                first = time.monotonic() - speech_end
    return first


def summarize(run_dir: Path) -> str:
    answers = read_jsonl(run_dir / "voice_latency.jsonl", VoiceAnswer)
    labels = sorted({answer.label for answer in answers})
    lines = ["| Setup | Questions (errors) | STT s | First words s | Whole answer s | First audio s |", "|---|---|---|---|---|---|"]
    for label in labels:
        mine = [answer for answer in answers if answer.label == label]
        medians = " | ".join(median_of(mine, field) for field in ("stt_seconds", "first_words_seconds", "answer_seconds", "first_audio_seconds"))
        lines.append(f"| {label} | {len(mine)} ({sum(1 for answer in mine if answer.error)}) | {medians} |")
    lines += ["", "First audio per question, in seconds:", "", "| Question | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    for question_id in dict.fromkeys(answer.question_id for answer in answers):
        lines.append(f"| {question_id} | " + " | ".join(first_audio_cell(answers, label, question_id) for label in labels) + " |")
    samples_path = run_dir / "samples.tsv"
    if samples_path.exists():
        lines += ["", sample_averages(read_samples(samples_path))]
    return "\n".join(lines)


def median_of(answers: list[VoiceAnswer], field: str) -> str:
    values = [getattr(answer, field) for answer in answers if getattr(answer, field) is not None]
    return f"{statistics.median(values):.2f}" if values else "–"


def first_audio_cell(answers: list[VoiceAnswer], label: str, question_id: str) -> str:
    values = [answer.first_audio_seconds for answer in answers if answer.label == label and answer.question_id == question_id and answer.first_audio_seconds is not None]
    return f"{values[0]:.2f}" if values else "–"


def read_samples(samples_path: Path) -> list[dict[str, str]]:
    with samples_path.open() as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def sample_averages(rows: list[dict[str, str]]) -> str:
    """Each setup's averages over its 5-second samples; the cumulative counters (swap-ins, swap-outs, file reads) become MB per minute."""
    process_headers = "".join(f" {name} total / of it compressed GB |" for name in PROCESS_COLUMNS.values())
    lines = [
        "| Setup | Samples | Swap used GB | Swap-ins MB/min | Swap-outs MB/min | File reads MB/min | memory_pressure free % | Wired GB | Compressor GB |" + process_headers,
        "|---|" + "---|" * (8 + len(PROCESS_COLUMNS)),
    ]
    for label in dict.fromkeys(row["label"] for row in rows):
        mine = [row for row in rows if row["label"] == label]
        processes = "".join(f" {mean_of(mine, f'{key}_mb') / 1024:.2f} / {mean_of(mine, f'{key}_cmprs_mb') / 1024:.2f} |" for key in PROCESS_COLUMNS)
        lines.append(
            f"| {label} | {len(mine)} | {mean_of(mine, 'swap_used_mb') / 1024:.2f} | {rate_of(mine, 'swapins'):.1f} | {rate_of(mine, 'swapouts'):.1f} "
            f"| {rate_of(mine, 'pageins'):.1f} | {mean_of(mine, 'pressure_free_percent'):.1f} | {pages_to_gb(mean_of(mine, 'wired_pages')):.1f} "
            f"| {pages_to_gb(mean_of(mine, 'compressor_pages')):.2f} |" + processes
        )
    return "\n".join(lines)


def mean_of(rows: list[dict[str, str]], field: str) -> float:
    values = [float(row[field]) for row in rows if row.get(field) not in (None, "")]
    return statistics.fmean(values) if values else 0.0


def pages_to_gb(pages: float) -> float:
    return pages * PAGE_BYTES / 1024**3


def rate_of(rows: list[dict[str, str]], counter: str) -> float:
    """MB per minute from a cumulative page counter, over consecutive samples only: a setup's rows come in more than one stretch."""
    pages, seconds = 0.0, 0.0
    for earlier, later in zip(rows, rows[1:]):
        gap = float(later["epoch"]) - float(earlier["epoch"])
        if 0 < gap <= 30:
            pages += float(later[counter]) - float(earlier[counter])
            seconds += gap
    return pages * PAGE_BYTES / 1024**2 / (seconds / 60) if seconds else 0.0
