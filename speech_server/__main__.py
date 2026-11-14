"""Run the speech server: `scripts/speech_server.sh` (which builds .venv-speech first), or `.venv-speech/bin/speech-server`.

speech-server                                   # the ports in config/speech.toml: 10300 and 10210, Whisper's and Kokoro's
speech-server --asr-port 10301 --tts-port 10211 # beside today's services, for trying it out
"""

import argparse
import asyncio
import logging
from pathlib import Path

from speech_server.models import QwenSpeechModels
from speech_server.server import serve
from speech_server.settings import SPEECH_CONFIG_PATH, SpeechSettings, load_speech_settings
from speech_server.worker import ModelThread, SpeechWorker


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Qwen3-ASR and Qwen3-TTS over Wyoming, in one MLX process.")
    parser.add_argument("--config", type=Path, default=SPEECH_CONFIG_PATH)
    parser.add_argument("--host", help="overrides [server] host")
    parser.add_argument("--asr-port", type=int, help="overrides [server] asr_port")
    parser.add_argument("--tts-port", type=int, help="overrides [server] tts_port")
    return parser.parse_args()


def settings_with_overrides(arguments: argparse.Namespace) -> SpeechSettings:
    settings = load_speech_settings(arguments.config)
    overrides = {"host": arguments.host, "asr_port": arguments.asr_port, "tts_port": arguments.tts_port}
    server = settings.server.model_copy(update={key: value for key, value in overrides.items() if value is not None})
    return settings.model_copy(update={"server": server})


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = settings_with_overrides(parse_args())
    thread = ModelThread()
    models = thread.run(QwenSpeechModels, settings)
    thread.run(models.warm_up)
    logging.getLogger(__name__).info("listening: speech to text on %s:%d, text to speech on %s:%d", settings.server.host, settings.server.asr_port, settings.server.host, settings.server.tts_port)
    asyncio.run(serve(SpeechWorker(models, thread), settings))


if __name__ == "__main__":
    main()
