"""The Home Assistant adapter is loaded by file path because the component package itself imports Home Assistant, which is not installed in this venv."""

import importlib.util
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from assistant_core import agent_loop
from assistant_core.models import AgentEvent, AgentPolicy, AnswerDelta, Done, FillerSpoken, Message, Role, ToolCall, ToolStarted, Transcript
from assistant_core.prompts import ACKNOWLEDGEMENT_REPLY, REPEAT_REQUEST_REPLY, SILENCE_MARKER
from tests.fakes import FakeToolBox, ScriptedLLM, text_reply, tool_replies_past_the_cap

ADAPTER_PATH = Path("custom_components/studio_assistant/adapter.py")
spec = importlib.util.spec_from_file_location("studio_assistant_adapter", ADAPTER_PATH)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


@dataclass
class FakeContent:
    role: str
    content: str | None = None


def test_chat_log_keeps_spoken_messages_only() -> None:
    contents = [
        FakeContent("system", "HA's own prompt"),
        FakeContent("user", "I'm deciding between 16 and 24 GB."),
        FakeContent("assistant", None),
        FakeContent("tool_result", "ignored"),
        FakeContent("assistant", "Go with 24."),
        FakeContent("user", "Suppose it costs $400 more."),
    ]
    conversation = adapter.chat_log_to_conversation(contents)
    assert [(message.role, message.content) for message in conversation] == [
        (Role.USER, "I'm deciding between 16 and 24 GB."),
        (Role.ASSISTANT, "Go with 24."),
        (Role.USER, "Suppose it costs $400 more."),
    ]


async def collect(events: AsyncIterator[AgentEvent]) -> list[dict[str, Any]]:
    return [delta async for delta in adapter.agent_events_to_deltas(events)]


async def events_from(items: list[AgentEvent]) -> AsyncIterator[AgentEvent]:
    for item in items:
        yield item


async def test_filler_and_answer_become_one_streamed_assistant_message() -> None:
    transcript = Transcript(model="m", system_prompt="", conversation=[], final_answer="It is 3.63 percent.")
    call = ToolCall(id="c", name="search_and_read", arguments={"query": "fed funds"})
    deltas = await collect(events_from([FillerSpoken(text="Let me check."), ToolStarted(call=call), AnswerDelta(text="It is "), AnswerDelta(text="3.63 percent."), Done(transcript=transcript)]))
    assert deltas[0] == {"role": "assistant"}
    assert "".join(delta.get("content", "") for delta in deltas[1:]) == "Let me check. It is 3.63 percent."
    assert all("tool_calls" not in delta for delta in deltas)


async def test_answer_after_the_tool_round_cap_follows_the_filler() -> None:
    policy = AgentPolicy(filler_phrases=["Let me check."])
    llm = ScriptedLLM([*tool_replies_past_the_cap(policy), text_reply("It is ", "3.63 percent.")])
    conversation = [Message(role=Role.USER, content="What is the fed funds rate?")]
    deltas = await collect(agent_loop.run(conversation, llm, FakeToolBox(), policy))
    assert [delta.get("content") for delta in deltas[1:]] == ["Let me check. ", "It is ", "3.63 percent."]


async def test_empty_answer_gets_a_spoken_fallback() -> None:
    transcript = Transcript(model="m", system_prompt="", conversation=[])
    deltas = await collect(events_from([Done(transcript=transcript)]))
    assert deltas == [{"role": "assistant"}, {"content": adapter.EMPTY_ANSWER_FALLBACK}]


async def test_silent_reply_streams_no_content_and_no_fallback() -> None:
    transcript = Transcript(model="m", system_prompt="", conversation=[], final_answer=SILENCE_MARKER, stayed_silent=True)
    deltas = await collect(events_from([Done(transcript=transcript)]))
    assert deltas == [{"role": "assistant"}]


async def test_an_unreachable_harness_is_announced_rather_than_silent() -> None:
    question = [Message(role=Role.USER, content="What's the weather?")]
    deltas = await collect(adapter.harness_unreachable(question, "connection refused"))
    assert deltas == [{"role": "assistant"}, {"content": adapter.HARNESS_UNREACHABLE_ANSWER}]


async def test_on_done_receives_the_transcript_before_the_stream_ends() -> None:
    transcript = Transcript(model="m", system_prompt="", conversation=[], final_answer="Done.")
    seen = []
    deltas = [delta async for delta in adapter.agent_events_to_deltas(events_from([AnswerDelta(text="Done."), Done(transcript=transcript)]), on_done=seen.append)]
    assert seen == [transcript]
    assert deltas[-1] == {"content": "Done."}


def reply(answer: str, stayed_silent: bool = False) -> Transcript:
    return Transcript(model="m", system_prompt="", conversation=[], final_answer=answer, stayed_silent=stayed_silent)


def decisions(listening: Any, replies: list[Transcript], conversation_id: str = "conv") -> list[bool]:
    return [listening.record_reply_and_decide(conversation_id, transcript) for transcript in replies]


def test_follow_ups_stop_after_the_cap_so_a_false_wake_cannot_loop() -> None:
    listening = adapter.FollowUpListening(enabled=True, max_follow_ups=2)
    assert decisions(listening, [reply("An answer."), reply("Another."), reply("A third.")]) == [True, True, False]
    assert listening.follow_ups_so_far("conv") == 0
    assert decisions(listening, [reply("After a new wake word.")]) == [True]


def test_repeat_request_counts_toward_the_cap() -> None:
    listening = adapter.FollowUpListening(enabled=True, max_follow_ups=2)
    assert decisions(listening, [reply(REPEAT_REQUEST_REPLY), reply(REPEAT_REQUEST_REPLY), reply(REPEAT_REQUEST_REPLY)]) == [True, True, False]


def test_silence_and_acknowledgement_end_the_conversation_and_reset_its_count() -> None:
    listening = adapter.FollowUpListening(enabled=True, max_follow_ups=2)
    assert decisions(listening, [reply("An answer."), reply(SILENCE_MARKER, stayed_silent=True)]) == [True, False]
    assert listening.follow_ups_so_far("conv") == 0
    assert decisions(listening, [reply("An answer."), reply(ACKNOWLEDGEMENT_REPLY)]) == [True, False]
    assert listening.follow_ups_so_far("conv") == 0


def test_setting_off_never_continues() -> None:
    listening = adapter.FollowUpListening(enabled=False, max_follow_ups=2)
    assert decisions(listening, [reply("An answer."), reply("Another.")]) == [False, False]


def test_conversations_are_counted_separately_and_the_oldest_are_forgotten() -> None:
    listening = adapter.FollowUpListening(enabled=True, max_follow_ups=2)
    for index in range(adapter.MAX_TRACKED_CONVERSATIONS + 1):
        listening.record_reply_and_decide(f"conv{index}", reply("An answer."))
    assert listening.follow_ups_so_far("conv0") == 0
    assert listening.follow_ups_so_far(f"conv{adapter.MAX_TRACKED_CONVERSATIONS}") == 1


def test_acknowledgement_tolerates_case_and_a_dropped_period() -> None:
    assert all(adapter.is_acknowledgement(answer) for answer in ("Okay.", "okay", " Okay! "))
    assert not adapter.is_acknowledgement("Okay, the capital is Canberra.")
