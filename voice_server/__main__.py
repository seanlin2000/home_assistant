"""OmniVoice from the command line, in .venv-speech: `.venv-speech/bin/voice-server`.

voice-server --download-only                     # fetch the model at its pinned revision and exit
voice-server --say "Good evening." --out a.wav   # speak one sentence in the JARVIS voice into a WAV file, with the production settings
"""

import argparse
import logging
import time
import wave
from pathlib import Path

import numpy as np

from speech_server.audio import PCM_CHANNELS, PCM_WIDTH_BYTES, pcm_bytes
from voice_server.models import OmniVoice, download_model
from voice_server.settings import VOICE_CONFIG_PATH, load_voice_settings

_LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OmniVoice on MLX, with the settings in config/voice.toml.")
    parser.add_argument("--config", type=Path, default=VOICE_CONFIG_PATH)
    action = parser.add_mutually_exclusive_group(required=True)
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


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    arguments = parse_args()
    settings = load_voice_settings(arguments.config).voice.omnivoice
    if arguments.download_only:
        _LOGGER.info("model ready at %s", download_model(settings))
        return
    say(OmniVoice(settings), arguments.say, arguments.out)


if __name__ == "__main__":
    main()
