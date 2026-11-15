"""Kokoro text-to-speech over Wyoming with the model loaded once.

wyoming-kokoro-torch builds a fresh KModel and KPipeline for every client connection, and Home Assistant opens a new connection for every
sentence it synthesizes (and for every capability check). On this machine that costs one to two seconds before the first audio sample, which
is the whole latency budget for the filler sentence. This entry point runs the upstream server unchanged except that the model and the
per-language pipeline are shared across connections, and that each sentence is respelled from the voice's pronunciation dictionary before Kokoro
reads it (utils/pronunciation_utils.py). Only what Kokoro reads changes: the harness and Home Assistant keep the text as the model wrote it.

    kokoro-server --uri tcp://0.0.0.0:10210 --voice bm_fable --data-dir ~/.cache/wyoming-kokoro --streaming --device cpu
"""

import asyncio
import functools
import logging
from typing import Any

from wyoming.tts import Synthesize
from wyoming_kokoro_torch import handler as kokoro_handler
from wyoming_kokoro_torch.__main__ import main as upstream_main

from utils.pronunciation_utils import LivePronunciations, PronunciationStore

KOKORO = "kokoro"

_ORIGINAL_MODEL = kokoro_handler.KModel
_ORIGINAL_PIPELINE = kokoro_handler.KPipeline
_ORIGINAL_HANDLE_SYNTHESIZE = kokoro_handler.KokoroEventHandler._handle_synthesize
_LOGGER = logging.getLogger(__name__)


@functools.lru_cache(maxsize=None)
def shared_model(model: str, config: str) -> Any:
    return _ORIGINAL_MODEL(model=model, config=config)


@functools.lru_cache(maxsize=None)
def shared_pipeline(lang_code: str, model_id: int) -> Any:
    return _ORIGINAL_PIPELINE(lang_code, model=_MODELS_BY_ID[model_id])


_MODELS_BY_ID: dict[int, Any] = {}


class SharedKModel:
    """Stands in for kokoro.KModel: same constructor, returns the one cached instance. `.to(device)` and `.eval()` are cheap on an already-moved model."""

    def __new__(cls, model: str, config: str) -> Any:
        instance = shared_model(model, config)
        _MODELS_BY_ID[id(instance)] = instance
        return instance


class SharedKPipeline:
    def __new__(cls, lang_code: str, model: Any = None) -> Any:
        return shared_pipeline(lang_code, id(model))


@functools.lru_cache(maxsize=None)
def pronunciations_for(voice: str) -> LivePronunciations:
    return LivePronunciations(PronunciationStore(KOKORO, voice))


async def handle_synthesize_respelled(handler: Any, synthesize: Synthesize, send_start: bool = True, send_stop: bool = True) -> bool:
    """Upstream's _handle_synthesize, given one sentence at a time (its sentence splitter has already run), with the sentence respelled."""
    voice = synthesize.voice.name if synthesize.voice and synthesize.voice.name else handler.cli_args.voice
    pronunciations = pronunciations_for(voice)
    pronunciations.refresh()
    respelled = pronunciations.matcher.respelled(synthesize.text)
    if respelled != synthesize.text:
        _LOGGER.info("respelled for %s: %r -> %r", voice, synthesize.text, respelled)
    return await _ORIGINAL_HANDLE_SYNTHESIZE(handler, Synthesize(text=respelled, voice=synthesize.voice), send_start, send_stop)


def main() -> None:
    kokoro_handler.KModel = SharedKModel
    kokoro_handler.KPipeline = SharedKPipeline
    kokoro_handler.KokoroEventHandler._handle_synthesize = handle_synthesize_respelled
    asyncio.run(upstream_main())


if __name__ == "__main__":
    main()
