"""The typed contents of config/voice.toml. Every table forbids unknown keys, so a misspelt setting stops the voice instead of being ignored."""

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import Field

from serving.settings import PROJECT_DIR, StrictModel
from utils.engine_override_utils import OVERRIDES_DIR, EngineOverride

VOICE_CONFIG_PATH = PROJECT_DIR / "config" / "voice.toml"
# A file holding "omnivoice" or "kokoro" overrides [voice] engine on this Mac only, as the engine file does for serving.
VOICE_ENGINE_OVERRIDE_PATH = OVERRIDES_DIR / "voice_engine"
VoiceEngine = Literal["omnivoice", "kokoro"]
VOICE_ENGINES: tuple[VoiceEngine, ...] = ("omnivoice", "kokoro")


class OmniVoiceSettings(StrictModel):
    source: str
    revision: str
    reference_clip: str
    reference_text: str
    reference_max_seconds: float = Field(gt=0)
    steps: int = Field(ge=1)
    language: str
    mlx_cache_limit_mib: int = Field(ge=0)
    mlx_wired_limit_mib: int = Field(ge=0)

    @property
    def reference_clip_path(self) -> Path:
        return PROJECT_DIR / self.reference_clip


class VoiceServerSettings(StrictModel):
    engine: VoiceEngine
    host: str
    port: int
    omnivoice: OmniVoiceSettings


class VoiceSettings(StrictModel):
    voice: VoiceServerSettings


def load_voice_settings(path: Path = VOICE_CONFIG_PATH) -> VoiceSettings:
    with path.open("rb") as handle:
        return VoiceSettings.model_validate(tomllib.load(handle))


def active_voice_engine(settings: VoiceSettings) -> VoiceEngine:
    """The voice this Mac runs: the override file's, when scripts/services.sh wrote one, else voice.toml's."""
    return EngineOverride(path=VOICE_ENGINE_OVERRIDE_PATH, engines=VOICE_ENGINES, reset_command="scripts/services.sh voice-engine default").engine_or(settings.voice.engine)
