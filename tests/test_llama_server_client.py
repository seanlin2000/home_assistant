from assistant_core.llama_server_client import CONVERSATION_SLOT, StreamedReply, parse_stream_line, response_request_body, thinking_template_options, to_openai_message, to_openai_tool
from assistant_core.models import AgentPolicy, MalformedToolCall, Message, Role, ToolCall, ToolCallRequest, ToolSpec


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
    assert "chat_template_kwargs" not in body


def test_a_thinking_level_turns_thinking_on_at_that_effort_and_a_bool_switches_it() -> None:
    assert thinking_template_options("medium") == {"enable_thinking": True, "reasoning_effort": "medium"}
    assert thinking_template_options(False) == {"enable_thinking": False}
    assert thinking_template_options(None) == {}
    body = response_request_body([Message(role=Role.USER, content="hi")], [], AgentPolicy(think="medium"))
    assert body["chat_template_kwargs"] == {"enable_thinking": True, "reasoning_effort": "medium"}


def test_thinking_is_kept_on_the_message_but_never_streamed_as_spoken_text() -> None:
    reply = StreamedReply()
    assert reply.absorb(chunk({"reasoning_content": "Twelve percent of 250 "}), 0.0) == []
    assert reply.absorb(chunk({"reasoning_content": "is 30."}), 0.0) == []
    assert reply.absorb(chunk({"content": "It is thirty."}), 0.0) == ["It is thirty."]
    message = reply.assistant_message()
    assert (message.thinking, message.content) == ("Twelve percent of 250 is 30.", "It is thirty.")


def test_the_model_reads_tool_schemas_without_the_titles_that_repeat_each_argument_name() -> None:
    schema = {"title": "percentArguments", "type": "object", "properties": {"title": {"title": "Title", "type": "string"}, "a": {"title": "A", "type": "number"}}}
    sent = to_openai_tool(ToolSpec(name="percent", description="Percent questions.", input_schema=schema))["function"]["parameters"]
    assert sent == {"type": "object", "properties": {"title": {"type": "string"}, "a": {"type": "number"}}}
