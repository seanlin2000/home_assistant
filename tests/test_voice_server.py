"""The OmniVoice voice server's Wyoming side (voice_server/handlers.py, speaker.py) against a stand-in synthesizer on a loopback port, with the
event sequences Home Assistant sends."""

import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import pytest
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncTcpClient
from wyoming.event import Event
from wyoming.info import Describe, Info
from wyoming.server import AsyncEventHandler
from wyoming.tts import Synthesize, SynthesizeChunk, SynthesizeStart, SynthesizeStop, SynthesizeStopped, SynthesizeVoice

from speech_server.worker import ModelThread
from utils.pronunciation_utils import VERBATIM_SPEAKER, LivePronunciations, PronunciationStore
from voice_server.handlers import SAMPLES_PER_CHUNK, VoiceHandler, voice_info
from voice_server.settings import load_voice_settings
from voice_server.speaker import FADE_OUT_SECONDS, PEAK_CEILING, PieceFinish, SentenceSpeaker, levelled, with_even_edges
from voice_server.start_cache import StartCache

SETTINGS = load_voice_settings()
SAMPLE_RATE = 24000
SAMPLES_PER_CHARACTER = 100
FINISH = PieceFinish(loudness_dbfs=-20.0, lead_silence_seconds=0.1, trail_silence_seconds=0.35)
EDGE_SAMPLES = round(FINISH.lead_silence_seconds * SAMPLE_RATE) + round(FINISH.trail_silence_seconds * SAMPLE_RATE)
ENGINE = "mlx-audio==0.6.5 mlx==0.32.4"


class StandInSynthesizer:
    """One 220 Hz tone per text, 100 samples per character, so the audio's length tells which text it was made from."""

    sample_rate = SAMPLE_RATE

    def __init__(self) -> None:
        self.made: list[str] = []

    def synthesize(self, text: str) -> np.ndarray:
        self.made.append(text)
        times = np.arange(len(text) * SAMPLES_PER_CHARACTER) / SAMPLE_RATE
        return (0.5 * np.sin(2 * np.pi * 220 * times)).astype(np.float32)


@pytest.fixture
def synthesizer() -> StandInSynthesizer:
    return StandInSynthesizer()


@pytest.fixture
def speaker(synthesizer: StandInSynthesizer, tmp_path: Path) -> SentenceSpeaker:
    dictionary = tmp_path / "versioned" / "omnivoice" / "jarvis.json"
    dictionary.parent.mkdir(parents=True)
    dictionary.write_text('{"model": "omnivoice", "voice": "jarvis", "revision": 0, "entries": [{"written": "Jokic", "say_as": "Yo-Kich"}]}')
    store = PronunciationStore("omnivoice", "jarvis", live_dir=tmp_path / "live", versioned_dir=tmp_path / "versioned")
    return SentenceSpeaker(synthesizer, ModelThread(), LivePronunciations(store), FINISH)


@pytest.fixture
def start_cache(tmp_path: Path) -> StartCache:
    return StartCache(SETTINGS.voice.omnivoice, tmp_path / "cache", ENGINE)


@asynccontextmanager
async def connected(make_handler: Callable[[asyncio.StreamReader, asyncio.StreamWriter], AsyncEventHandler]):
    async def accept(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await make_handler(reader, writer).run()

    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    client = AsyncTcpClient("127.0.0.1", server.sockets[0].getsockname()[1])
    await client.connect()
    try:
        yield client
    finally:
        await client.disconnect()
        server.close()


def voice_handler(speaker: SentenceSpeaker) -> Callable[[asyncio.StreamReader, asyncio.StreamWriter], AsyncEventHandler]:
    return lambda reader, writer: VoiceHandler(speaker, voice_info(SETTINGS), reader, writer)


async def events_until(client: AsyncTcpClient, last_type: str) -> list[Event]:
    events = []
    while (event := await asyncio.wait_for(client.read_event(), timeout=5)) is not None:
        events.append(event)
        if event.type == last_type:
            break
    return events


def heard_samples(*pieces: str) -> int:
    """The stand-in tone is loud throughout, so trimming leaves it whole; each piece then gains its two edges of silence."""
    return sum(len(piece) * SAMPLES_PER_CHARACTER + EDGE_SAMPLES for piece in pieces)


def utterances(events: list[Event]) -> list[int]:
    """The audio between each AudioStart and its AudioStop, as a sample count."""
    lengths = []
    for event in events:
        if AudioStart.is_type(event.type):
            lengths.append(0)
        elif AudioChunk.is_type(event.type):
            lengths[-1] += len(AudioChunk.from_event(event).audio) // 2
    return lengths


async def test_the_port_describes_a_streaming_omnivoice_in_both_english_tags(speaker: SentenceSpeaker) -> None:
    async with connected(voice_handler(speaker)) as client:
        await client.write_event(Describe().event())
        info = Info.from_event(await asyncio.wait_for(client.read_event(), timeout=5))

    program = info.tts[0]
    assert (program.name, program.supports_synthesize_streaming) == ("omnivoice", True)
    assert {voice.name: voice.languages for voice in program.voices} == {"jarvis": ["en_GB", "en_US"], "bm_fable": ["en_GB", "en_US"]}


async def test_a_whole_text_is_one_utterance_made_sentence_by_sentence(speaker: SentenceSpeaker, synthesizer: StandInSynthesizer) -> None:
    async with connected(voice_handler(speaker)) as client:
        await client.write_event(Synthesize(text="It is sunny. Jokic scored forty.").event())
        events = await events_until(client, AudioStop().event().type)

    assert synthesizer.made == ["It is sunny.", "Yo-Kich scored forty."]
    assert utterances(events) == [heard_samples("It is sunny.", "Yo-Kich scored forty.")]
    assert all(len(AudioChunk.from_event(event).audio) <= SAMPLES_PER_CHUNK * 2 for event in events if AudioChunk.is_type(event.type))


async def test_a_stream_speaks_the_filler_then_each_sentence_as_its_end_arrives(speaker: SentenceSpeaker, synthesizer: StandInSynthesizer) -> None:
    """The filler, then the blank line the component sends after it, then the answer in token-sized pieces (custom_components adapter)."""
    deltas = ["Let me check.", "\n\n", "The Knicks", " won 108", " to 102.", " Brunson", " scored 31."]
    async with connected(voice_handler(speaker)) as client:
        await client.write_event(SynthesizeStart(voice=SynthesizeVoice(name="bm_fable")).event())
        for delta in deltas:
            await client.write_event(SynthesizeChunk(text=delta).event())
        await client.write_event(Synthesize(text="".join(deltas)).event())  # the copy Home Assistant sends for servers without streaming
        await client.write_event(SynthesizeStop().event())
        events = await events_until(client, SynthesizeStopped().event().type)

    assert synthesizer.made == ["Let me check.", "The Knicks won 108 to 102.", "Brunson scored 31."]
    assert utterances(events) == [heard_samples(text) for text in synthesizer.made]
    assert events[-1].type == SynthesizeStopped().event().type


async def test_a_long_sentence_is_made_in_pieces_within_one_utterance(speaker: SentenceSpeaker, synthesizer: StandInSynthesizer) -> None:
    sentence = "Tonight there are showings at seven, at half past eight, at ten, and at a quarter to midnight, at the Angelika, the IFC Center downtown, and the Film Forum on Houston Street."
    async with connected(voice_handler(speaker)) as client:
        await client.write_event(Synthesize(text=sentence + " Enjoy the film.").event())
        events = await events_until(client, AudioStop().event().type)

    assert len(sentence) > 150 and len(synthesizer.made) == 3
    assert " ".join(synthesizer.made[:2]) == sentence and all(len(piece) <= 150 for piece in synthesizer.made[:2])
    assert len(utterances(events)) == 1


async def test_the_dashboards_verbatim_previews_are_not_respelled(speaker: SentenceSpeaker, synthesizer: StandInSynthesizer) -> None:
    async with connected(voice_handler(speaker)) as client:
        await client.write_event(Synthesize(text="Jokic scored.", voice=SynthesizeVoice(name="jarvis", speaker=VERBATIM_SPEAKER)).event())
        await events_until(client, AudioStop().event().type)

    assert synthesizer.made == ["Jokic scored."]


async def test_fillers_made_ahead_are_replayed_without_the_model(speaker: SentenceSpeaker, synthesizer: StandInSynthesizer, start_cache: StartCache) -> None:
    speaker.make_ahead(["One moment.", "Let me look that up."], start_cache)
    async with connected(voice_handler(speaker)) as client:
        await client.write_event(SynthesizeStart().event())
        await client.write_event(SynthesizeChunk(text="One moment.\n\nIt is 72 degrees.").event())
        await client.write_event(SynthesizeStop().event())
        events = await events_until(client, SynthesizeStopped().event().type)

    assert synthesizer.made == ["One moment.", "Let me look that up.", "It is 72 degrees."]
    assert utterances(events) == [heard_samples("One moment."), heard_samples("It is 72 degrees.")]


def test_each_piece_is_levelled_to_the_target_loudness_with_its_peak_capped() -> None:
    quiet_speech = np.concatenate([np.zeros(1000), 0.05 * np.sin(np.linspace(0, 400, 24000))]).astype(np.float32)
    voiced = levelled(quiet_speech, -20.0)[1000:]
    assert 20 * np.log10(np.sqrt(np.mean(voiced[np.abs(voiced) > 0.01] ** 2))) == pytest.approx(-20.0, abs=0.5)

    spiky = np.concatenate([np.full(10, 0.9), np.full(24000, 0.02)]).astype(np.float32)
    assert np.abs(levelled(spiky, -20.0)).max() == pytest.approx(PEAK_CEILING)
    assert np.array_equal(levelled(np.zeros(100, dtype=np.float32), -20.0), np.zeros(100))


def test_each_piece_is_trimmed_to_its_speech_and_ends_in_set_silence_so_the_puck_never_holds_back_a_word() -> None:
    """As OmniVoice made "Checking Reddit.": most of a second of near-silence first, and the last syllable still sounding at the very end."""
    near_silence = np.full(SAMPLE_RATE, 0.001, dtype=np.float32)
    speech_to_the_end = (0.3 * np.sin(2 * np.pi * 220 * np.arange(SAMPLE_RATE // 2) / SAMPLE_RATE)).astype(np.float32)

    finished = with_even_edges(np.concatenate([near_silence, speech_to_the_end]), SAMPLE_RATE, FINISH)

    lead, trail = round(FINISH.lead_silence_seconds * SAMPLE_RATE), round(FINISH.trail_silence_seconds * SAMPLE_RATE)
    assert len(finished) == lead + len(speech_to_the_end) + trail
    assert not finished[:lead].any() and not finished[-trail:].any()
    assert finished[-trail - 1] == 0.0 and np.abs(finished[-trail - int(FADE_OUT_SECONDS * SAMPLE_RATE) // 2]) < 0.3


def test_a_silent_piece_is_left_as_it_is() -> None:
    silent = np.zeros(SAMPLE_RATE, dtype=np.float32)
    assert np.array_equal(with_even_edges(silent, SAMPLE_RATE, FINISH), silent)
