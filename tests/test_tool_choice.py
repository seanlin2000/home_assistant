"""The tool-choice check: which tool a candidate calls first, scored against the question's expected tools, without running any tool."""

from pathlib import Path

from assistant_core.models import AgentPolicy
from assistant_core.tool_guards import load_tool_table
from benchmark.tool_choice import ANSWER_DIRECTLY, CHECKS_PATH, MALFORMED_CALL, ToolChoiceCheck, first_move, load_checks
from tests.fakes import FakeToolBox, ScriptedLLM, malformed_reply, text_reply, tool_reply

RESTAURANT_CHECK = ToolChoiceCheck(id="restaurants", question="Can you recommend a good Italian restaurant in the West Village?", expected=["restaurant_recommendations"])


async def test_a_first_call_to_an_expected_tool_is_right_and_no_tool_runs() -> None:
    toolbox = FakeToolBox()
    llm = ScriptedLLM([tool_reply("Italian West Village", tool_name="restaurant_recommendations")])
    move = await first_move(llm, toolbox, AgentPolicy(), RESTAURANT_CHECK, "fake", 1)
    assert (move.first_call, move.correct, move.calls_in_first_turn) == ("restaurant_recommendations", True, 1)
    assert toolbox.calls == []


async def test_a_web_search_where_a_domain_tool_was_expected_is_wrong() -> None:
    move = await first_move(ScriptedLLM([tool_reply("Italian West Village")]), FakeToolBox(), AgentPolicy(), RESTAURANT_CHECK, "fake", 1)
    assert (move.first_call, move.correct) == ("search_and_read", False)


async def test_answering_without_a_tool_and_a_malformed_call_are_named_as_such() -> None:
    sky = ToolChoiceCheck(id="sky", question="Why is the sky blue?", expected=[ANSWER_DIRECTLY])
    answered = await first_move(ScriptedLLM([text_reply("Sunlight scatters.")]), FakeToolBox(), AgentPolicy(), sky, "fake", 1)
    malformed = await first_move(ScriptedLLM([malformed_reply()]), FakeToolBox(), AgentPolicy(), sky, "fake", 1)
    assert (answered.first_call, answered.correct) == (ANSWER_DIRECTLY, True)
    assert (malformed.first_call, malformed.correct) == (MALFORMED_CALL, False)


async def test_the_model_reads_the_harness_prompt_with_the_word_limit_before_the_question() -> None:
    llm = ScriptedLLM([tool_reply("Italian", tool_name="restaurant_recommendations")])
    await first_move(llm, FakeToolBox(), AgentPolicy(), RESTAURANT_CHECK, "fake", 1)
    question = llm.seen_messages[0][-1].content
    assert "Answer word limit: about" in question and question.endswith(RESTAURANT_CHECK.question)


def test_every_expected_first_call_is_a_harness_tool_or_answering() -> None:
    known = set(load_tool_table().tools) | {ANSWER_DIRECTLY}
    checks = load_checks(Path(CHECKS_PATH))
    assert len({check.id for check in checks}) == len(checks)
    assert {name for check in checks for name in check.expected} <= known
