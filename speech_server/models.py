"""The two models, loaded once at their pinned revisions: Qwen3-ASR for speech to text and Qwen3-TTS CustomVoice for text to speech. Load and call them
on one thread only (worker.ModelThread): MLX does not allow two calls at once, and keeps state per thread."""

import gc
import logging
import time
from collections.abc import Iterator

import mlx.core as mx
import mlx.nn as nn
import numpy as np
from mlx_audio.stt.utils import load as load_recognizer
from mlx_audio.tts.utils import load as load_voice_model

from speech_server.audio import RECOGNIZER_SAMPLE_RATE
from speech_server.settings import SpeechSettings, VoiceSettings
from speech_server.text import max_audio_tokens

BYTES_PER_MIB = 2**20
BYTES_PER_GIB = 2**30
QUANTIZATION_GROUP_SIZE = 64
WARM_UP_SENTENCE = "Hello there."

_LOGGER = logging.getLogger(__name__)


class QwenSpeechModels:
    def __init__(self, settings: SpeechSettings) -> None:
        self._settings = settings
        mx.set_cache_limit(settings.server.mlx_cache_limit_mib * BYTES_PER_MIB)
        if settings.server.mlx_wired_limit_mib:
            mx.set_wired_limit(settings.server.mlx_wired_limit_mib * BYTES_PER_MIB)
        self._recognizer = load_recognizer(settings.asr.source, revision=settings.asr.revision)
        self._voice_model = load_voice_model(settings.tts.source, revision=settings.tts.revision)
        slim_voice_model(self._voice_model, settings.tts)
        _LOGGER.info("models loaded: %.2f GiB of MLX memory in use", mx.get_active_memory() / BYTES_PER_GIB)

    def warm_up(self) -> None:
        """The first call of each model compiles its kernels, which would otherwise land on the first question of the day. What the recognizer makes
        of a second of silence does not matter here."""
        for _ in self.speak(WARM_UP_SENTENCE, self._settings.tts.default_voice):
            pass
        self.transcribe(np.zeros(RECOGNIZER_SAMPLE_RATE, dtype=np.float32))
        _LOGGER.info("warmed up: %.2f GiB peak", mx.get_peak_memory() / BYTES_PER_GIB)

    def speak(self, sentence: str, voice: str) -> Iterator[np.ndarray]:
        """Pieces of float audio at the voice model's sample rate, each yielded as soon as it is decoded."""
        tts = self._settings.tts
        started = time.perf_counter()
        pieces = self._voice_model.generate(
            text=sentence,
            voice=voice,
            lang_code=tts.voices[voice],
            max_tokens=max_audio_tokens(sentence, tts.speech_length),
            stream=True,
            streaming_interval=tts.streaming_interval_seconds,
        )
        for index, piece in enumerate(pieces):
            if index == 0:
                _LOGGER.info("first audio after %.3f s: %s", time.perf_counter() - started, sentence)
            yield np.array(piece.audio, dtype=np.float32)

    def transcribe(self, audio: np.ndarray) -> str:
        asr = self._settings.asr
        started = time.perf_counter()
        output = self._recognizer.generate(audio, language=asr.language or None, system_prompt=asr.context or None)
        text = output.text.strip()
        _LOGGER.info("transcribed %.1f s of audio in %.3f s: %s", len(audio) / RECOGNIZER_SAMPLE_RATE, time.perf_counter() - started, text)
        return text

    @property
    def sample_rate(self) -> int:
        return self._voice_model.sample_rate


def slim_voice_model(voice_model: nn.Module, tts: VoiceSettings) -> None:
    """Drops what a CustomVoice model never uses and shrinks what it keeps. The speech tokenizer's encoder only turns reference recordings into codes
    for voice cloning, which preset speakers never need. The quantized embedding is evaluated at once: until then MLX keeps the bfloat16 table it is
    computed from."""
    voice_model.speech_tokenizer.encoder_model = None
    if tts.text_embedding_bits:
        nn.quantize(voice_model.talker.model, group_size=QUANTIZATION_GROUP_SIZE, bits=tts.text_embedding_bits, class_predicate=is_text_embedding)
        mx.eval(voice_model.talker.parameters())
    gc.collect()
    mx.clear_cache()


def is_text_embedding(path: str, module: nn.Module) -> bool:
    return path == "text_embedding" and isinstance(module, nn.Embedding)
