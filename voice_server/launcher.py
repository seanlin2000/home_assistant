"""The voice agent's launcher, in .venv: `voice launch` starts whichever engine config/voice.toml (or this Mac's override) names and replaces
itself with it, so launchd supervises the server directly and switching engine is a restart. It never imports MLX: OmniVoice runs from
.venv-speech, Kokoro from .venv.

voice launch     # exec the active engine's server on [voice] host and port
voice engine     # print the active engine: omnivoice or kokoro
voice port       # print the port the voice listens on
voice check      # exit 1, saying why, when the active engine could not start: its model or reference clip missing
voice handoff    # after a switch: wait for the voice, then have Home Assistant re-read it and drop replies cached in the old voice
"""

import argparse
import os
import sys
from pathlib import Path

from huggingface_hub import snapshot_download
from huggingface_hub.errors import LocalEntryNotFoundError

from ops import voice_handoff
from serving.settings import PROJECT_DIR
from voice_server.settings import VoiceSettings, active_voice_engine, load_voice_settings

OMNIVOICE_SERVER = PROJECT_DIR / ".venv-speech" / "bin" / "voice-server"
KOKORO_SERVER = PROJECT_DIR / ".venv" / "bin" / "kokoro-server"
KOKORO_MODEL_FILE = "kokoro-v1_0.pth"


def server_command(settings: VoiceSettings) -> list[str]:
    """The program and arguments of the active engine's server."""
    if active_voice_engine(settings) == "omnivoice":
        return [str(OMNIVOICE_SERVER)]
    voice, kokoro = settings.voice, settings.voice.kokoro
    return [
        str(KOKORO_SERVER),
        *("--uri", f"tcp://{voice.host}:{voice.port}", "--voice", kokoro.voice, "--data-dir", str(kokoro.data_path)),
        *("--streaming", "--volume", f"{kokoro.volume:g}", "--device", kokoro.device),
    ]


def missing_for_launch(settings: VoiceSettings) -> list[str]:
    """What the active engine needs on this Mac and does not have."""
    if active_voice_engine(settings) == "kokoro":
        model = settings.voice.kokoro.data_path / KOKORO_MODEL_FILE
        return [] if model.exists() else [f"Kokoro's model {model} (scripts/services.sh install fetches it)"]
    omnivoice = settings.voice.omnivoice
    missing = [] if OMNIVOICE_SERVER.exists() else [f"{OMNIVOICE_SERVER} (scripts/speech_env.sh builds it)"]
    missing += [] if omnivoice.reference_clip_path.exists() else [f"the reference clip {omnivoice.reference_clip_path}"]
    return missing + ([] if omnivoice_model_downloaded(settings) else [f"{omnivoice.source} at {omnivoice.revision[:7]} (voice-server --download-only fetches it)"])


def omnivoice_model_downloaded(settings: VoiceSettings) -> bool:
    try:
        snapshot_download(settings.voice.omnivoice.source, revision=settings.voice.omnivoice.revision, local_files_only=True)
    except LocalEntryNotFoundError:
        return False
    return True


def launch(settings: VoiceSettings) -> None:
    command = server_command(settings)
    print(f"voice: starting {active_voice_engine(settings)}: {' '.join(command)}", flush=True)
    os.execv(command[0], command)


def check(settings: VoiceSettings) -> int:
    missing = missing_for_launch(settings)
    for item in missing:
        print(f"voice: {active_voice_engine(settings)} cannot start without {item}", file=sys.stderr)
    if not missing:
        print(f"voice: {active_voice_engine(settings)} is ready to launch")
    return 1 if missing else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start or inspect the voice that speaks the answers.")
    parser.add_argument("command", choices=["launch", "engine", "port", "check", "handoff"])
    parser.add_argument("--config", type=Path, default=None, help="another voice.toml (default config/voice.toml)")
    arguments = parser.parse_args(argv)
    settings = load_voice_settings(arguments.config) if arguments.config else load_voice_settings()
    if arguments.command == "launch":
        launch(settings)
    elif arguments.command == "engine":
        print(active_voice_engine(settings))
    elif arguments.command == "port":
        print(settings.voice.port)
    elif arguments.command == "handoff":
        return voice_handoff.main()
    return check(settings) if arguments.command == "check" else 0


if __name__ == "__main__":
    sys.exit(main())
