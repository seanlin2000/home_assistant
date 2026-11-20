"""newsletters_list and newsletter_summarize (design doc v2/14 section 3.5), called directly against the benchmark's made-up day of issues
(benchmark/fixtures/newsletters), and the route, filler, tool table, and benchmark questions around them."""

import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer

from assistant_core.agent_loop import filler_for
from assistant_core.models import DEFAULT_NEWSLETTERS_FILLER_PHRASES, DEFAULT_REDDIT_FILLER_PHRASES, NEWSLETTERS_TOOL_NAMES, AgentPolicy, Route, ToolCall
from assistant_core.router import DIRECTIVES, NEWSLETTERS_DIRECTIVE
from assistant_core.tool_guards import Tier, load_tool_table
from assistant_core.tools import McpToolBox
from benchmark.mcp_process import NEWSLETTERS_DIR, NEWSLETTERS_RECORDED_ON
from benchmark.records import Category, load_questions
from newsletters_mcp.answers import sections_mentioning
from newsletters_mcp.issue import Issue, Section
from newsletters_mcp.register import NEWSLETTER_SUMMARIZE_TOOL_NAME, NEWSLETTERS_LIST_TOOL_NAME, register_newsletters_tools
from newsletters_mcp.settings import NewslettersSettings
from newsletters_mcp.store import PullStatus, issue_markdown, issue_path, read_issues, write_status
from utils.snapshot_utils import write_file_atomically

RECORDED_ON = date.fromisoformat(NEWSLETTERS_RECORDED_ON)


@pytest.fixture
def settings(tmp_path: Path) -> NewslettersSettings:
    """A copy of the benchmark's day, so a test can add a status file or an issue without touching the fixture."""
    folder = tmp_path / "newsletters"
    shutil.copytree(NEWSLETTERS_DIR, folder)
    return NewslettersSettings(dir=folder, today=RECORDED_ON)


async def call_tool(settings: NewslettersSettings, name: str, **arguments: Any) -> str:
    server = MCPServer("test")
    register_newsletters_tools(server, settings)
    async with McpToolBox(server) as toolbox:
        return await toolbox.call(ToolCall(id="1", name=name, arguments=arguments))


async def listing(settings: NewslettersSettings, **arguments: Any) -> str:
    return await call_tool(settings, NEWSLETTERS_LIST_TOOL_NAME, **arguments)


async def summary(settings: NewslettersSettings, **arguments: Any) -> str:
    return await call_tool(settings, NEWSLETTER_SUMMARIZE_TOOL_NAME, **arguments)


def issue_lines(reply: str) -> list[str]:
    return [line for line in reply.split("\n") if line.startswith("- ")]


def add_issue(settings: NewslettersSettings, issue: Issue) -> None:
    write_file_atomically(issue_path(settings.dir, issue), issue_markdown(issue).encode())


# ---------------------------------------------------------------- newsletters_list


async def test_the_list_names_each_issue_with_its_headline_and_sections(settings: NewslettersSettings) -> None:
    reply = await listing(settings)
    assert reply.startswith("Newsletters for Monday, November 16:")
    lines = issue_lines(reply)
    assert [line.removeprefix("- ").split(",")[0] for line in lines] == ["WSJ Markets A.M.", "The Morning", "The Daily Widget", "Money Stuff"]
    assert 'Money Stuff, "Hypothetical Widgets"' in lines[3] and "Sections: Hypothetical widgets; Procurement; Things happen." in lines[3]
    assert "Opening" not in reply


async def test_the_list_and_a_summary_leave_out_the_arrival_time(settings: NewslettersSettings) -> None:
    for reply in (await listing(settings), await summary(settings, newsletter="Money Stuff")):
        assert not re.search(r"\d:\d\d", reply)


async def test_a_named_newsletter_lists_only_its_sections(settings: NewslettersSettings) -> None:
    lines = issue_lines(await listing(settings, newsletter="money stuff"))
    assert len(lines) == 1 and "Money Stuff" in lines[0]


async def test_a_morning_letter_said_as_am_is_found(settings: NewslettersSettings) -> None:
    lines = issue_lines(await listing(settings, newsletter="markets am"))
    assert len(lines) == 1 and "WSJ Markets A.M." in lines[0]


async def test_a_topic_keeps_only_the_issues_and_sections_that_mention_it(settings: NewslettersSettings) -> None:
    lines = issue_lines(await listing(settings, topic="Widgetron"))
    assert len(lines) == 2
    assert "WSJ Markets A.M." in lines[0] and "Sections: Stocks I'm Watching." in lines[0]
    assert "Money Stuff" in lines[1] and "Sections: Hypothetical widgets." in lines[1]


async def test_a_newsletter_and_a_topic_search_one_issue(settings: NewslettersSettings) -> None:
    lines = issue_lines(await listing(settings, newsletter="Money Stuff", topic="fee"))
    assert len(lines) == 1 and "Sections: Procurement." in lines[0]


def test_a_topic_ending_in_punctuation_is_found_as_a_whole_word() -> None:
    issue = Issue(
        publication="WSJ Markets A.M.",
        subject="s",
        headline="h",
        received=datetime(2026, 11, 17, 6, 21).astimezone(),
        message_id="<a@example.com>",
        sections=[
            Section(title="Your 401(k)", paragraphs=["Index funds hold Nvidia."]),
            Section(title="Other", paragraphs=["A 401(k)s plan is not this one.", "Neither is k401(k)."]),
        ],
    )
    assert [section.title for section in sections_mentioning(issue, "401(k)")] == ["Your 401(k)"]


async def test_a_topic_nothing_mentions_says_so(settings: NewslettersSettings) -> None:
    assert await listing(settings, topic="Binance") == 'No section of the newsletters on Monday, November 16 mentions "Binance".'


async def test_an_unknown_newsletter_names_the_days_newsletters(settings: NewslettersSettings) -> None:
    reply = await listing(settings, newsletter="Matt Taibbi")
    assert reply == 'No newsletter matching "Matt Taibbi" on Monday, November 16. That day\'s newsletters are: WSJ Markets A.M., The Morning, The Daily Widget, Money Stuff.'


async def test_a_day_with_no_issues_says_so(settings: NewslettersSettings) -> None:
    assert await listing(settings, date="yesterday") == "No newsletters arrived on Sunday, November 15."


async def test_a_date_that_cannot_be_read_asks_for_another(settings: NewslettersSettings) -> None:
    assert (await listing(settings, date="last week")).startswith('Cannot read "last week" as a day.')


async def test_a_failed_last_pull_is_noted(settings: NewslettersSettings) -> None:
    failed_at = datetime(2026, 11, 16, 15, 0).astimezone()
    write_status(settings.dir, PullStatus(last_success=failed_at - timedelta(hours=1), last_failure=failed_at, failure_kind="sign-in refused"))
    reply = await listing(settings)
    assert reply.endswith("The last newsletter pull failed at 3:00 PM (sign-in refused), so newer issues may be missing.")


async def test_a_pull_that_was_never_set_up_says_so(tmp_path: Path) -> None:
    settings = NewslettersSettings(dir=tmp_path / "empty", today=RECORDED_ON)
    write_status(settings.dir, PullStatus(last_failure=datetime(2026, 11, 16, 15, 0).astimezone(), failure_kind="not set up"))
    assert (await listing(settings)).startswith("Newsletters are not set up yet")


# ---------------------------------------------------------------- newsletter_summarize


async def test_a_summary_request_returns_the_whole_issue_with_its_quotations(settings: NewslettersSettings) -> None:
    reply = await summary(settings, newsletter="Money Stuff")
    assert reply.startswith('Money Stuff, "Hypothetical Widgets".\n')
    assert "## Hypothetical widgets" in reply and "## Procurement" in reply and "## Things happen" in reply
    assert '> Widgetron Inc. said Monday that its board "regularly reviews all strategic options,"' in reply


async def test_a_named_section_returns_only_that_section(settings: NewslettersSettings) -> None:
    reply = await summary(settings, newsletter="money stuff", section="procurement")
    assert "## Procurement" in reply and "$40 million" in reply
    assert "## Hypothetical widgets" not in reply


async def test_an_unknown_section_names_the_issues_sections(settings: NewslettersSettings) -> None:
    reply = await summary(settings, newsletter="Money Stuff", section="Binance")
    assert reply == 'No section matching "Binance" in Money Stuff. Its sections are: Hypothetical widgets; Procurement; Things happen.'


async def test_a_long_issue_is_cut_between_sections_and_names_what_was_left_out(settings: NewslettersSettings) -> None:
    reply = await summary(settings.model_copy(update={"summary_max_words": 120}), newsletter="Money Stuff")
    assert "## Hypothetical widgets" in reply and "## Procurement" not in reply
    assert reply.endswith("Left out for length: Procurement; Things happen. Ask for one of them by name.")


async def test_two_newsletters_matching_one_name_ask_which(settings: NewslettersSettings) -> None:
    morning_letter = read_issues(settings.dir, RECORDED_ON)[0]
    add_issue(settings, morning_letter.model_copy(update={"publication": "WSJ Markets P.M.", "message_id": "<pm@example.com>", "received": morning_letter.received + timedelta(hours=10)}))
    reply = await summary(settings, newsletter="WSJ Markets")
    assert reply == 'Several newsletters on Monday, November 16 match "WSJ Markets": WSJ Markets A.M., WSJ Markets P.M.. Ask the user which one.'


async def test_every_string_argument_has_a_maximum_length() -> None:
    server = MCPServer("test")
    register_newsletters_tools(server, NewslettersSettings())
    async with McpToolBox(server) as toolbox:
        specs = {spec.name: spec for spec in await toolbox.list_tools()}
    for name in NEWSLETTERS_TOOL_NAMES:
        properties = specs[name].input_schema["properties"]
        assert all("maxLength" in schema for schema in properties.values()), name


# ---------------------------------------------------------------- around the tools


def test_both_tools_are_private_reads_that_mark_the_exchange_untrusted() -> None:
    table = load_tool_table()
    for name in NEWSLETTERS_TOOL_NAMES:
        assert (table.tools[name].tier, table.tools[name].marks_untrusted) == (Tier.READ_PRIVATE, True)


def test_the_newsletters_route_has_its_directive_and_filler() -> None:
    assert DIRECTIVES[Route.NEWSLETTERS] == NEWSLETTERS_DIRECTIVE
    assert filler_for(NEWSLETTERS_LIST_TOOL_NAME, AgentPolicy()) in DEFAULT_NEWSLETTERS_FILLER_PHRASES


def test_reddits_filler_no_longer_warns_it_can_be_slow() -> None:
    assert not any("slow" in phrase or "do my best" in phrase for phrase in DEFAULT_REDDIT_FILLER_PHRASES)


def test_the_newsletter_questions_run_only_on_the_benchmarks_tool_server() -> None:
    questions = [question for question in load_questions(Path("benchmark/questions.yaml")).questions if Route.NEWSLETTERS in question.required_tools]
    assert {question.id for question in questions} == {"K96", "K97", "K98", "K99", "H100"}
    assert all(question.needs_benchmark_tool_server and question.today == RECORDED_ON for question in questions)
    assert sum(question.category == Category.K for question in questions) == 4
