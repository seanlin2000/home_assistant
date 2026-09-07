from assistant_core import agent_loop
from assistant_core.agent_loop import SpokenAnswerCap
from assistant_core.models import AgentEvent, AgentPolicy, AnswerDelta, Done, FillerSpoken, Message, Role, ToolFinished, ToolStarted
from tests.fakes import FakeToolBox, ScriptedLLM, empty_turn, text_turn, tool_turn


async def collect(llm: ScriptedLLM, tools: FakeToolBox, policy: AgentPolicy | None = None) -> list[AgentEvent]:
    conversation = [Message(role=Role.USER, content="What is the fed funds rate?")]
    return [event async for event in agent_loop.run(conversation, llm, tools, policy or AgentPolicy(filler_phrases=["Checking."]))]


async def test_plain_answer_streams_text_and_returns_transcript() -> None:
    llm = ScriptedLLM([text_turn("It is ", "four percent.")])
    events = await collect(llm, FakeToolBox())
    assert [event.text for event in events if isinstance(event, AnswerDelta)] == ["It is ", "four percent."]
    transcript = events[-1].transcript
    assert isinstance(events[-1], Done)
    assert transcript.final_answer == "It is four percent."
    assert transcript.tool_call_count == 0
    assert transcript.time_to_first_spoken_seconds is not None
    assert llm.seen_messages[0][0].role == Role.SYSTEM


async def test_tool_call_speaks_filler_before_running_tool_then_answers() -> None:
    llm = ScriptedLLM([tool_turn("fed funds rate"), text_turn("It is 4.25 percent.")])
    tools = FakeToolBox()
    events = await collect(llm, tools)
    kinds = [type(event).__name__ for event in events]
    assert kinds == ["FillerSpoken", "ToolStarted", "ToolFinished", "AnswerDelta", "Done"]
    assert events[0].text == "Checking."
    assert tools.calls[0].arguments == {"query": "fed funds rate"}
    transcript = events[-1].transcript
    assert transcript.tool_call_count == 1
    assert transcript.tool_exchanges[0].result.startswith("[1] Source")
    second_call_messages = llm.seen_messages[1]
    assert second_call_messages[-1].role == Role.TOOL
    assert second_call_messages[-1].tool_call_id == "call_0"


async def test_tool_round_cap_forces_a_final_answer() -> None:
    llm = ScriptedLLM([tool_turn("q1"), tool_turn("q2"), tool_turn("q3"), text_turn("Here is what I have.")])
    policy = AgentPolicy(max_tool_rounds=2, filler_phrases=["Checking."])
    events = await collect(llm, FakeToolBox(), policy)
    transcript = events[-1].transcript
    assert transcript.hit_tool_round_cap is True
    assert transcript.tool_call_count == 3
    assert transcript.final_answer == "Here is what I have."
    assert agent_loop.TOOL_LIMIT_NOTICE in [message.content for message in llm.seen_messages[-1]]


async def test_tool_failure_is_reported_to_model_not_raised() -> None:
    llm = ScriptedLLM([tool_turn("q"), text_turn("I could not check the web, but roughly four percent.")])
    events = await collect(llm, FakeToolBox(fail=True))
    finished = next(event for event in events if isinstance(event, ToolFinished))
    assert finished.error is not None and "ConnectionError" in finished.error
    assert events[-1].transcript.tool_exchanges[0].result == agent_loop.TOOL_UNREACHABLE_NOTICE


async def test_tool_server_unavailable_still_answers() -> None:
    class DeadToolBox(FakeToolBox):
        async def list_tools(self):
            raise ConnectionError("refused")

    llm = ScriptedLLM([text_turn("Answering from memory.")])
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


async def test_multi_turn_conversation_carries_history() -> None:
    llm = ScriptedLLM([text_turn("Pick 24 GB."), text_turn("Still 24 GB.")])
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
    llm = ScriptedLLM([tool_turn("18% of 245", tool_name="percent"), text_turn("Forty-four dollars and ten cents.")])
    policy = AgentPolicy(filler_phrases=["Checking the web."], calculate_filler_phrases=["Doing the math."])
    events = await collect(llm, FakeToolBox(), policy)
    assert isinstance(events[0], FillerSpoken)
    assert events[0].text == "Doing the math."


async def test_empty_completion_is_retried_once_and_the_retry_answers() -> None:
    llm = ScriptedLLM([empty_turn(), text_turn("Yes, it can.")])
    events = await collect(llm, FakeToolBox())
    transcript = events[-1].transcript
    assert transcript.final_answer == "Yes, it can."
    assert transcript.empty_completion_retries == 1
    assert len(transcript.model_calls) == 2
    assert len(llm.seen_messages) == 2 and llm.seen_messages[1] == llm.seen_messages[0]


async def test_second_empty_completion_is_accepted_as_an_empty_answer() -> None:
    llm = ScriptedLLM([empty_turn(), empty_turn()])
    events = await collect(llm, FakeToolBox())
    transcript = events[-1].transcript
    assert transcript.final_answer == ""
    assert transcript.empty_completion_retries == 1
