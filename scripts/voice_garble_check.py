"""Does a voice say every word it is given? Stream benchmark answers to a Wyoming voice server as Home Assistant streams them, read the audio back
with Qwen3-ASR (the model and revision in config/speech.toml), line the transcript up against the answer word by word, and flag stretches the
voice lost (four or more written words in a row missing) or invented (four or more heard words that match nothing).

One- and two-word slips are counted but not flagged: they are mostly the recognizer spelling a name its own way. Numbers are left out of the
comparison, since the answer says "31" where the recognizer may write words. Runs in .venv-speech, which has mlx-audio:

    .venv-speech/bin/python scripts/voice_garble_check.py --port 10211 benchmark/results/<run>/<candidate>.jsonl --audio-dir /tmp/garble
"""

import argparse
import asyncio
import difflib
import json
import re
import time
import wave
from pathlib import Path

import numpy as np
from mlx_audio.stt.utils import load, load_audio
from pydantic import BaseModel
from wyoming.audio import AudioChunk, AudioStart
from wyoming.client import AsyncTcpClient
from wyoming.tts import SynthesizeChunk, SynthesizeStart, SynthesizeStop, SynthesizeStopped

from benchmark.records import QuestionResult, read_jsonl
from speech_server.settings import load_speech_settings

RECOGNIZER_SAMPLE_RATE = 16000
FLAGGED_RUN_WORDS = 4
CHARACTERS_PER_DELTA = 8  # about two tokens, as the component streams an answer
WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")
NUMBER_WORDS = set(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty "
    "thirty forty fifty sixty seventy eighty ninety hundred thousand million billion point percent first second third fourth fifth".split()
)


class SpokenAnswer(BaseModel):
    question_id: str
    text: str
    first_audio_seconds: float
    audio_seconds: float
    wav: Path


class Comparison(BaseModel):
    heard: str
    expected_words: int
    matched_words: int
    lost_words: int
    invented_words: int
    slipped_words: int
    flagged: list[dict[str, str]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream benchmark answers to a Wyoming voice and check every word is spoken.")
    parser.add_argument("results", type=Path, help="a benchmark results JSONL")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--audio-dir", type=Path, default=Path("voice_garble_audio"), help="where each answer's WAV is written")
    parser.add_argument("--question", action="append", help="only these question ids (repeatable)")
    return parser.parse_args()


def answers_in(results: Path, questions: list[str] | None) -> dict[str, str]:
    answers = {}
    for result in read_jsonl(results, QuestionResult):
        final_answers = [exchange.final_answer for exchange in result.exchanges if exchange.final_answer]
        if final_answers and (questions is None or result.question_id in questions):
            answers[result.question_id] = final_answers[-1]
    return answers


async def spoken(host: str, port: int, question_id: str, text: str, audio_dir: Path) -> SpokenAnswer:
    """The answer streamed in small deltas; the audio of every utterance, joined, written to one WAV."""
    audio, rate, first_audio_seconds = bytearray(), 0, None
    started = time.perf_counter()
    async with AsyncTcpClient(host, port) as client:
        await client.write_event(SynthesizeStart().event())
        for start in range(0, len(text), CHARACTERS_PER_DELTA):
            await client.write_event(SynthesizeChunk(text=text[start : start + CHARACTERS_PER_DELTA]).event())
        await client.write_event(SynthesizeStop().event())
        while (event := await client.read_event()) is not None and not SynthesizeStopped.is_type(event.type):
            if AudioStart.is_type(event.type):
                rate = AudioStart.from_event(event).rate
            elif AudioChunk.is_type(event.type):
                first_audio_seconds = first_audio_seconds or time.perf_counter() - started
                audio += AudioChunk.from_event(event).audio
    wav = audio_dir / f"{question_id}.wav"
    write_wav(wav, bytes(audio), rate)
    return SpokenAnswer(question_id=question_id, text=text, first_audio_seconds=first_audio_seconds or 0.0, audio_seconds=len(audio) / 2 / rate, wav=wav)


def write_wav(path: Path, audio: bytes, rate: int) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(audio)


def comparable_words(text: str) -> list[str]:
    spaced = text.lower().replace("-", " ").replace("’", "'")
    return [word.removesuffix("'s") for word in WORD.findall(spaced) if word not in NUMBER_WORDS]


def compare(expected_text: str, heard_text: str) -> Comparison:
    expected, heard = comparable_words(expected_text), comparable_words(heard_text)
    matcher = difflib.SequenceMatcher(None, expected, heard, autojunk=False)
    lost, invented, slips, flagged = 0, 0, 0, []
    for operation, expected_start, expected_end, heard_start, heard_end in matcher.get_opcodes():
        missing, extra = expected_end - expected_start, heard_end - heard_start
        lost += missing if operation == "delete" else max(missing - extra, 0) if operation == "replace" else 0
        invented += extra if operation == "insert" else max(extra - missing, 0) if operation == "replace" else 0
        slips += min(missing, extra) if operation == "replace" else 0
        if operation != "equal" and max(missing, extra) >= FLAGGED_RUN_WORDS:
            flagged.append({"written": " ".join(expected[expected_start:expected_end]), "heard": " ".join(heard[heard_start:heard_end])})
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return Comparison(heard=heard_text, expected_words=len(expected), matched_words=matched, lost_words=lost, invented_words=invented, slipped_words=slips, flagged=flagged)


def print_summary(rows: list[tuple[SpokenAnswer, Comparison]]) -> None:
    expected = sum(comparison.expected_words for _, comparison in rows)
    matched = sum(comparison.matched_words for _, comparison in rows)
    print(
        f"{len(rows)} answers, {expected} words: matched {matched / max(expected, 1):.1%}; lost {sum(c.lost_words for _, c in rows)}, invented {sum(c.invented_words for _, c in rows)}, one-for-one slips {sum(c.slipped_words for _, c in rows)}; flagged stretches {sum(len(c.flagged) for _, c in rows)}"
    )
    first_audio = sorted(answer.first_audio_seconds for answer, _ in rows)
    print(f"first audio after the answer's first delta: median {first_audio[len(first_audio) // 2]:.2f} s, slowest {first_audio[-1]:.2f} s")
    for answer, comparison in rows:
        for stretch in comparison.flagged:
            print(f"   {answer.question_id}: written '{stretch['written']}' / heard '{stretch['heard']}'")


def main() -> None:
    arguments = parse_args()
    arguments.audio_dir.mkdir(parents=True, exist_ok=True)
    answers = answers_in(arguments.results, arguments.question)
    spoken_answers = [asyncio.run(spoken(arguments.host, arguments.port, question_id, text, arguments.audio_dir)) for question_id, text in answers.items()]
    asr = load_speech_settings().asr
    recognizer = load(asr.source, revision=asr.revision)
    rows = []
    for answer in spoken_answers:
        heard = recognizer.generate(np.array(load_audio(str(answer.wav), sr=RECOGNIZER_SAMPLE_RATE)), language="English").text.strip()
        rows.append((answer, compare(answer.text, heard)))
    (arguments.audio_dir / "garble.json").write_text(json.dumps([{**answer.model_dump(mode="json"), "comparison": comparison.model_dump()} for answer, comparison in rows], indent=1))
    print_summary(rows)


if __name__ == "__main__":
    main()
