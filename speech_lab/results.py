"""What an engine hands back to the page, and the engine's shape, so the page can be tested without loading a model."""

from typing import Protocol

from pydantic import BaseModel

from speech_lab.settings import OmniVoiceRequest, SpeechRequest, TranscriptionRequest, VoiceModelChoice


class VoiceModelFacts(BaseModel):
    repo_id: str
    downloaded: bool
    speakers: list[str]
    dialects: dict[str, str]
    languages: list[str]


class SynthesisStats(BaseModel):
    repo_id: str
    load_seconds: float  # 0 when the model was already loaded
    first_audio_seconds: float
    total_seconds: float
    audio_seconds: float
    chunks: int  # OmniVoice always returns one
    peak_memory_gib: float


class Synthesis(BaseModel):
    wav: bytes
    stats: SynthesisStats


class Transcription(BaseModel):
    repo_id: str
    text: str
    language: str | None
    audio_seconds: float
    load_seconds: float
    total_seconds: float
    peak_memory_gib: float


class SpeechEngine(Protocol):
    def describe_voice_model(self, choice: VoiceModelChoice) -> VoiceModelFacts: ...

    def synthesize(self, request: SpeechRequest) -> Synthesis: ...

    def synthesize_with_omnivoice(self, request: OmniVoiceRequest) -> Synthesis: ...

    def transcribe(self, request: TranscriptionRequest) -> Transcription: ...

    def unload(self) -> None: ...
