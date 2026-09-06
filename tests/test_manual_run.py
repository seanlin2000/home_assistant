"""The manual replay must produce the same transcript shape as a model run: real tool exchanges first, then the scripted answer."""

from assistant_core import agent_loop
from assistant_core.models import AgentPolicy, Done, Message, Role
from benchmark.manual_run import ScriptedAnswerClient, ScriptedTurn
from tests.fakes import FakeToolBox


async def replay(turn: ScriptedTurn, toolbox: FakeToolBox):
    client = ScriptedAnswerClient("manual")
    client.load_turn(turn)
    async for event in agent_loop.run([Message(role=Role.USER, content="question")], client, toolbox, AgentPolicy()):
        if isinstance(event, Done):
            return event.transcript
    raise AssertionError("no Done event")


async def test_scripted_turn_with_queries_searches_then_answers() -> None:
    toolbox = FakeToolBox()
    transcript = await replay(ScriptedTurn(queries=["fed funds rate", "fed funds history"], answer="It is 4.25 percent."), toolbox)
    assert [call.arguments["query"] for call in toolbox.calls] == ["fed funds rate", "fed funds history"]
    assert transcript.tool_call_count == 2
    assert len(transcript.tool_exchanges) == 2
    assert transcript.final_answer == "It is 4.25 percent."
    assert [message.role for message in transcript.conversation] == [Role.USER, Role.ASSISTANT, Role.TOOL, Role.TOOL, Role.ASSISTANT]


async def test_scripted_turn_without_queries_never_touches_tools() -> None:
    toolbox = FakeToolBox()
    transcript = await replay(ScriptedTurn(answer="Nineteen eighty nine."), toolbox)
    assert toolbox.calls == []
    assert transcript.tool_exchanges == []
    assert transcript.final_answer == "Nineteen eighty nine."
