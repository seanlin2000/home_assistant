"""Run the speech lab on the laptop: `uv sync --group speech-lab`, then `uv run speech-lab`, and open http://127.0.0.1:8795."""

import logging

import uvicorn

from speech_lab.app import build_app
from speech_lab.mlx_engine import MlxSpeechEngine
from speech_lab.settings import LAB_HOST, LAB_PORT


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(build_app(MlxSpeechEngine()), host=LAB_HOST, port=LAB_PORT)


if __name__ == "__main__":
    main()
