"""The benchmark's --speak (benchmark/speaking.py): answers streamed to a stand-in Wyoming voice the way Home Assistant streams them, and the
audio timed as it comes back."""

import re
from collections.abc import AsyncIterator

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.server import AsyncEventHandler
from wyoming.tts import SynthesizeChunk, SynthesizeStart, SynthesizeStop, SynthesizeStopped

from assistant_core.models import AgentEvent, AnswerDelta, Done, FillerSpoken, ToolCall, ToolStarted, Transcript
from benchmark.speaking import VoiceAddress, spoken_transcript
from tests.test_smoke import serving

VOICE_RATE = 24000
SECONDS_PER_SENTENCE = 0.5
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
FILLER = "Let me look that up."
TRANSCRIPT = Transcript(model="stand-in", system_prompt="", conversation=[], final_answer="Jokic scored 31. Denver won.")


class StreamingStandInVoice(AsyncEventHandler):
    """Keeps what it was sent, then speaks each sentence of it as its own utterance, half a second of silence each, as the voice servers stream."""

    def __init__(self, received: list[str], *args: object) -> None:
        super().__init__(*args)
        self.received = received
        self.text = ""

    async def handle_event(self, event: Event) -> bool:
        if SynthesizeStart.is_type(event.type):
            self.received.append("start")
        elif SynthesizeChunk.is_type(event.type):
            self.received.append(SynthesizeChunk.from_event(event).text)
            self.text += SynthesizeChunk.from_event(event).text
        elif SynthesizeStop.is_type(event.type):
            await self.speak_every_sentence()
            return False
        return True

    async def speak_every_sentence(self) -> None:
        for _ in [sentence for sentence in SENTENCE_END.split(self.text.strip()) if sentence]:
            await self.write_event(AudioStart(rate=VOICE_RATE, width=2, channels=1).event())
            await self.write_event(AudioChunk(audio=bytes(int(VOICE_RATE * 2 * SECONDS_PER_SENTENCE)), rate=VOICE_RATE, width=2, channels=1).event())
            await self.write_event(AudioStop().event())
        await self.write_event(SynthesizeStopped().event())


async def events_of(*events: AgentEvent) -> AsyncIterator[AgentEvent]:
    for event in events:
        yield event


async def spoken(*events: AgentEvent) -> tuple[Transcript, list[str]]:
    received: list[str] = []
    server, port = await serving(lambda reader, writer: StreamingStandInVoice(received, reader, writer))
    transcript = await spoken_transcript(events_of(*events), VoiceAddress(host="127.0.0.1", port=port), started=0.0)
    server.close()  # not wait_closed: it waits for the handler's side of the connection, which the stand-in leaves open
    return transcript, received


def test_a_voice_address_is_read_from_host_and_port() -> None:
    assert VoiceAddress.from_text("192.168.1.162:10210") == VoiceAddress(host="192.168.1.162", port=10210)
    assert VoiceAddress.from_text(":10210") == VoiceAddress(host="127.0.0.1", port=10210)


async def test_the_filler_opens_the_stream_at_the_tool_call_and_the_answer_audio_is_the_utterance_after_it() -> None:
    transcript, received = await spoken(
        FillerSpoken(text=FILLER),
        ToolStarted(call=ToolCall(id="call-1", name="sports_scores", arguments={})),
        AnswerDelta(text="Jokic scored 31. "),
        AnswerDelta(text="Denver won."),
        Done(transcript=TRANSCRIPT),
    )

    assert received == ["start", FILLER + "\n\n", "Jokic scored 31. ", "Denver won."]
    assert transcript.final_answer == TRANSCRIPT.final_answer
    assert transcript.time_to_first_audio_seconds < transcript.time_to_first_answer_audio_seconds <= transcript.audio_done_seconds
    assert transcript.spoken_audio_seconds == 3 * SECONDS_PER_SENTENCE


async def test_text_is_held_until_it_passes_sixty_characters_then_streamed_as_it_comes() -> None:
    deltas = ["Denver beat the Lakers ", "one hundred twelve to ", "one hundred eight last ", "night at home. ", "Jokic had a triple double."]

    transcript, received = await spoken(*[AnswerDelta(text=delta) for delta in deltas], Done(transcript=TRANSCRIPT))

    assert received == ["start", "".join(deltas[:3]), *deltas[3:]]
    assert transcript.time_to_first_answer_audio_seconds == transcript.time_to_first_audio_seconds
    assert transcript.spoken_audio_seconds == 2 * SECONDS_PER_SENTENCE


async def test_a_short_reply_is_sent_whole_when_it_ends() -> None:
    transcript, received = await spoken(AnswerDelta(text="It is 72 "), AnswerDelta(text="degrees."), Done(transcript=TRANSCRIPT))

    assert received == ["start", "It is 72 degrees."]
    assert transcript.spoken_audio_seconds == SECONDS_PER_SENTENCE


async def test_a_reply_that_stays_silent_sends_the_voice_nothing() -> None:
    silent = TRANSCRIPT.model_copy(update={"stayed_silent": True, "final_answer": ""})

    transcript, received = await spoken(Done(transcript=silent))

    assert received == []
    assert (transcript.time_to_first_audio_seconds, transcript.spoken_audio_seconds, transcript.stayed_silent) == (None, 0.0, True)
