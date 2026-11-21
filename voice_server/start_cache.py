"""What OmniVoice makes at start-up, kept on disk so the next start reuses it: the JARVIS clip's encoded tokens, and the audio of every filler and
notice phrase.

Each is filed under a fingerprint of everything that shapes it, so nothing stale is ever replayed. The tokens depend on the clip, how much of it
is encoded, the model at its revision, and the installed mlx-audio and MLX. A filler's audio also depends on the clip's transcript, the steps, the
language and the loudness, and on its own text as spoken, after the pronunciation dictionary respells it. Change any of these and that part is
made again; anything no longer used is deleted. The cache sits outside the checkout, so a deploy never carries generated audio.
"""

import hashlib
import os
import shutil
from importlib.metadata import version
from pathlib import Path

import numpy as np

from voice_server.settings import OmniVoiceSettings

VOICE_CACHE_DIR = Path.home() / "Library" / "Caches" / "studio-assistant" / "voice"
ENGINE_PACKAGES = ("mlx-audio", "mlx")
REFERENCES_FOLDER = "references"
FILLERS_FOLDER = "fillers"


def installed_engine() -> str:
    return " ".join(f"{package}=={version(package)}" for package in ENGINE_PACKAGES)


def digest(*parts: str | bytes) -> str:
    hasher = hashlib.sha256()
    for part in parts:
        hasher.update(part if isinstance(part, bytes) else part.encode())
        hasher.update(b"\0")
    return hasher.hexdigest()[:24]


def save_array(path: Path, array: np.ndarray) -> None:
    """Written beside its final name and renamed into place, so a start that is killed midway never leaves half a file to be read next time."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f".{path.name}.partial")
    with partial.open("wb") as file:
        np.save(file, array)
    os.replace(partial, path)


class StartCache:
    def __init__(self, settings: OmniVoiceSettings, root: Path, engine: str) -> None:
        self.root = root
        clip = settings.reference_clip_path.read_bytes()
        self.reference_key = digest(clip, str(settings.reference_max_seconds), settings.source, settings.revision, engine)
        self.speech_key = digest(self.reference_key, settings.reference_text, str(settings.steps), settings.language, str(settings.loudness_dbfs))

    @classmethod
    def for_this_mac(cls, settings: OmniVoiceSettings) -> "StartCache":
        return cls(settings, VOICE_CACHE_DIR, installed_engine())

    @property
    def reference_tokens_path(self) -> Path:
        return self.root / REFERENCES_FOLDER / f"{self.reference_key}.npy"

    @property
    def fillers_dir(self) -> Path:
        return self.root / FILLERS_FOLDER / self.speech_key

    def saved_reference_tokens(self) -> np.ndarray | None:
        return np.load(self.reference_tokens_path) if self.reference_tokens_path.exists() else None

    def save_reference_tokens(self, tokens: np.ndarray) -> None:
        save_array(self.reference_tokens_path, tokens)

    def filler_path(self, spoken: str) -> Path:
        return self.fillers_dir / f"{digest(spoken)}.npy"

    def saved_filler(self, spoken: str) -> np.ndarray | None:
        path = self.filler_path(spoken)
        return np.load(path) if path.exists() else None

    def save_filler(self, spoken: str, audio: np.ndarray) -> None:
        save_array(self.filler_path(spoken), audio)

    def forget_all_but(self, spoken_fillers: set[str]) -> None:
        """Deletes the saved fillers no current phrase speaks, and everything filed under another fingerprint."""
        kept = {self.filler_path(spoken) for spoken in spoken_fillers} | {self.reference_tokens_path}
        for path in [*self.fillers_dir.glob("*.npy"), *(self.root / REFERENCES_FOLDER).glob("*.npy")]:
            if path not in kept:
                path.unlink()
        for folder in (self.root / FILLERS_FOLDER).glob("*"):
            if folder != self.fillers_dir:
                shutil.rmtree(folder)
