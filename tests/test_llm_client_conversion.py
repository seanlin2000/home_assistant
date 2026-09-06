from assistant_core.anthropic_client import assistant_blocks, split_system_prompt, to_anthropic_messages
from assistant_core.llm_client import to_ollama_message
from assistant_core.models import Message, Role, ToolCall


def sample_conversation() -> list[Message]:
    call_a = ToolCall(id="a", name="search_and_read", arguments={"query": "x"})
    call_b = ToolCall(id="b", name="fetch_page", arguments={"url": "http://y"})
    return [
        Message(role=Role.SYSTEM, content="be brief"),
        Message(role=Role.USER, content="hi"),
        Message(role=Role.ASSISTANT, content="", tool_calls=[call_a, call_b]),
        Message(role=Role.TOOL, content="result a", tool_call_id="a", tool_name="search_and_read"),
        Message(role=Role.TOOL, content="result b", tool_call_id="b", tool_name="fetch_page"),
        Message(role=Role.ASSISTANT, content="done"),
    ]


def test_anthropic_conversion_groups_parallel_tool_results_into_one_user_message() -> None:
    system_text, conversation = split_system_prompt(sample_conversation())
    converted = to_anthropic_messages(conversation)
    assert system_text == "be brief"
    assert [message["role"] for message in converted] == ["user", "assistant", "user", "assistant"]
    tool_results = converted[2]["content"]
    assert [block["tool_use_id"] for block in tool_results] == ["a", "b"]
    assert converted[1]["content"][0] == {"type": "tool_use", "id": "a", "name": "search_and_read", "input": {"query": "x"}}


def test_anthropic_conversion_prefers_raw_provider_payload() -> None:
    payload = [{"type": "thinking", "thinking": "", "signature": "sig"}, {"type": "text", "text": "done"}]
    message = Message(role=Role.ASSISTANT, content="done", provider_payload=payload)
    assert assistant_blocks(message) is payload


def test_ollama_conversion_of_tool_and_assistant_messages() -> None:
    messages = sample_conversation()
    assert to_ollama_message(messages[3]) == {"role": "tool", "content": "result a", "tool_name": "search_and_read"}
    assistant = to_ollama_message(messages[2])
    assert assistant["tool_calls"][0]["function"] == {"name": "search_and_read", "arguments": {"query": "x"}}
