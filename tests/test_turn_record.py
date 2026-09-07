from datetime import UTC, datetime

from assistant_core.models import GenerationStats, Message, Role, Route, RouteDecision, ToolCall, ToolExchange, Transcript
from assistant_core.turn_record import TurnRecord, turn_record_from_transcript, turns_url_from_mcp_url


def searched_transcript() -> Transcript:
    call = ToolCall(id="c1", name="search_and_read", arguments={"query": "fed funds rate"})
    return Transcript(
        model="gemma4:12b",
        system_prompt="You are Jarvis.",
        conversation=[
            Message(role=Role.USER, content="Earlier question"),
            Message(role=Role.ASSISTANT, content="Earlier answer"),
            Message(role=Role.USER, content="What is the Fed rate today?"),
            Message(role=Role.ASSISTANT, content="It is three and a half to three and three quarters percent."),
        ],
        tool_exchanges=[ToolExchange(round_index=0, call=call, result="x" * 5000, seconds=4.2)],
        model_calls=[
            GenerationStats(model="gemma4:12b", prompt_tokens=1800, output_tokens=40, total_seconds=3.0),
            GenerationStats(model="gemma4:12b", prompt_tokens=6200, output_tokens=90, total_seconds=7.5),
        ],
        malformed_tool_calls=["{bad"],
        spoken_text="Let me pull some sources. It is three and a half to three and three quarters percent.",
        final_answer="It is three and a half to three and three quarters percent.",
        tool_call_count=1,
        total_seconds=15.1,
        time_to_first_token_seconds=1.2,
        time_to_first_spoken_seconds=1.4,
        route=RouteDecision(route=Route.SEARCH, source="model", detail="model classified", seconds=0.8),
    )


def test_record_keeps_the_debugging_fields_and_drops_page_text() -> None:
    record = turn_record_from_transcript(searched_transcript(), recorded_at=datetime(2026, 9, 7, 3, 0, tzinfo=UTC))
    assert record.recorded_at == "2026-09-07T03:00:00+00:00"
    assert record.user_text == "What is the Fed rate today?"
    assert record.history_turns == 2  # the earlier question and answer
    assert record.final_answer.startswith("It is three and a half")
    assert record.spoken_chars == len("Let me pull some sources. It is three and a half to three and three quarters percent.")
    assert record.route is not None and record.route.route == Route.SEARCH
    assert [call.prompt_tokens for call in record.model_calls] == [1800, 6200]
    assert record.tool_calls[0].name == "search_and_read"
    assert record.tool_calls[0].arguments == {"query": "fed funds rate"}
    assert record.tool_calls[0].result_chars == 5000
    assert "xxxx" not in record.model_dump_json()
    assert record.malformed_tool_call_count == 1
    assert record.time_to_first_spoken_seconds == 1.4


def test_failed_flag_covers_the_benchmark_gate_signals() -> None:
    healthy = turn_record_from_transcript(searched_transcript())
    assert healthy.failed  # one malformed call in the fixture
    clean = healthy.model_copy(update={"malformed_tool_call_count": 0})
    assert not clean.failed
    assert clean.model_copy(update={"final_answer": "  "}).failed
    assert clean.model_copy(update={"truncated": True}).failed
    assert clean.model_copy(update={"error": "boom"}).failed


def test_empty_conversation_produces_a_record_without_crashing() -> None:
    record = turn_record_from_transcript(Transcript(model="m", system_prompt="", conversation=[]))
    assert record.user_text == "" and record.history_turns == 0 and record.failed


def test_record_round_trips_through_json() -> None:
    record = turn_record_from_transcript(searched_transcript())
    assert TurnRecord.model_validate_json(record.model_dump_json()) == record


def test_turns_url_sits_beside_the_mcp_endpoint() -> None:
    assert turns_url_from_mcp_url("http://192.168.1.152:8765/mcp") == "http://192.168.1.152:8765/turns"
    assert turns_url_from_mcp_url("http://192.168.1.152:8765/mcp/") == "http://192.168.1.152:8765/turns"
    assert turns_url_from_mcp_url("http://127.0.0.1:8765") == "http://127.0.0.1:8765/turns"
