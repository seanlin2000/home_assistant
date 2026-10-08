"""The harness service: its access rules, its newline-delimited JSON stream, its per-conversation state, and what it says when a dependency is down."""

from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path

import httpx
import pytest

from assistant_core.converse_protocol import CONVERSE_PATH, HEALTH_PATH, ConverseRequest, HarnessHealth, line_to_event
from assistant_core.harness_client import HarnessClient
from assistant_core.models import AgentEvent, AgentPolicy, AnswerDelta, Done, LLMEvent, Message, Role, ToolSpec
from assistant_service.app import AccessRules, build_app
from assistant_service.conversation_state import ConversationState
from assistant_service.exchange_log import ExchangeLog
from assistant_service.harness import MODEL_UNREACHABLE_ANSWER, Harness
from assistant_service.settings import ALLOWED_HOSTS_VARIABLE, load_harness_config
from serving.settings import load_serving_config
from tests.fakes import ScriptedLLM, text_reply

API_KEY = "test-key"
UNREACHABLE_TOOL_SERVER = "http://127.0.0.1:1/mcp"
QUESTION = [Message(role=Role.USER, content="How tall is the Eiffel Tower?")]


class UnreachableLLM(ScriptedLLM):
    def __init__(self) -> None:
        super().__init__([])

    async def chat(self, messages: list[Message], tools: list[ToolSpec], policy: AgentPolicy) -> AsyncIterator[LLMEvent]:
        raise httpx.ConnectError("connection refused")
        yield


def harness_with(llm: ScriptedLLM, tmp_path: Path) -> Harness:
    return Harness(
        llm=llm,
        tool_server_url=UNREACHABLE_TOOL_SERVER,
        policy=AgentPolicy(),
        state=ConversationState(tmp_path / "state.sqlite3"),
        exchange_log=ExchangeLog(tmp_path / "exchanges"),
        quiet_minutes=5,
    )


def client_for(harness: Harness, allowed_hosts: list[str] | None = None) -> httpx.AsyncClient:
    app = build_app(harness, AccessRules(api_key=API_KEY, allowed_hosts=allowed_hosts or ["mac.lan:8770"]))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mac.lan:8770")


async def collect(harness: Harness, conversation_id: str = "conversation-1") -> list[AgentEvent]:
    return [event async for event in harness.converse(ConverseRequest(conversation_id=conversation_id, conversation=QUESTION))]


async def test_an_answer_streams_as_one_json_line_per_event(tmp_path: Path) -> None:
    harness = harness_with(ScriptedLLM([text_reply("About ", "330 metres.")]), tmp_path)
    async with client_for(harness) as client:
        request = ConverseRequest(conversation_id="conversation-1", conversation=QUESTION)
        response = await client.post(CONVERSE_PATH, content=request.model_dump_json(), headers={"authorization": f"Bearer {API_KEY}"})
    events = [line_to_event(line) for line in response.text.splitlines()]
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert [event.text for event in events if isinstance(event, AnswerDelta)] == ["About ", "330 metres."]
    assert isinstance(events[-1], Done)
    assert events[-1].transcript.final_answer == "About 330 metres."


async def test_the_harness_client_reads_the_same_stream(tmp_path: Path) -> None:
    harness = harness_with(ScriptedLLM([text_reply("About 330 metres.")]), tmp_path)
    async with client_for(harness) as http:
        client = HarnessClient("http://mac.lan:8770", API_KEY, client=http)
        events = [event async for event in client.converse(ConverseRequest(conversation_id="conversation-1", conversation=QUESTION))]
    assert events[-1].transcript.final_answer == "About 330 metres."


async def test_a_request_without_the_key_is_refused(tmp_path: Path) -> None:
    async with client_for(harness_with(ScriptedLLM([]), tmp_path)) as client:
        missing = await client.get(HEALTH_PATH)
        wrong = await client.get(HEALTH_PATH, headers={"authorization": "Bearer guess"})
    assert missing.status_code == 401
    assert wrong.status_code == 401


async def test_other_host_names_and_browser_pages_are_turned_away(tmp_path: Path) -> None:
    key = {"authorization": f"Bearer {API_KEY}"}
    async with client_for(harness_with(ScriptedLLM([]), tmp_path)) as client:
        assert (await client.get(HEALTH_PATH, headers=key | {"host": "evil.example:8770"})).status_code == 421
        assert (await client.get(HEALTH_PATH, headers=key | {"origin": "http://mac.lan:8770"})).status_code == 421


async def test_a_malformed_request_is_rejected_before_the_model_runs(tmp_path: Path) -> None:
    async with client_for(harness_with(ScriptedLLM([]), tmp_path)) as client:
        response = await client.post(CONVERSE_PATH, content=b'{"conversation": "not a list"}', headers={"authorization": f"Bearer {API_KEY}"})
    assert response.status_code == 422


async def test_health_reports_each_dependency(tmp_path: Path) -> None:
    class ReadyLLM(ScriptedLLM):
        async def is_ready(self) -> bool:
            return True

    async with client_for(harness_with(ReadyLLM([]), tmp_path)) as client:
        response = await client.get(HEALTH_PATH, headers={"authorization": f"Bearer {API_KEY}"})
    assert HarnessHealth.model_validate(response.json()) == HarnessHealth(status="degraded", llama_server=True, tool_server=False)


async def test_with_the_tool_server_down_the_model_still_answers(tmp_path: Path) -> None:
    llm = ScriptedLLM([text_reply("About 330 metres.")])
    events = await collect(harness_with(llm, tmp_path))
    assert events[-1].transcript.final_answer == "About 330 metres."
    assert events[-1].transcript.error is None


async def test_with_llama_server_down_the_harness_says_so(tmp_path: Path) -> None:
    events = await collect(harness_with(UnreachableLLM(), tmp_path))
    assert [event.text for event in events if isinstance(event, AnswerDelta)] == [MODEL_UNREACHABLE_ANSWER]
    assert "connection refused" in events[-1].transcript.error


async def test_every_exchange_is_logged_with_its_source(tmp_path: Path) -> None:
    harness = harness_with(ScriptedLLM([text_reply("About 330 metres.")]), tmp_path)
    [event async for event in harness.converse(ConverseRequest(conversation_id="c", conversation=QUESTION, source="benchmark"))]
    records = ExchangeLog(tmp_path / "exchanges").read_since(date.min)
    assert [(record.source, record.final_answer) for record in records] == [("benchmark", "About 330 metres.")]


async def test_conversations_quiet_for_five_minutes_are_forgotten(tmp_path: Path) -> None:
    class NotReadyLLM(ScriptedLLM):
        async def is_ready(self) -> bool:
            return False

    harness = harness_with(NotReadyLLM([]), tmp_path)
    state = ConversationState(tmp_path / "state.sqlite3")
    state.record_exchange("old", at=1_000.0)
    state.record_exchange("recent", at=1_000.0 + 4 * 60)
    await harness.check_in(now=1_000.0 + 6 * 60)
    assert state.quiet_since(10_000.0) == ["recent"]


def test_the_trust_mark_survives_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    first = ConversationState(path)
    first.record_exchange("conversation-1")
    first.mark_untrusted("conversation-1")
    first.close()
    assert ConversationState(path).is_untrusted("conversation-1")


def test_the_checked_in_config_loads_and_takes_the_window_from_the_served_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ALLOWED_HOSTS_VARIABLE, "192.168.1.152:8770, mac.local:8770")
    config = load_harness_config()
    serving = load_serving_config()
    assert config.allowed_hosts() == ["192.168.1.152:8770", "mac.local:8770"]
    assert config.policy(serving).context_tokens == serving.served_model.conversation_tokens
    assert config.service.tool_server_url.startswith("http://127.0.0.1:")
