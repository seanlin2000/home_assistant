"""The typed contents of config/speech.toml. Every table forbids unknown keys, so a misspelt setting stops the server instead of being ignored."""

import tomllib
from pathlib import Path

from pydantic import Field, model_validator

from serving.settings import StrictModel

SPEECH_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "speech.toml"
# Qwen3's language names, and the BCP-47 tags Home Assistant matches a pipeline's language against.
LANGUAGE_TAGS = {"English": "en", "Chinese": "zh"}


class ServerSettings(StrictModel):
    host: str
    asr_port: int
    mlx_cache_limit_mib: int = Field(ge=0)
    mlx_wired_limit_mib: int = Field(ge=0)


class RecognizerSettings(StrictModel):
    source: str
    revision: str
    language: str
    context: str
    speech_floor_dbfs: float = Field(lt=0)

    @model_validator(mode="after")
    def check_language_is_known(self) -> "RecognizerSettings":
        if self.language and self.language not in LANGUAGE_TAGS:
            raise ValueError(f"asr.language must be empty or one of {sorted(LANGUAGE_TAGS)}, not {self.language!r}")
        return self

    @property
    def language_tags(self) -> list[str]:
        return [LANGUAGE_TAGS[self.language]] if self.language else list(LANGUAGE_TAGS.values())


class SpeechSettings(StrictModel):
    server: ServerSettings
    asr: RecognizerSettings


def load_speech_settings(path: Path = SPEECH_CONFIG_PATH) -> SpeechSettings:
    with path.open("rb") as handle:
        return SpeechSettings.model_validate(tomllib.load(handle))
