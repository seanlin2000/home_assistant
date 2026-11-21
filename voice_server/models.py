"""OmniVoice on mlx-audio, loaded once at its pinned revision, with the JARVIS voice encoded once at start-up. Load and call it on one thread only
(speech_server.worker.ModelThread): MLX does not allow two calls at once, and keeps state per thread."""

import gc
import logging
import os
from pathlib import Path

import mlx.core as mx
import numpy as np
from huggingface_hub import snapshot_download
from mlx_audio.tts.models.omnivoice.utils import create_voice_clone_prompt
from mlx_audio.tts.utils import load_model

from speech_server.wiring import RESIDENCY_REFRESH_VARIABLE, wiring_summary
from voice_server.settings import OmniVoiceSettings

BYTES_PER_MIB = 2**20
BYTES_PER_GIB = 2**30
# Decoding uses only the quantizer, the acoustic decoder and fc2. These four only encode, so once the reference is encoded they are dropped
# (about 309 MiB; a seeded sentence came out bit-identical). Encoding another voice afterwards would need the model loaded again.
ENCODE_ONLY_PARTS = ("acoustic_encoder", "semantic_model", "encoder_semantic", "fc")
WARM_UP_SENTENCE = "Warming up the voice."

_LOGGER = logging.getLogger(__name__)


def download_model(settings: OmniVoiceSettings) -> Path:
    """Into the Hugging Face cache; a revision already there is not fetched again."""
    return Path(snapshot_download(settings.source, revision=settings.revision))


def downloaded_model(settings: OmniVoiceSettings) -> Path:
    """The pinned snapshot's folder, found offline; loading by repository name fetches the Hub's newest revision, which nobody measured."""
    return Path(snapshot_download(settings.source, revision=settings.revision, local_files_only=True))


class OmniVoice:
    def __init__(self, settings: OmniVoiceSettings) -> None:
        self._settings = settings
        pin_memory(settings)
        self._model = load_model(downloaded_model(settings))
        self._reference_tokens = create_voice_clone_prompt(
            str(settings.reference_clip_path),
            tokenizer=self._model.audio_tokenizer,
            max_duration_s=settings.reference_max_seconds,
        )
        free_encoder_parts(self._model.audio_tokenizer)
        _LOGGER.info("model loaded and voice encoded: %.2f GiB of MLX memory in use", mx.get_active_memory() / BYTES_PER_GIB)

    @property
    def sample_rate(self) -> int:
        return self._model.sample_rate

    def warm_up(self) -> None:
        """The first call compiles the model's kernels, which would otherwise land on the first answer of the day."""
        self.synthesize(WARM_UP_SENTENCE)
        _LOGGER.info("warmed up: %.2f GiB peak", mx.get_peak_memory() / BYTES_PER_GIB)

    def synthesize(self, text: str) -> np.ndarray:
        """The text spoken in the JARVIS voice, as float samples at sample_rate. Pass one sentence: OmniVoice makes the whole of it before any
        can play."""
        settings = self._settings
        results = self._model.generate(text=text, ref_tokens=self._reference_tokens, ref_text=settings.reference_text, num_steps=settings.steps, language=settings.language)
        return np.concatenate([np.asarray(result.audio, dtype=np.float32) for result in results])


def pin_memory(settings: OmniVoiceSettings) -> None:
    mx.set_cache_limit(settings.mlx_cache_limit_mib * BYTES_PER_MIB)
    if settings.mlx_wired_limit_mib:
        mx.set_wired_limit(settings.mlx_wired_limit_mib * BYTES_PER_MIB)
        _LOGGER.info(wiring_summary(settings.mlx_wired_limit_mib, os.environ.get(RESIDENCY_REFRESH_VARIABLE)))


def free_encoder_parts(audio_tokenizer: object) -> None:
    for name in ENCODE_ONLY_PARTS:
        setattr(audio_tokenizer, name, None)
    gc.collect()
    mx.clear_cache()
