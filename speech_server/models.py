"""Qwen3-ASR, loaded once at its pinned revision. Load and call it on one thread only (worker.ModelThread): MLX does not allow two calls at once,
and keeps state per thread."""

import logging
import os
import time
from pathlib import Path

import mlx.core as mx
import numpy as np
from huggingface_hub import snapshot_download
from mlx_audio.stt.utils import load as load_recognizer

from speech_server.audio import RECOGNIZER_SAMPLE_RATE
from speech_server.settings import SpeechSettings
from speech_server.wiring import RESIDENCY_REFRESH_VARIABLE, wiring_summary

BYTES_PER_MIB = 2**20
BYTES_PER_GIB = 2**30

_LOGGER = logging.getLogger(__name__)


def download_model(settings: SpeechSettings) -> Path:
    """Into the Hugging Face cache, where load_recognizer finds it; a revision already there is not fetched again."""
    return Path(snapshot_download(settings.asr.source, revision=settings.asr.revision))


class QwenRecognizer:
    def __init__(self, settings: SpeechSettings) -> None:
        self._settings = settings
        mx.set_cache_limit(settings.server.mlx_cache_limit_mib * BYTES_PER_MIB)
        if settings.server.mlx_wired_limit_mib:
            mx.set_wired_limit(settings.server.mlx_wired_limit_mib * BYTES_PER_MIB)
            _LOGGER.info(wiring_summary(settings.server.mlx_wired_limit_mib, os.environ.get(RESIDENCY_REFRESH_VARIABLE)))
        self._recognizer = load_recognizer(settings.asr.source, revision=settings.asr.revision)
        _LOGGER.info("model loaded: %.2f GiB of MLX memory in use", mx.get_active_memory() / BYTES_PER_GIB)

    def warm_up(self) -> None:
        """The first call compiles the model's kernels, which would otherwise land on the first question of the day. What it makes of a second of
        silence does not matter here."""
        self.transcribe(np.zeros(RECOGNIZER_SAMPLE_RATE, dtype=np.float32))
        _LOGGER.info("warmed up: %.2f GiB peak", mx.get_peak_memory() / BYTES_PER_GIB)

    def transcribe(self, audio: np.ndarray) -> str:
        asr = self._settings.asr
        started = time.perf_counter()
        output = self._recognizer.generate(audio, language=asr.language or None, system_prompt=asr.context or None)
        text = output.text.strip()
        _LOGGER.info("transcribed %.1f s of audio in %.3f s: %s", len(audio) / RECOGNIZER_SAMPLE_RATE, time.perf_counter() - started, text)
        return text
