"""The OmniVoice voice server, in .venv-speech: `.venv-speech/bin/voice-server`.

voice-server                                     # serve Wyoming text to speech on the port in config/voice.toml: 10210, Kokoro's
voice-server --port 10211                        # beside the running voice, for trying a change out
voice-server --download-only                     # fetch the model at its pinned revision and exit
voice-server --say "Good evening." --out a.wav   # speak one sentence in the JARVIS voice into a WAV file, with the production settings
"""

import argparse
import asyncio
import logging
import time
import wave
from pathlib import Path

import numpy as np

from assistant_service.settings import load_harness_config
from serving.settings import load_serving_config
from speech_server.audio import PCM_CHANNELS, PCM_WIDTH_BYTES, pcm_bytes
from speech_server.worker import ModelThread
from utils.pronunciation_utils import LivePronunciations, PronunciationStore
from voice_server.handlers import JARVIS, OMNIVOICE
from voice_server.models import OmniVoice, download_model
from voice_server.server import serve
from voice_server.settings import VOICE_CONFIG_PATH, VoiceSettings, load_voice_settings
from voice_server.speaker import PieceFinish, SentenceSpeaker
from voice_server.start_cache import StartCache

_LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OmniVoice on MLX, with the settings in config/voice.toml.")
    parser.add_argument("--config", type=Path, default=VOICE_CONFIG_PATH)
    parser.add_argument("--port", type=int, help="overrides [voice] port")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--download-only", action="store_true", help="download the model at its pinned revision, then exit")
    action.add_argument("--say", metavar="TEXT", help="speak TEXT into the --out file")
    parser.add_argument("--out", type=Path, default=Path("voice.wav"), help="where --say writes its WAV (default voice.wav)")
    return parser.parse_args()


def write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(PCM_CHANNELS)
        wav.setsampwidth(PCM_WIDTH_BYTES)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm_bytes(samples))


def say(voice: OmniVoice, text: str, out: Path) -> None:
    voice.warm_up()
    started = time.perf_counter()
    samples = voice.synthesize(text)
    make_seconds = time.perf_counter() - started
    write_wav(out, samples, voice.sample_rate)
    _LOGGER.info("%d characters -> %.2f s of audio in %.2f s: %s", len(text), len(samples) / voice.sample_rate, make_seconds, out)


def serve_voice(settings: VoiceSettings) -> None:
    thread = ModelThread()
    cache = StartCache.for_this_mac(settings.voice.omnivoice)
    voice = thread.run(OmniVoice, settings.voice.omnivoice, cache)
    thread.run(voice.warm_up)
    speaker = SentenceSpeaker(voice, thread, LivePronunciations(PronunciationStore(OMNIVOICE, JARVIS)), PieceFinish.from_settings(settings.voice.omnivoice))
    speaker.make_ahead(load_harness_config().policy(load_serving_config()).every_filler_phrase, cache)
    _LOGGER.info("listening: text to speech on %s:%d", settings.voice.host, settings.voice.port)
    asyncio.run(serve(speaker, settings))


def settings_with_port(arguments: argparse.Namespace) -> VoiceSettings:
    settings = load_voice_settings(arguments.config)
    if arguments.port is None:
        return settings
    return settings.model_copy(update={"voice": settings.voice.model_copy(update={"port": arguments.port})})


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    arguments = parse_args()
    settings = settings_with_port(arguments)
    if arguments.download_only:
        _LOGGER.info("model ready at %s", download_model(settings.voice.omnivoice))
    elif arguments.say:
        say(OmniVoice(settings.voice.omnivoice, StartCache.for_this_mac(settings.voice.omnivoice)), arguments.say, arguments.out)
    else:
        serve_voice(settings)


if __name__ == "__main__":
    main()
