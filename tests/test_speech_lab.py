import base64
import json

import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient

from speech_lab.app import STATS_HEADER, build_app
from speech_lab.results import Synthesis, SynthesisStats, Transcription, VoiceModelFacts
from speech_lab.settings import OMNIVOICE_REPO_ID, OmniVoiceRequest, SpeechRequest, TranscriptionRequest, VoiceModelChoice

FAKE_WAV = b"RIFF fake wav"


class FakeEngine:
    def __init__(self) -> None:
        self.speech_requests: list[SpeechRequest] = []
        self.omnivoice_requests: list[OmniVoiceRequest] = []
        self.transcription_requests: list[TranscriptionRequest] = []
        self.unloaded = False

    def describe_voice_model(self, choice: VoiceModelChoice) -> VoiceModelFacts:
        return VoiceModelFacts(repo_id=choice.repo_id, downloaded=True, speakers=["ryan", "dylan"], dialects={"dylan": "beijing_dialect"}, languages=["auto", "english"])

    def synthesize(self, request: SpeechRequest) -> Synthesis:
        self.speech_requests.append(request)
        stats = SynthesisStats(repo_id=request.repo_id, load_seconds=0.0, first_audio_seconds=0.1, total_seconds=1.0, audio_seconds=2.0, chunks=3, peak_memory_gib=3.1)
        return Synthesis(wav=FAKE_WAV, stats=stats)

    def synthesize_with_omnivoice(self, request: OmniVoiceRequest) -> Synthesis:
        self.omnivoice_requests.append(request)
        stats = SynthesisStats(repo_id=request.repo_id, load_seconds=5.0, first_audio_seconds=9.0, total_seconds=9.0, audio_seconds=12.0, chunks=1, peak_memory_gib=3.4)
        return Synthesis(wav=FAKE_WAV, stats=stats)

    def transcribe(self, request: TranscriptionRequest) -> Transcription:
        self.transcription_requests.append(request)
        return Transcription(repo_id=request.repo_id, text="hello", language="English", audio_seconds=1.0, load_seconds=0.0, total_seconds=0.2, peak_memory_gib=2.0)

    def unload(self) -> None:
        self.unloaded = True


def lab_client() -> tuple[TestClient, FakeEngine]:
    engine = FakeEngine()
    return TestClient(build_app(engine)), engine


def test_the_repo_follows_the_variant_size_and_precision() -> None:
    assert VoiceModelChoice(variant="VoiceDesign").repo_id == "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit"
    assert VoiceModelChoice(variant="Base", size="0.6B", precision="bf16").repo_id == "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16"
    assert TranscriptionRequest(audio_wav_base64="eA==", size="0.6B").repo_id == "mlx-community/Qwen3-ASR-0.6B-8bit"


def test_each_variant_is_refused_without_what_it_needs() -> None:
    with pytest.raises(ValidationError, match="only in 1.7B"):
        VoiceModelChoice(variant="VoiceDesign", size="0.6B")
    with pytest.raises(ValidationError, match="needs a speaker"):
        SpeechRequest(text="Hi", variant="CustomVoice")
    with pytest.raises(ValidationError, match="description of the voice"):
        SpeechRequest(text="Hi", variant="VoiceDesign")
    with pytest.raises(ValidationError, match="words spoken in it"):
        SpeechRequest(text="Hi", variant="Base", reference_audio_wav_base64="eA==")


def test_speaking_returns_the_audio_with_its_numbers_in_a_header() -> None:
    client, engine = lab_client()
    response = client.post("/api/speak", json={"text": "Hi", "speaker": "ryan", "instruct": "Very happy.", "temperature": 0.7})

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == FAKE_WAV
    assert json.loads(response.headers[STATS_HEADER])["first_audio_seconds"] == 0.1
    assert engine.speech_requests[0].instruct == "Very happy." and engine.speech_requests[0].temperature == 0.7


def test_a_bad_setting_comes_back_as_one_readable_error() -> None:
    client, _ = lab_client()
    response = client.post("/api/speak", json={"text": "Hi", "speaker": "ryan", "top_p": 0})

    assert response.status_code == 422
    assert response.json()["error"].startswith("top_p:")


def test_omnivoice_speaks_with_its_attributes_and_diffusion_settings() -> None:
    client, engine = lab_client()
    response = client.post("/api/speak-omnivoice", json={"text": "Hi [laughter]", "language": "en", "instruct": "male, low pitch, british accent", "num_steps": 16})

    assert response.status_code == 200 and response.content == FAKE_WAV
    assert json.loads(response.headers[STATS_HEADER])["repo_id"] == OMNIVOICE_REPO_ID
    assert engine.omnivoice_requests[0].instruct == "male, low pitch, british accent"
    assert engine.omnivoice_requests[0].num_steps == 16 and engine.omnivoice_requests[0].guidance_scale == 2.0


def test_omnivoice_refuses_a_recording_without_its_words_and_out_of_range_steps() -> None:
    client, _ = lab_client()

    assert "words spoken in it" in client.post("/api/speak-omnivoice", json={"text": "Hi", "reference_audio_wav_base64": "eA=="}).json()["error"]
    assert client.post("/api/speak-omnivoice", json={"text": "Hi", "num_steps": 1}).json()["error"].startswith("num_steps:")


def test_transcribing_passes_the_context_and_language_through() -> None:
    client, engine = lab_client()
    audio = base64.b64encode(b"wav bytes").decode()
    response = client.post("/api/transcribe", json={"audio_wav_base64": audio, "language": "Chinese", "context": "Giannis Antetokounmpo"})

    assert response.json()["text"] == "hello"
    assert engine.transcription_requests[0].language == "Chinese"
    assert engine.transcription_requests[0].context == "Giannis Antetokounmpo"


def test_the_page_the_catalog_and_the_model_facts_are_served() -> None:
    client, engine = lab_client()

    assert "Speech Lab" in client.get("/").text
    assert "Mixed" in client.get("/api/catalog").json()["test_sentences"]
    assert "british accent" in client.get("/api/catalog").json()["omnivoice_attributes"]["English accent"]
    assert client.post("/api/voice-model", json={"variant": "CustomVoice"}).json()["dialects"] == {"dylan": "beijing_dialect"}
    assert client.post("/api/unload").json() == {"unloaded": True} and engine.unloaded
