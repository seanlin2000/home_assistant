"""The engine behind the page: mlx-audio's Qwen3-TTS, OmniVoice and Qwen3-ASR on Apple Silicon.

It keeps at most one voice model and one recognizer loaded, because the laptop has 16 GB. MLX is not safe to call from two threads at once, so
every call holds one lock.
"""

import base64
import io
import json
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import mlx.core as mx
import numpy as np
import soundfile
from huggingface_hub import hf_hub_download, snapshot_download
from huggingface_hub.errors import LocalEntryNotFoundError
from mlx_audio.stt.utils import load_model as load_recognizer
from mlx_audio.tts.utils import load_model as load_voice_model
from mlx_audio.utils import load_audio

from speech_lab.results import Synthesis, SynthesisStats, Transcription, VoiceModelFacts
from speech_lab.settings import OmniVoiceRequest, SpeechRequest, TranscriptionRequest, VoiceModelChoice

RECOGNIZER_SAMPLE_RATE = 16000
BYTES_PER_GIB = 2**30


@dataclass
class LoadedModel:
    repo_id: str
    model: object
    load_seconds: float


class MlxSpeechEngine:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._voice_model: LoadedModel | None = None
        self._recognizer: LoadedModel | None = None

    def describe_voice_model(self, choice: VoiceModelChoice) -> VoiceModelFacts:
        config = json.loads(Path(hf_hub_download(choice.repo_id, "config.json")).read_text())
        talker = config.get("talker_config", {})
        speakers = list((talker.get("spk_id") or {}).keys())
        dialects = {speaker: dialect for speaker, dialect in (talker.get("spk_is_dialect") or {}).items() if dialect}
        languages = ["auto", *(talker.get("codec_language_id") or {}).keys()]
        return VoiceModelFacts(repo_id=choice.repo_id, downloaded=is_downloaded(choice.repo_id), speakers=speakers, dialects=dialects, languages=languages)

    def synthesize(self, request: SpeechRequest) -> Synthesis:
        with self._lock:
            loaded, load_seconds = self._loaded_voice_model(request.repo_id)
            mx.reset_peak_memory()
            with reference_recording(request.reference_audio_wav_base64) as reference_path:
                return synthesized(loaded, qwen_generation_arguments(request, reference_path), load_seconds)

    def synthesize_with_omnivoice(self, request: OmniVoiceRequest) -> Synthesis:
        with self._lock:
            loaded, load_seconds = self._loaded_voice_model(request.repo_id)
            mx.reset_peak_memory()
            with reference_recording(request.reference_audio_wav_base64) as reference_path:
                return synthesized(loaded, omnivoice_generation_arguments(request, reference_path), load_seconds)

    def transcribe(self, request: TranscriptionRequest) -> Transcription:
        with self._lock:
            loaded, load_seconds = self._loaded_recognizer(request.repo_id)
            mx.reset_peak_memory()
            audio = recognizer_audio(request.audio_wav_base64)
            return transcribed(loaded, request, audio, load_seconds)

    def unload(self) -> None:
        with self._lock:
            self._voice_model = None
            self._recognizer = None
            mx.clear_cache()

    def _loaded_voice_model(self, repo_id: str) -> tuple[LoadedModel, float]:
        if self._voice_model and self._voice_model.repo_id == repo_id:
            return self._voice_model, 0.0
        self._voice_model = None  # drop the old one before loading, so two never sit in memory at once
        mx.clear_cache()
        self._voice_model = timed_load(repo_id, load_voice_model)
        return self._voice_model, self._voice_model.load_seconds

    def _loaded_recognizer(self, repo_id: str) -> tuple[LoadedModel, float]:
        if self._recognizer and self._recognizer.repo_id == repo_id:
            return self._recognizer, 0.0
        self._recognizer = None
        mx.clear_cache()
        self._recognizer = timed_load(repo_id, load_recognizer)
        return self._recognizer, self._recognizer.load_seconds


def is_downloaded(repo_id: str) -> bool:
    try:
        snapshot_download(repo_id, local_files_only=True)
    except LocalEntryNotFoundError:
        return False
    return True


def timed_load(repo_id: str, loader: Callable[[str], object]) -> LoadedModel:
    started = time.perf_counter()
    model = loader(repo_id)
    return LoadedModel(repo_id=repo_id, model=model, load_seconds=round(time.perf_counter() - started, 2))


def synthesized(loaded: LoadedModel, generation_arguments: dict, load_seconds: float) -> Synthesis:
    started = time.perf_counter()
    first_audio_seconds = None
    chunks: list[np.ndarray] = []
    sample_rate = 24000
    for result in loaded.model.generate(**generation_arguments):
        first_audio_seconds = first_audio_seconds or time.perf_counter() - started
        chunks.append(np.array(result.audio, dtype=np.float32))
        sample_rate = result.sample_rate
    audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
    stats = SynthesisStats(
        repo_id=loaded.repo_id,
        load_seconds=load_seconds,
        first_audio_seconds=round(first_audio_seconds or 0.0, 3),
        total_seconds=round(time.perf_counter() - started, 3),
        audio_seconds=round(len(audio) / sample_rate, 2),
        chunks=len(chunks),
        peak_memory_gib=round(mx.get_peak_memory() / BYTES_PER_GIB, 2),
    )
    return Synthesis(wav=wav_bytes(audio, sample_rate), stats=stats)


def qwen_generation_arguments(request: SpeechRequest, reference_path: str | None) -> dict:
    """Everything Qwen3-TTS's generate() accepts that changes the voice. `speed` is left out: mlx-audio 0.6.5 takes it and ignores it."""
    arguments = {
        "text": request.text,
        "voice": request.speaker,
        "instruct": request.instruct or None,
        "lang_code": request.language,
        "temperature": request.temperature,
        "top_k": request.top_k,
        "top_p": request.top_p,
        "repetition_penalty": request.repetition_penalty,
        "max_tokens": request.max_tokens,
        "stream": True,
        "streaming_interval": request.streaming_interval,
        "streaming_context_size": request.streaming_context_size,
    }
    if reference_path:
        arguments |= {"ref_audio": reference_path, "ref_text": request.reference_text}
    return arguments


def omnivoice_generation_arguments(request: OmniVoiceRequest, reference_path: str | None) -> dict:
    """OmniVoice spells "not set" as the string "None" for its language and instruct."""
    arguments = {
        "text": request.text,
        "language": request.language or "None",
        "instruct": request.instruct.strip() or "None",
        "duration_s": request.duration_seconds,
        "num_steps": request.num_steps,
        "guidance_scale": request.guidance_scale,
        "class_temperature": request.class_temperature,
        "position_temperature": request.position_temperature,
        "layer_penalty_factor": request.layer_penalty_factor,
        "t_shift": request.t_shift,
    }
    if reference_path:
        arguments |= {"ref_audio": reference_path, "ref_text": request.reference_text, "ref_audio_max_duration_s": request.reference_max_seconds}
    return arguments


def transcribed(loaded: LoadedModel, request: TranscriptionRequest, audio: np.ndarray, load_seconds: float) -> Transcription:
    started = time.perf_counter()
    output = loaded.model.generate(
        audio,
        language=request.language,
        system_prompt=request.context or None,
        temperature=request.temperature,
        top_p=request.top_p,
        top_k=request.top_k,
        min_p=request.min_p,
        repetition_penalty=request.repetition_penalty,
        max_tokens=request.max_tokens,
    )
    language = output.language[0] if isinstance(output.language, list) else output.language
    return Transcription(
        repo_id=loaded.repo_id,
        text=output.text.strip(),
        language=language,
        audio_seconds=round(len(audio) / RECOGNIZER_SAMPLE_RATE, 2),
        load_seconds=load_seconds,
        total_seconds=round(time.perf_counter() - started, 3),
        peak_memory_gib=round(mx.get_peak_memory() / BYTES_PER_GIB, 2),
    )


@contextmanager
def reference_recording(audio_wav_base64: str | None) -> Iterator[str | None]:
    """mlx-audio reads a reference recording from a path and resamples it to 24 kHz itself."""
    if not audio_wav_base64:
        yield None
        return
    with tempfile.NamedTemporaryFile(suffix=".wav") as handle:
        handle.write(base64.b64decode(audio_wav_base64))
        handle.flush()
        yield handle.name


def recognizer_audio(audio_wav_base64: str) -> np.ndarray:
    """The browser records at its own rate (Firefox will not record at 16 kHz), so the recording is resampled here."""
    with reference_recording(audio_wav_base64) as path:
        return np.array(load_audio(path, sample_rate=RECOGNIZER_SAMPLE_RATE), dtype=np.float32)


def wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    soundfile.write(buffer, audio, sample_rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()
