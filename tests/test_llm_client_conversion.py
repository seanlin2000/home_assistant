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


def test_ollama_conversion_of_tool_and_assistant_messages() -> None:
    messages = sample_conversation()
    assert to_ollama_message(messages[3]) == {"role": "tool", "content": "result a", "tool_name": "search_and_read"}
    assistant = to_ollama_message(messages[2])
    assert assistant["tool_calls"][0]["function"] == {"name": "search_and_read", "arguments": {"query": "x"}}
