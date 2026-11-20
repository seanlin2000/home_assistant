"""What the page may ask for: every setting mlx-audio's Qwen3-TTS and OmniVoice accept, and every setting Qwen3-ASR accepts.

The bounds are the ones the page offers, not the library's; the library itself accepts any float.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

LAB_HOST = "127.0.0.1"
LAB_PORT = 8795
MODEL_OWNER = "mlx-community"
VoiceVariant = Literal["CustomVoice", "VoiceDesign", "Base"]
VoiceSize = Literal["1.7B", "0.6B"]
Precision = Literal["8bit", "bf16"]
RecognizerSize = Literal["1.7B", "0.6B"]
VARIANTS_WITHOUT_A_SMALL_SIZE = frozenset({"VoiceDesign"})
OMNIVOICE_REPO_ID = f"{MODEL_OWNER}/OmniVoice-bf16"


class ReferenceRecording(BaseModel):
    """A recording of the voice to clone, with the words spoken in it."""

    reference_audio_wav_base64: str | None = None
    reference_text: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def check_reference_has_its_words(self) -> "ReferenceRecording":
        if self.reference_audio_wav_base64 and not self.reference_text.strip():
            raise ValueError("a reference recording needs the words spoken in it")
        return self


class VoiceModelChoice(BaseModel):
    variant: VoiceVariant = "CustomVoice"
    size: VoiceSize = "1.7B"
    precision: Precision = "8bit"

    @model_validator(mode="after")
    def check_size_exists(self) -> "VoiceModelChoice":
        if self.size == "0.6B" and self.variant in VARIANTS_WITHOUT_A_SMALL_SIZE:
            raise ValueError(f"{self.variant} comes only in 1.7B")
        return self

    @property
    def repo_id(self) -> str:
        return f"{MODEL_OWNER}/Qwen3-TTS-12Hz-{self.size}-{self.variant}-{self.precision}"


class SpeechRequest(VoiceModelChoice, ReferenceRecording):
    """One synthesis. `instruct` is the style or emotion for CustomVoice and the voice's description for VoiceDesign; Base ignores it.
    `reference_audio_wav_base64` with `reference_text` clones a voice on Base."""

    text: str = Field(min_length=1, max_length=2000)
    language: str = "auto"
    speaker: str | None = None
    instruct: str = Field(default="", max_length=1000)
    temperature: float = Field(default=0.9, ge=0.0, le=2.0)
    top_k: int = Field(default=50, ge=0, le=1000)
    top_p: float = Field(default=1.0, gt=0.0, le=1.0)
    repetition_penalty: float = Field(default=1.05, ge=1.0, le=3.0)
    max_tokens: int = Field(default=4096, ge=64, le=8192)
    streaming_interval: float = Field(default=0.32, ge=0.08, le=4.0)
    streaming_context_size: int = Field(default=25, ge=0, le=200)

    @model_validator(mode="after")
    def check_variant_needs(self) -> "SpeechRequest":
        if self.variant == "CustomVoice" and not self.speaker:
            raise ValueError("CustomVoice needs a speaker")
        if self.variant == "VoiceDesign" and not self.instruct.strip():
            raise ValueError("VoiceDesign needs a description of the voice")
        return self


class OmniVoiceRequest(ReferenceRecording):
    """One OmniVoice synthesis. `instruct` is comma-separated voice attributes, at most one per category (catalog.OMNIVOICE_ATTRIBUTES); empty lets
    the model pick a voice. `language` is a BCP-47 tag such as en or zh; empty detects it. A reference recording clones its voice, and attributes
    still apply on top. OmniVoice is a diffusion model: `num_steps` trades time for quality, and the clip arrives all at once, not streamed."""

    text: str = Field(min_length=1, max_length=2000)
    language: str = Field(default="", max_length=16)
    instruct: str = Field(default="", max_length=500)
    duration_seconds: float | None = Field(default=None, gt=0.5, le=120.0)
    num_steps: int = Field(default=32, ge=4, le=128)
    guidance_scale: float = Field(default=2.0, ge=0.0, le=10.0)
    class_temperature: float = Field(default=0.0, ge=0.0, le=5.0)
    position_temperature: float = Field(default=5.0, ge=0.0, le=20.0)
    layer_penalty_factor: float = Field(default=5.0, ge=0.0, le=20.0)
    t_shift: float = Field(default=0.1, ge=0.0, le=1.0)
    reference_max_seconds: float = Field(default=10.0, ge=1.0, le=30.0)

    @property
    def repo_id(self) -> str:
        return OMNIVOICE_REPO_ID


class TranscriptionRequest(BaseModel):
    """One recognition. `context` is Qwen3-ASR's system prompt: names and terms that bias what it hears."""

    audio_wav_base64: str = Field(min_length=1)
    size: RecognizerSize = "1.7B"
    language: str | None = None
    context: str = Field(default="", max_length=2000)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, gt=0.0, le=1.0)
    top_k: int = Field(default=0, ge=0, le=1000)
    min_p: float = Field(default=0.0, ge=0.0, le=1.0)
    repetition_penalty: float | None = Field(default=None, ge=1.0, le=3.0)
    max_tokens: int = Field(default=1024, ge=16, le=8192)

    @property
    def repo_id(self) -> str:
        return f"{MODEL_OWNER}/Qwen3-ASR-{self.size}-8bit"
