"""newsletter_read and the harness rule that speaks its result (design doc v2/14 sections 3.6 and 3.7): parts of about three minutes with their
opening and closing lines, the read cursor behind "next", the speech cleanup, and the agent loop speaking a reading whole with no model after it,
handing anything else back to the model, and shortening a replayed reading."""

import shutil
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer

from assistant_core import agent_loop
from assistant_core.models import AgentEvent, AgentPolicy, AnswerDelta, Completion, Done, FillerSpoken, GenerationStats, LLMEvent, Message, Role, ToolCall, ToolCallRequest, ToolSpec
from assistant_core.tool_guards import speaks_its_result
from assistant_core.tools import McpToolBox
from benchmark.mcp_process import NEWSLETTERS_DIR, NEWSLETTERS_RECORDED_ON
from newsletters_mcp.answers import FINISHED_MESSAGE, NOTHING_TO_CONTINUE_MESSAGE
from newsletters_mcp.reading import spoken_paragraph
from newsletters_mcp.register import NEWSLETTER_READ_TOOL_NAME, register_newsletters_tools
from newsletters_mcp.settings import NewslettersSettings
from tests.fakes import FakeToolBox, ScriptedLLM, text_reply
from utils.spoken_reading_utils import is_reading

RECORDED_ON = date.fromisoformat(NEWSLETTERS_RECORDED_ON)
READING = "Reading Money Stuff: Procurement.\nA pretend official steered a contract.\nThe fee was about $40 million.\nNext is Things happen. Say continue to hear it."
READ_TOOL = ToolSpec(
    name=NEWSLETTER_READ_TOOL_NAME,
    description="read aloud",
    input_schema={"type": "object", "properties": {"newsletter": {"type": "string"}, "section": {"type": "string"}}},
)


@pytest.fixture
def settings(tmp_path: Path) -> NewslettersSettings:
    folder = tmp_path / "newsletters"
    shutil.copytree(NEWSLETTERS_DIR, folder)
    return NewslettersSettings(dir=folder, today=RECORDED_ON)


async def read(settings: NewslettersSettings, **arguments: Any) -> str:
    server = MCPServer("test")
    register_newsletters_tools(server, settings)
    async with McpToolBox(server) as toolbox:
        return await toolbox.call(ToolCall(id="1", name=NEWSLETTER_READ_TOOL_NAME, arguments=arguments))


def reading_lines(reply: str) -> tuple[str, str]:
    lines = reply.split("\n")
    return lines[0], lines[-1]


async def test_a_short_issue_is_one_part_that_names_each_section_as_it_starts(settings: NewslettersSettings) -> None:
    reply = await read(settings, newsletter="Money Stuff")
    assert reading_lines(reply) == ("Reading Money Stuff: Hypothetical widgets.", "That's the end of Money Stuff.")
    assert "\nProcurement.\nAnyway, a pretend deputy secretary" in reply and "\nThings happen.\n" in reply
    assert is_reading(reply)


async def test_a_named_section_is_read_from_its_start(settings: NewslettersSettings) -> None:
    reply = await read(settings, newsletter="money stuff", section="procurement")
    assert reading_lines(reply) == ("Reading Money Stuff: Procurement.", "That's the end of Money Stuff.")
    assert "$40 million" in reply


async def test_the_text_before_the_first_heading_is_read_under_the_headline(settings: NewslettersSettings) -> None:
    assert reading_lines(await read(settings, newsletter="The Morning"))[0] == "Reading The Morning: Taking stock."


async def test_quotation_marks_and_footnote_marks_are_not_read_out(settings: NewslettersSettings) -> None:
    reply = await read(settings, newsletter="Money Stuff")
    assert "\n> " not in reply and "either, but it is the sort of thing a board says." in reply
    assert "Footnote 1: It probably means nothing." in reply


def test_a_table_row_is_read_as_a_list_without_its_arrow() -> None:
    assert spoken_paragraph("↓ DJIA Futures | 51,000.00 | -1.20%") == "DJIA Futures, 51,000.00, -1.20%"
    assert spoken_paragraph("| Last | Chg%") == "Last, Chg%"


async def test_a_long_section_is_read_in_parts_and_next_continues_it(settings: NewslettersSettings) -> None:
    short_parts = settings.model_copy(update={"reading_words": 40})
    first = await read(short_parts, newsletter="Money Stuff")
    assert reading_lines(first)[1] == "Next is more of Hypothetical widgets. Say continue to hear it."
    second = await read(short_parts, section="next")
    assert reading_lines(second)[0] == "Reading Money Stuff: more of Hypothetical widgets."
    assert first.split("\n")[1:-1] != second.split("\n")[1:-1]


async def test_the_last_part_says_the_issue_is_over_and_next_then_says_so_to_the_model(settings: NewslettersSettings) -> None:
    last = await read(settings, newsletter="Money Stuff", section="things happen")
    assert reading_lines(last)[1] == "That's the end of Money Stuff."
    after = await read(settings, section="next")
    assert after == FINISHED_MESSAGE.format(publication="Money Stuff") and not is_reading(after)


async def test_continuing_with_nothing_read_yet_goes_back_to_the_model(settings: NewslettersSettings) -> None:
    assert await read(settings) == NOTHING_TO_CONTINUE_MESSAGE


async def test_a_failure_sentence_is_never_a_reading(settings: NewslettersSettings) -> None:
    assert not is_reading(await read(settings, newsletter="Matt Taibbi"))


def test_only_newsletter_read_speaks_its_result() -> None:
    assert speaks_its_result(NEWSLETTER_READ_TOOL_NAME)
    assert not speaks_its_result("newsletter_summarize") and not speaks_its_result("search_and_read")


class ReadingToolBox(FakeToolBox):
    async def list_tools(self) -> list[ToolSpec]:
        return [READ_TOOL]


def read_reply(*argument_sets: dict[str, Any]) -> list[LLMEvent]:
    calls = [ToolCall(id=f"read_{index}", name=NEWSLETTER_READ_TOOL_NAME, arguments=arguments) for index, arguments in enumerate(argument_sets)]
    message = Message(role=Role.ASSISTANT, content="", tool_calls=calls)
    return [*(ToolCallRequest(call=call) for call in calls), Completion(message=message, stats=GenerationStats(model="fake", total_seconds=0.1))]


async def run_loop(llm: ScriptedLLM, tools: FakeToolBox, conversation: list[Message] | None = None, policy: AgentPolicy | None = None) -> list[AgentEvent]:
    asked = conversation or [Message(role=Role.USER, content="Read me the procurement section of Money Stuff.")]
    return [event async for event in agent_loop.run(asked, llm, tools, policy or AgentPolicy(filler_phrases=["Checking."]))]


def spoken(events: list[AgentEvent]) -> str:
    return "".join(event.text for event in events if isinstance(event, AnswerDelta))


async def test_a_reading_is_spoken_whole_with_no_filler_and_no_second_model_call() -> None:
    llm = ScriptedLLM([read_reply({"newsletter": "Money Stuff", "section": "Procurement"})])
    events = await run_loop(llm, ReadingToolBox(result=READING))
    assert not any(isinstance(event, FillerSpoken) for event in events)
    assert spoken(events).strip() == READING
    transcript = events[-1].transcript
    assert isinstance(events[-1], Done) and len(llm.seen_messages) == 1
    assert transcript.final_answer == READING and transcript.spoken_text == READING and not transcript.truncated
    assert transcript.conversation[-1] == Message(role=Role.ASSISTANT, content=READING)


async def test_a_reading_is_not_cut_by_the_spoken_answer_cap() -> None:
    long_reading = "Reading Money Stuff: Procurement.\n" + "\n".join(f"Paragraph {index} has a few words in it." for index in range(100)) + "\nThat's the end of Money Stuff."
    events = await run_loop(ScriptedLLM([read_reply({"newsletter": "Money Stuff"})]), ReadingToolBox(result=long_reading), policy=AgentPolicy(filler_phrases=["Checking."], word_budget=20))
    assert spoken(events).strip() == long_reading


async def test_a_failure_sentence_goes_back_to_the_model_to_explain() -> None:
    llm = ScriptedLLM([read_reply({"newsletter": "Matt Taibbi"}), text_reply("You have no newsletter by that name today.")])
    events = await run_loop(llm, ReadingToolBox(result='No newsletter matching "Matt Taibbi" on Monday, November 16.'))
    assert spoken(events) == "You have no newsletter by that name today."


async def test_two_calls_in_one_round_go_back_to_the_model() -> None:
    llm = ScriptedLLM([read_reply({"newsletter": "Money Stuff"}, {"newsletter": "The Morning"}), text_reply("Which one first?")])
    assert spoken(await run_loop(llm, ReadingToolBox(result=READING))) == "Which one first?"


async def test_a_repeated_call_goes_back_to_the_model() -> None:
    failure = 'No section matching "Binance" in Money Stuff.'
    llm = ScriptedLLM(
        [read_reply({"newsletter": "Money Stuff", "section": "Binance"}), read_reply({"newsletter": "Money Stuff", "section": "Binance"}), text_reply("There is no Binance section today.")]
    )
    assert spoken(await run_loop(llm, ReadingToolBox(result=failure))) == "There is no Binance section today."


async def test_a_refused_call_goes_back_to_the_model() -> None:
    llm = ScriptedLLM([read_reply({"newsletter": 5}), text_reply("Sorry, which newsletter?")])
    assert spoken(await run_loop(llm, ReadingToolBox(result=READING))) == "Sorry, which newsletter?"


async def test_a_failed_call_goes_back_to_the_model() -> None:
    llm = ScriptedLLM([read_reply({"newsletter": "Money Stuff"}), text_reply("I could not open your newsletters.")])
    assert spoken(await run_loop(llm, ReadingToolBox(fail=True))) == "I could not open your newsletters."


async def test_a_replayed_reading_reaches_the_model_as_its_first_and_last_lines() -> None:
    conversation = [
        Message(role=Role.USER, content="Read me the procurement section of Money Stuff."),
        Message(role=Role.ASSISTANT, content=READING),
        Message(role=Role.USER, content="Continue."),
    ]
    llm = ScriptedLLM([read_reply({"section": "next"})])
    await run_loop(llm, ReadingToolBox(result=READING), conversation)
    replayed = [message.content for message in llm.seen_messages[0] if message.role == Role.ASSISTANT]
    assert replayed == ["Reading Money Stuff: Procurement.\n[read aloud]\nNext is Things happen. Say continue to hear it."]
