"""The frontier-model client used only by the benchmark baseline. Kept out of llm_client.py so the Home Assistant component does not need the anthropic package."""

import time
from collections.abc import AsyncIterator
from typing import Any

import anthropic

from assistant_core.models import AgentPolicy, Completion, GenerationStats, LLMEvent, Message, Role, TextDelta, ToolCall, ToolCallRequest, ToolSpec

ANTHROPIC_FALLBACK_BETA = "server-side-fallback-2026-06-01"
ANTHROPIC_FALLBACK_MODELS = [{"model": "claude-opus-4-8"}]


class AnthropicClient:
    """Runs the same loop against a frontier model. Thinking stays adaptive because Opus 5 misbehaves with it disabled; see design_docs/v1/DEVIATIONS.md."""

    def __init__(self, model: str, client: anthropic.AsyncAnthropic | None = None) -> None:
        self._model = model
        self._client = client or anthropic.AsyncAnthropic()

    @property
    def model_name(self) -> str:
        return self._model

    async def chat(self, messages: list[Message], tools: list[ToolSpec], policy: AgentPolicy) -> AsyncIterator[LLMEvent]:
        started = time.perf_counter()
        first_token_at: float | None = None
        async with self._client.beta.messages.stream(**self._request(messages, tools, policy)) as stream:
            async for event in stream:
                if event.type == "content_block_delta" and event.delta.type == "text_delta":
                    first_token_at = first_token_at or time.perf_counter()
                    yield TextDelta(text=event.delta.text)
            final = await stream.get_final_message()
        completion = anthropic_completion(final, started, first_token_at)
        for call in completion.message.tool_calls:
            yield ToolCallRequest(call=call)
        yield completion

    def _request(self, messages: list[Message], tools: list[ToolSpec], policy: AgentPolicy) -> dict[str, Any]:
        system_text, conversation = split_system_prompt(messages)
        request: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max(policy.max_output_tokens, 1024),
            "system": system_text,
            "messages": to_anthropic_messages(conversation),
            "betas": [ANTHROPIC_FALLBACK_BETA],
            "fallbacks": ANTHROPIC_FALLBACK_MODELS,
            "thinking": {"type": "adaptive"},
        }
        if tools:
            request["tools"] = [{"name": tool.name, "description": tool.description, "input_schema": tool.input_schema} for tool in tools]
        if policy.effort:
            request["output_config"] = {"effort": policy.effort}
        return request


def split_system_prompt(messages: list[Message]) -> tuple[str, list[Message]]:
    system_text = "\n\n".join(message.content for message in messages if message.role == Role.SYSTEM)
    return system_text, [message for message in messages if message.role != Role.SYSTEM]


def to_anthropic_messages(conversation: list[Message]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in conversation:
        if message.role == Role.TOOL:
            append_tool_result(converted, message)
        elif message.role == Role.ASSISTANT:
            converted.append({"role": "assistant", "content": assistant_blocks(message)})
        else:
            converted.append({"role": "user", "content": message.content})
    return converted


def append_tool_result(converted: list[dict[str, Any]], message: Message) -> None:
    block = {"type": "tool_result", "tool_use_id": message.tool_call_id, "content": message.content}
    # Results for parallel tool calls must share one user message, otherwise the model stops calling tools in parallel.
    if converted and converted[-1]["role"] == "user" and isinstance(converted[-1]["content"], list):
        converted[-1]["content"].append(block)
    else:
        converted.append({"role": "user", "content": [block]})


def assistant_blocks(message: Message) -> list[dict[str, Any]]:
    if message.provider_payload is not None:
        return message.provider_payload
    blocks: list[dict[str, Any]] = []
    if message.content:
        blocks.append({"type": "text", "text": message.content})
    blocks.extend({"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments} for call in message.tool_calls)
    return blocks


def anthropic_completion(final: Any, started: float, first_token_at: float | None) -> Completion:
    text = "".join(block.text for block in final.content if block.type == "text")
    tool_calls = [ToolCall(id=block.id, name=block.name, arguments=dict(block.input)) for block in final.content if block.type == "tool_use"]
    payload = [block.model_dump(mode="json", exclude_none=True) for block in final.content]
    message = Message(role=Role.ASSISTANT, content=text, tool_calls=tool_calls, provider_payload=payload)
    stats = GenerationStats(
        model=final.model,
        prompt_tokens=final.usage.input_tokens,
        output_tokens=final.usage.output_tokens,
        time_to_first_token_seconds=(first_token_at - started) if first_token_at is not None else None,
        total_seconds=time.perf_counter() - started,
        stop_reason=final.stop_reason,
    )
    return Completion(message=message, stats=stats)
