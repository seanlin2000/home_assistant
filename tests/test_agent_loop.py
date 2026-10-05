from assistant_core import agent_loop
from assistant_core.agent_loop import SilenceMarkerHold, SpokenAnswerCap
from assistant_core.models import AgentEvent, AgentPolicy, AnswerDelta, Done, FillerSpoken, Message, Role, ToolFinished, ToolStarted
from assistant_core.prompts import SILENCE_MARKER
from tests.fakes import FakeToolBox, ScriptedLLM, empty_reply, text_reply, tool_replies_past_the_cap, tool_reply


async def collect(llm: ScriptedLLM, tools: FakeToolBox, policy: AgentPolicy | None = None) -> list[AgentEvent]:
    conversation = [Message(role=Role.USER, content="What is the fed funds rate?")]
    return [event async for event in agent_loop.run(conversation, llm, tools, policy or AgentPolicy(filler_phrases=["Checking."]))]


async def test_plain_answer_streams_text_and_returns_transcript() -> None:
    llm = ScriptedLLM([text_reply("It is ", "four percent.")])
    events = await collect(llm, FakeToolBox())
    assert [event.text for event in events if isinstance(event, AnswerDelta)] == ["It is ", "four percent."]
    transcript = events[-1].transcript
    assert isinstance(events[-1], Done)
    assert transcript.final_answer == "It is four percent."
    assert transcript.tool_call_count == 0
    assert transcript.time_to_first_spoken_seconds is not None
    assert llm.seen_messages[0][0].role == Role.SYSTEM


async def test_tool_call_speaks_filler_before_running_tool_then_answers() -> None:
    llm = ScriptedLLM([tool_reply("fed funds rate"), text_reply("It is 4.25 percent.")])
    tools = FakeToolBox()
    events = await collect(llm, tools)
    kinds = [type(event).__name__ for event in events]
    assert kinds == ["FillerSpoken", "ToolStarted", "ToolFinished", "AnswerDelta", "Done"]
    assert events[0].text == "Checking."
    assert tools.calls[0].arguments == {"query": "fed funds rate"}
    transcript = events[-1].transcript
    assert transcript.tool_call_count == 1
    assert transcript.tool_call_records[0].result.startswith("[1] Source")
    second_call_messages = llm.seen_messages[1]
    assert second_call_messages[-1].role == Role.TOOL
    assert second_call_messages[-1].tool_call_id == "call_0"


async def test_tool_round_cap_forces_a_final_answer() -> None:
    llm = ScriptedLLM([tool_reply("q1"), tool_reply("q2"), tool_reply("q3"), text_reply("Here is what I have.")])
    policy = AgentPolicy(max_tool_rounds=2, filler_phrases=["Checking."])
    events = await collect(llm, FakeToolBox(), policy)
    transcript = events[-1].transcript
    assert transcript.hit_tool_round_cap is True
    assert transcript.tool_call_count == 3
    assert transcript.final_answer == "Here is what I have."
    assert agent_loop.TOOL_LIMIT_NOTICE in [message.content for message in llm.seen_messages[-1]]


async def test_answer_after_the_tool_round_cap_is_spoken() -> None:
    policy = AgentPolicy(filler_phrases=["Checking."])
    llm = ScriptedLLM([*tool_replies_past_the_cap(policy), text_reply("Here is ", "what I found.")])
    events = await collect(llm, FakeToolBox(), policy)
    spoken = [event.text for event in events if isinstance(event, AnswerDelta)]
    transcript = events[-1].transcript
    assert spoken == ["Here is ", "what I found."]
    assert transcript.spoken_text == "".join(spoken).strip()
    assert transcript.hit_tool_round_cap is True
    assert transcript.final_answer == "Here is what I found."
    assert len(transcript.model_calls) == policy.max_tool_rounds + 2


async def test_answer_after_the_tool_round_cap_is_cut_by_the_word_budget() -> None:
    policy = AgentPolicy(word_budget=3, filler_phrases=["Checking."])
    llm = ScriptedLLM([*tool_replies_past_the_cap(policy), text_reply("One two three four. ", "Five six.")])
    events = await collect(llm, FakeToolBox(), policy)
    transcript = events[-1].transcript
    assert [event.text for event in events if isinstance(event, AnswerDelta)] == ["One two three four. "]
    assert transcript.spoken_text == "One two three four."
    assert transcript.truncated is True
    assert transcript.final_answer == "One two three four. Five six."


async def test_tool_failure_is_reported_to_model_not_raised() -> None:
    llm = ScriptedLLM([tool_reply("q"), text_reply("I could not check the web, but roughly four percent.")])
    events = await collect(llm, FakeToolBox(fail=True))
    finished = next(event for event in events if isinstance(event, ToolFinished))
    assert finished.error is not None and "ConnectionError" in finished.error
    assert events[-1].transcript.tool_call_records[0].result == agent_loop.TOOL_UNREACHABLE_NOTICE


async def test_tool_server_unavailable_still_answers() -> None:
    class DeadToolBox(FakeToolBox):
        async def list_tools(self):
            raise ConnectionError("refused")

    llm = ScriptedLLM([text_reply("Answering from memory.")])
    events = await collect(llm, DeadToolBox())
    transcript = events[-1].transcript
    assert transcript.final_answer == "Answering from memory."
    assert transcript.error is not None and "tool server unavailable" in transcript.error


async def test_word_cap_stops_speech_at_sentence_end() -> None:
    cap = SpokenAnswerCap(word_budget=5)
    spoken = [cap.admit(chunk) for chunk in ["One two three. ", "Four five six seven. ", "Eight nine."]]
    assert spoken == ["One two three. ", "Four five six seven. ", ""]
    assert cap.truncated is True
    assert cap.spoken_text == "One two three. Four five six seven."


async def test_multi_exchange_conversation_carries_history() -> None:
    llm = ScriptedLLM([text_reply("Pick 24 GB."), text_reply("Still 24 GB.")])
    tools = FakeToolBox()
    first = [event async for event in agent_loop.run([Message(role=Role.USER, content="16 or 24 GB?")], llm, tools, AgentPolicy())]
    conversation = first[-1].transcript.conversation + [Message(role=Role.USER, content="It costs $400 more.")]
    second = [event async for event in agent_loop.run(conversation, llm, tools, AgentPolicy())]
    roles = [message.role for message in llm.seen_messages[1]]
    assert roles == [Role.SYSTEM, Role.USER, Role.ASSISTANT, Role.USER]
    assert second[-1].transcript.final_answer == "Still 24 GB."
    assert isinstance(second[0], AnswerDelta)
    assert not any(isinstance(event, (FillerSpoken, ToolStarted)) for event in second)


async def test_calculator_call_speaks_the_math_filler_not_the_web_one() -> None:
    llm = ScriptedLLM([tool_reply("18% of 245", tool_name="percent"), text_reply("Forty-four dollars and ten cents.")])
    policy = AgentPolicy(filler_phrases=["Checking the web."], calculate_filler_phrases=["Doing the math."])
    events = await collect(llm, FakeToolBox(), policy)
    assert isinstance(events[0], FillerSpoken)
    assert events[0].text == "Doing the math."


async def test_empty_completion_is_retried_once_and_the_retry_answers() -> None:
    llm = ScriptedLLM([empty_reply(), text_reply("Yes, it can.")])
    events = await collect(llm, FakeToolBox())
    transcript = events[-1].transcript
    assert transcript.final_answer == "Yes, it can."
    assert transcript.empty_completion_retries == 1
    assert len(transcript.model_calls) == 2
    assert len(llm.seen_messages) == 2 and llm.seen_messages[1] == llm.seen_messages[0]


async def test_second_empty_completion_is_accepted_as_an_empty_answer() -> None:
    llm = ScriptedLLM([empty_reply(), empty_reply()])
    events = await collect(llm, FakeToolBox())
    transcript = events[-1].transcript
    assert transcript.final_answer == ""
    assert transcript.empty_completion_retries == 1


async def test_filler_is_spoken_once_even_when_tools_run_in_two_rounds() -> None:
    llm = ScriptedLLM([tool_reply("18% of 64.50", "call_0", "percent"), tool_reply("11.61 + 64.50", "call_1", "calculate"), text_reply("Seventy-six eleven.")])
    events = await collect(llm, FakeToolBox())
    assert len([event for event in events if isinstance(event, FillerSpoken)]) == 1
    assert events[-1].transcript.final_answer == "Seventy-six eleven."


def spoken_deltas(events: list[AgentEvent]) -> list[str]:
    return [event.text for event in events if isinstance(event, AnswerDelta)]


async def test_silence_marker_alone_is_never_spoken_and_is_recorded() -> None:
    events = await collect(ScriptedLLM([text_reply(SILENCE_MARKER)]), FakeToolBox())
    transcript = events[-1].transcript
    assert spoken_deltas(events) == []
    assert transcript.stayed_silent is True
    assert transcript.spoken_text == ""
    assert transcript.time_to_first_spoken_seconds is None


async def test_silence_marker_surrounded_by_whitespace_is_still_silence() -> None:
    events = await collect(ScriptedLLM([text_reply(" ", f"{SILENCE_MARKER}", "\n")]), FakeToolBox())
    assert spoken_deltas(events) == []
    assert events[-1].transcript.stayed_silent is True


async def test_an_ordinary_answer_is_released_from_its_first_chunk() -> None:
    events = await collect(ScriptedLLM([text_reply("Canberra ", "is the capital.")]), FakeToolBox())
    assert spoken_deltas(events) == ["Canberra ", "is the capital."]
    assert events[-1].transcript.stayed_silent is False


async def test_an_answer_that_starts_with_the_marker_character_is_spoken_in_full() -> None:
    events = await collect(ScriptedLLM([text_reply(" ", SILENCE_MARKER, " Canberra", " is the capital.")]), FakeToolBox())
    assert spoken_deltas(events) == [f" {SILENCE_MARKER} Canberra", " is the capital."]
    assert events[-1].transcript.stayed_silent is False


def test_silence_hold_releases_everything_held_once_the_text_diverges() -> None:
    hold = SilenceMarkerHold()
    assert [hold.release(chunk) for chunk in ["\n", SILENCE_MARKER, "Not silent.", " More."]] == ["", "", f"\n{SILENCE_MARKER}Not silent.", " More."]
