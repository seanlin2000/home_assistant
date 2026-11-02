"""The prompt cache tab: each model call's prompt is rebuilt and split into the parts the harness lays out, where the cache stopped is judged against
what should have been cached, and the slots are read from llama-server (design doc v2/13 section 3.10)."""

from datetime import date
from pathlib import Path
from typing import Any

import httpx

from assistant_core.converse_protocol import ConverseRequest
from assistant_core.exchange_record import ExchangeTrace
from assistant_core.models import GenerationStats, Message, Role, ToolCall, ToolCallRecord, ToolSpec, Transcript
from assistant_service.exchange_log import ExchangeArchive, ExchangeLog, TraceLog
from dashboard.app import build_app
from dashboard.exchange_views import ExchangeStore
from dashboard.prompt_layout import SegmentKind, Verdict, prompt_layout, prompt_parts
from dashboard.settings import LlamaServerAccess
from dashboard.slot_views import slots_view
from ops.pipeline_runs import PipelineRunLog

TOOLS = [ToolSpec(name="search_and_read", description="Search the web", input_schema={}), ToolSpec(name="calculate", description="Do math", input_schema={})]
BLOCK = "Today is Monday."
MODEL_TURN = "<model>"  # opens the model's turn, both after a prompt and before a reply in the history, as Gemma's template does
SEARCH_CALL = ToolCall(id="call_1", name="search_and_read", arguments={"query": "1995 World Series"})
REPORTED_SLOTS = [
    {"id": 0, "n_ctx": 18432, "is_processing": False, "n_prompt_tokens": 3104, "n_prompt_tokens_cache": 2900, "next_token": [{"n_decoded": 70}]},
    {"id": 1, "n_ctx": 18432, "is_processing": False},
]


class TemplatingServer:
    """Stands in for llama-server: a template with the tool names inside the system turn and a model opener at the end, one token per character
    after a start token, and the slots as llama-server reports them. Unreachable, it fails as a stopped server does."""

    def __init__(self, reachable: bool = True) -> None:
        self.reachable = reachable

    async def render_prompt(self, messages: list[Message], tools: list[ToolSpec]) -> str:
        self.refuse_when_unreachable()
        return "".join(rendered_turn(message, tools) for message in messages) + MODEL_TURN

    async def count_tokens(self, text: str) -> int:
        self.refuse_when_unreachable()
        return len(text) + 1

    async def slots(self) -> list[dict[str, Any]]:
        self.refuse_when_unreachable()
        return REPORTED_SLOTS

    def refuse_when_unreachable(self) -> None:
        if not self.reachable:
            raise httpx.ConnectError("connection refused")


def rendered_turn(message: Message, tools: list[ToolSpec]) -> str:
    declared = "{" + ",".join(tool.name for tool in tools) + "}" if message.role == Role.SYSTEM and tools else ""
    calls = "".join(f"call:{call.name}" for call in message.tool_calls)
    opener = MODEL_TURN if message.role == Role.ASSISTANT else f"<{message.role.value}>"
    return f"{opener}{message.content}{declared}{calls}</>"


def search_trace(tools: list[ToolSpec] = TOOLS, block: str = BLOCK) -> ExchangeTrace:
    """A follow-up that searched once: an earlier exchange, the question, a tool round, the answer."""
    transcript = Transcript(
        model="small",
        system_prompt="Be brief.",
        conversation=[
            Message(role=Role.USER, content="Hello"),
            Message(role=Role.ASSISTANT, content="Hi."),
            Message(role=Role.USER, content="Who won in 1995?"),
            Message(role=Role.ASSISTANT, tool_calls=[SEARCH_CALL]),
            Message(role=Role.TOOL, content="The Braves.", tool_call_id="call_1", tool_name="search_and_read"),
            Message(role=Role.ASSISTANT, content="The Atlanta Braves."),
        ],
        per_question_block=block,
    )
    return ExchangeTrace(exchange_id="e1", recorded_at="2026-11-02T12:00:00+00:00", source="home_assistant", transcript=transcript, tool_specs=tools)


async def recorded_sizes(trace: ExchangeTrace) -> list[int]:
    """What llama-server would have recorded for each call's prompt: the prompt before the tool round, then the prompt before the answer."""
    server, parts = TemplatingServer(), prompt_parts(trace)
    return [await server.count_tokens(await server.render_prompt(parts.prompt_before(start), trace.tool_specs)) for start in parts.reply_starts]


def calls_with(sizes: list[int], cached: list[int | None]) -> list[GenerationStats]:
    return [GenerationStats(model="small", prompt_tokens=size, cached_prompt_tokens=hit, total_seconds=1.0) for size, hit in zip(sizes, cached)]


async def test_the_prompt_splits_into_the_parts_the_harness_lays_out_in_order() -> None:
    trace = search_trace()
    sizes = await recorded_sizes(trace)
    layout = await prompt_layout(trace, calls_with(sizes, [None, None]), TemplatingServer())
    first, second = layout.calls
    expected_order = [SegmentKind.SYSTEM, SegmentKind.TOOLS, SegmentKind.EARLIER, SegmentKind.BLOCK, SegmentKind.QUESTION]
    assert [segment.kind for segment in first.segments] == expected_order
    assert [segment.kind for segment in second.segments] == expected_order + [SegmentKind.TOOL_ROUND]
    assert layout.exact and layout.note == ""
    assert [(call.prompt_tokens, sum(segment.tokens for segment in call.segments)) for call in layout.calls] == [(size, size) for size in sizes]
    assert second.segments[5].label == "tool round 1 (search_and_read)"
    assert [tool.name for tool in layout.tools] == ["search_and_read", "calculate"]
    assert all(tool.tokens > 0 for tool in layout.tools)


async def test_each_part_keeps_its_text_as_the_model_read_it_and_together_they_are_the_whole_prompt() -> None:
    trace = search_trace()
    layout = await prompt_layout(trace, calls_with(await recorded_sizes(trace), [None, None]), TemplatingServer())
    whole = await TemplatingServer().render_prompt(prompt_parts(trace).last_prompt(), trace.tool_specs)
    assert "".join(layout.part_texts.values()) == whole
    assert layout.part_texts["system rules"].startswith("<system>Be brief.")
    assert layout.part_texts["tool definitions"].startswith("{search_and_read,calculate}")
    assert "Who won in 1995?" in layout.part_texts["question"]
    assert "text" not in layout.calls[0].model_dump()["segments"][0]


async def test_a_cache_reaching_past_the_tools_then_the_whole_last_prompt_is_as_expected() -> None:
    trace = search_trace()
    sizes = await recorded_sizes(trace)
    probe = await prompt_layout(trace, calls_with(sizes, [None, None]), TemplatingServer())
    tools_end = probe.calls[0].segments[1].end
    layout = await prompt_layout(trace, calls_with(sizes, [tools_end, sizes[0]]), TemplatingServer())
    assert [call.verdict for call in layout.calls] == [Verdict.EXPECTED, Verdict.EXPECTED]
    assert layout.calls[0].explanation == "cache held through tool definitions, read from earlier exchanges"
    assert layout.calls[1].explanation == "cache held through question, read from tool round 1 (search_and_read)"


async def test_a_cache_stopping_inside_the_tools_is_early_and_an_empty_one_a_full_re_read() -> None:
    trace = search_trace()
    sizes = await recorded_sizes(trace)
    layout = await prompt_layout(trace, calls_with(sizes, [5, 0]), TemplatingServer())
    assert [call.verdict for call in layout.calls] == [Verdict.EARLY, Verdict.FULL_REREAD]
    assert layout.calls[0].explanation.startswith("cache held 5 of the")
    assert layout.calls[1].explanation == "full re-read: nothing came from the cache"


async def test_a_trace_without_tool_definitions_infers_their_size_and_does_not_judge_the_first_call() -> None:
    with_tools = await recorded_sizes(search_trace())
    layout = await prompt_layout(search_trace(tools=[], block=""), calls_with(with_tools, [40, with_tools[0]]), TemplatingServer())
    assert not layout.exact and layout.note.startswith("Recorded before traces kept the tool definitions")
    assert [segment.kind for segment in layout.calls[0].segments][:2] == [SegmentKind.SYSTEM, SegmentKind.TOOLS]
    assert layout.calls[0].segments[1].label == "tool definitions and per-question block (not recorded)"
    assert [call.verdict for call in layout.calls] == [Verdict.UNKNOWN, Verdict.EXPECTED]
    assert [call.prompt_tokens for call in layout.calls] == with_tools


def test_slots_show_their_share_of_the_pool_and_what_the_last_request_left() -> None:
    view = slots_view(REPORTED_SLOTS, pool_tokens=18432, conversation_tokens=16384)
    conversation, quiet = view.slots
    assert (conversation.role, conversation.share_tokens, conversation.holds_tokens, conversation.last_cached_tokens) == ("conversation", 16384, 3174, 2900)
    assert (quiet.role, quiet.share_tokens, quiet.last_prompt_tokens, quiet.holds_tokens) == ("router and quiet requests", 2048, None, None)


def kept_store(tmp_path: Path, tool_specs: list[ToolSpec]) -> ExchangeStore:
    """One exchange kept the way the harness keeps it, with the tool definitions the transcript carried in memory."""
    records, traces = ExchangeLog(tmp_path / "exchanges"), TraceLog(tmp_path / "traces")
    trace = search_trace()
    call = ToolCallRecord(round_index=0, call=SEARCH_CALL, result="The Braves.", seconds=1.0)
    transcript = trace.transcript.model_copy(update={"tool_specs": tool_specs, "tool_call_records": [call], "model_calls": calls_with([100, 140], [80, 100])})
    ExchangeArchive(records, traces).keep(ConverseRequest(conversation_id="c1", conversation=transcript.conversation[:3]), transcript)
    return ExchangeStore(records, traces, PipelineRunLog(tmp_path / "pipeline_runs"))


def client_with(store: ExchangeStore, server: TemplatingServer | None) -> httpx.AsyncClient:
    access = LlamaServerAccess(client=server, pool_tokens=18432, conversation_tokens=16384) if server else None
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=build_app(store, ["mac.lan:8775"], llama_server=access)), base_url="http://mac.lan:8775")


def test_the_trace_keeps_the_tool_definitions_the_transcript_leaves_out_when_written(tmp_path: Path) -> None:
    store = kept_store(tmp_path, TOOLS)
    day = store.days()[0].day
    _record, trace = store.record_and_trace(date.fromisoformat(day), 0)
    assert [tool.name for tool in trace.tool_specs] == ["search_and_read", "calculate"]
    assert trace.transcript.per_question_block == BLOCK
    assert "tool_specs" not in trace.transcript.model_dump()


async def test_the_api_rebuilds_an_exchanges_prompt_and_reads_the_slots(tmp_path: Path) -> None:
    store = kept_store(tmp_path, TOOLS)
    day = store.days()[0].day
    async with client_with(store, TemplatingServer()) as client:
        layout = (await client.get(f"/api/days/{day}/exchanges/0/prompt")).json()
        slots = (await client.get("/api/slots")).json()
        missing = await client.get(f"/api/days/{day}/exchanges/5/prompt")
    assert [call["number"] for call in layout["calls"]] == [1, 2]
    assert [slot["role"] for slot in slots["slots"]] == ["conversation", "router and quiet requests"]
    assert missing.status_code == 404


async def test_the_tab_says_why_when_llama_server_is_down_or_its_key_is_missing(tmp_path: Path) -> None:
    store = kept_store(tmp_path, TOOLS)
    day = store.days()[0].day
    async with client_with(store, TemplatingServer(reachable=False)) as client:
        down = await client.get("/api/slots")
        down_prompt = await client.get(f"/api/days/{day}/exchanges/0/prompt")
    async with client_with(store, None) as client:
        no_key = await client.get("/api/slots")
    assert (down.status_code, down.json()["error"]) == (503, "llama-server did not answer: ConnectError: connection refused")
    assert down_prompt.status_code == 503
    assert no_key.status_code == 503 and "key was not found" in no_key.json()["error"]
