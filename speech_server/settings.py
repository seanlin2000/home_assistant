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
    tts_port: int
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


class SpeechLength(StrictModel):
    minimum_seconds: float = Field(gt=0)
    seconds_per_latin_character: float = Field(gt=0)
    seconds_per_cjk_character: float = Field(gt=0)


class VoiceSettings(StrictModel):
    source: str
    revision: str
    default_voice: str
    gain: float = Field(gt=0)
    streaming_interval_seconds: float = Field(gt=0)
    text_embedding_bits: int
    speech_length: SpeechLength
    voices: dict[str, str]

    @model_validator(mode="after")
    def check_voices(self) -> "VoiceSettings":
        if self.default_voice not in self.voices:
            raise ValueError(f"tts.default_voice {self.default_voice!r} is not one of tts.voices {sorted(self.voices)}")
        unknown = {voice: language for voice, language in self.voices.items() if language not in LANGUAGE_TAGS}
        if unknown:
            raise ValueError(f"tts.voices may only read {sorted(LANGUAGE_TAGS)}: {unknown}")
        if self.text_embedding_bits not in (0, 4, 8):
            raise ValueError("tts.text_embedding_bits must be 0 (leave it), 4 or 8")
        return self

    def voice_or_default(self, requested: str | None) -> str:
        return requested if requested in self.voices else self.default_voice


class SpeechSettings(StrictModel):
    server: ServerSettings
    asr: RecognizerSettings
    tts: VoiceSettings


def load_speech_settings(path: Path = SPEECH_CONFIG_PATH) -> SpeechSettings:
    with path.open("rb") as handle:
        return SpeechSettings.model_validate(tomllib.load(handle))
