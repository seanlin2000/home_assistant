from assistant_core.llama_server_client import CONVERSATION_SLOT, StreamedReply, parse_stream_line, response_request_body, to_openai_message
from assistant_core.models import AgentPolicy, MalformedToolCall, Message, Role, ToolCall, ToolCallRequest


def chunk(delta: dict, finish_reason: str | None = None, timings: dict | None = None) -> dict:
    body = {"choices": [{"delta": delta, "finish_reason": finish_reason}]}
    if timings is not None:
        body["timings"] = timings
    return body


def test_stream_lines_are_parsed_and_the_end_marker_is_skipped() -> None:
    assert parse_stream_line('data: {"choices": []}') == {"choices": []}
    assert parse_stream_line("data: [DONE]") is None
    assert parse_stream_line("") is None


def test_text_streams_in_order_and_the_timings_become_fresh_and_cached_tokens() -> None:
    reply = StreamedReply()
    assert reply.absorb(chunk({"content": "It is "}), 0.0) == ["It is "]
    assert reply.absorb(chunk({"content": "four."}), 0.0) == ["four."]
    reply.absorb(chunk({}, "stop", {"prompt_n": 30, "cache_n": 2300, "predicted_n": 5, "prompt_ms": 120.0, "predicted_ms": 100.0}), 0.0)
    stats = reply.stats("gemma-4-e4b", 0.0)
    assert reply.assistant_message().content == "It is four."
    assert (stats.fresh_prompt_tokens, stats.cached_prompt_tokens, stats.prompt_tokens) == (30, 2300, 2330)
    assert stats.prompt_eval_seconds == 0.12 and stats.stop_reason == "stop" and stats.slot == CONVERSATION_SLOT


def test_tool_call_fragments_are_joined_by_index() -> None:
    reply = StreamedReply()
    reply.absorb(chunk({"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "percent", "arguments": '{"kind": "of", '}}]}), 0.0)
    reply.absorb(chunk({"tool_calls": [{"index": 0, "function": {"arguments": '"a": 15, "b": 80}'}}]}), 0.0)
    events = reply.tool_call_events()
    assert events == [ToolCallRequest(call=ToolCall(id="c1", name="percent", arguments={"kind": "of", "a": 15, "b": 80}))]
    assert reply.assistant_message().tool_calls[0].name == "percent"


def test_a_call_with_broken_arguments_is_malformed_and_kept_out_of_the_message() -> None:
    reply = StreamedReply()
    reply.absorb(chunk({"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "percent", "arguments": '{"kind": '}}]}), 0.0)
    assert isinstance(reply.tool_call_events()[0], MalformedToolCall)
    assert reply.assistant_message().tool_calls == []


def test_messages_convert_to_the_openai_shape_with_json_arguments() -> None:
    call = ToolCall(id="c1", name="percent", arguments={"a": 15})
    assistant = to_openai_message(Message(role=Role.ASSISTANT, content="", tool_calls=[call]))
    assert assistant["tool_calls"][0] == {"id": "c1", "type": "function", "function": {"name": "percent", "arguments": '{"a": 15}'}}
    assert to_openai_message(Message(role=Role.TOOL, content="12", tool_call_id="c1", tool_name="percent")) == {"role": "tool", "tool_call_id": "c1", "content": "12"}


def test_every_response_request_is_pinned_to_the_conversation_slot() -> None:
    body = response_request_body([Message(role=Role.USER, content="hi")], [], AgentPolicy(temperature=0.5, max_output_tokens=600))
    assert body["id_slot"] == CONVERSATION_SLOT and body["cache_prompt"] is True and body["stream"] is True
    assert body["tools"] is None and body["temperature"] == 0.5 and body["max_tokens"] == 600
