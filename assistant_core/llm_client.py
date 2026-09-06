"""Model clients behind one streaming interface. OllamaClient serves every local candidate; AnthropicClient serves the frontier baseline."""

import json
import time
from collections.abc import AsyncIterator
from typing import Any, Protocol

import anthropic
import ollama

from assistant_core.models import AgentPolicy, Completion, GenerationStats, LLMEvent, MalformedToolCall, Message, Role, TextDelta, ToolCall, ToolCallRequest, ToolSpec

NANOSECONDS_PER_SECOND = 1_000_000_000
ANTHROPIC_FALLBACK_BETA = "server-side-fallback-2026-06-01"
ANTHROPIC_FALLBACK_MODELS = [{"model": "claude-opus-4-8"}]


class LLMClient(Protocol):
    @property
    def model_name(self) -> str: ...

    def chat(self, messages: list[Message], tools: list[ToolSpec], policy: AgentPolicy) -> AsyncIterator[LLMEvent]: ...


class OllamaClient:
    def __init__(self, model: str, host: str = "http://127.0.0.1:11434", keep_alive: str = "10m") -> None:
        self._model = model
        self._client = ollama.AsyncClient(host=host)
        self._keep_alive = keep_alive

    @property
    def model_name(self) -> str:
        return self._model

    async def chat(self, messages: list[Message], tools: list[ToolSpec], policy: AgentPolicy) -> AsyncIterator[LLMEvent]:
        started = time.perf_counter()
        first_token_at: float | None = None
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        last_chunk: ollama.ChatResponse | None = None
        async for chunk in await self._stream(messages, tools, policy):
            last_chunk = chunk
            if first_token_at is None and (chunk.message.content or chunk.message.tool_calls):
                first_token_at = time.perf_counter()
            if chunk.message.content:
                text_parts.append(chunk.message.content)
                yield TextDelta(text=chunk.message.content)
            for raw_call in chunk.message.tool_calls or []:
                call = to_tool_call(raw_call, len(tool_calls))
                tool_calls.append(call)
                yield ToolCallRequest(call=call)
        content = "".join(text_parts)
        stats = ollama_stats(self._model, last_chunk, started, first_token_at)
        yield Completion(message=Message(role=Role.ASSISTANT, content=content, tool_calls=tool_calls), stats=stats)

    async def _stream(self, messages: list[Message], tools: list[ToolSpec], policy: AgentPolicy) -> AsyncIterator[ollama.ChatResponse]:
        request: dict[str, Any] = {
            "model": self._model,
            "messages": [to_ollama_message(message) for message in messages],
            "tools": [to_ollama_tool(tool) for tool in tools] or None,
            "stream": True,
            "keep_alive": self._keep_alive,
            "options": {"temperature": policy.temperature, "num_ctx": policy.context_tokens, "num_predict": policy.max_output_tokens},
        }
        if policy.think is not None:
            request["think"] = policy.think
        try:
            return await self._client.chat(**request)
        except ollama.ResponseError as error:
            if "think" not in str(error).lower() or "think" not in request:
                raise
            # Some model families reject the thinking switch outright; they have no thinking mode to turn off.
            del request["think"]
            return await self._client.chat(**request)


def to_ollama_message(message: Message) -> dict[str, Any]:
    if message.role == Role.TOOL:
        return {"role": "tool", "content": message.content, "tool_name": message.tool_name}
    converted: dict[str, Any] = {"role": message.role.value, "content": message.content}
    if message.tool_calls:
        converted["tool_calls"] = [{"function": {"name": call.name, "arguments": call.arguments}} for call in message.tool_calls]
    return converted


def to_ollama_tool(tool: ToolSpec) -> dict[str, Any]:
    return {"type": "function", "function": {"name": tool.name, "description": tool.description, "parameters": tool.input_schema}}


def to_tool_call(raw_call: ollama.Message.ToolCall, index: int) -> ToolCall:
    arguments = raw_call.function.arguments
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    return ToolCall(id=f"call_{index}", name=raw_call.function.name, arguments=dict(arguments or {}))


def ollama_stats(model: str, last_chunk: ollama.ChatResponse | None, started: float, first_token_at: float | None) -> GenerationStats:
    total_seconds = time.perf_counter() - started
    time_to_first_token = (first_token_at - started) if first_token_at is not None else None
    if last_chunk is None:
        return GenerationStats(model=model, total_seconds=total_seconds, time_to_first_token_seconds=time_to_first_token)
    return GenerationStats(
        model=model,
        prompt_tokens=last_chunk.prompt_eval_count,
        output_tokens=last_chunk.eval_count,
        time_to_first_token_seconds=time_to_first_token,
        total_seconds=total_seconds,
        prompt_eval_seconds=nanoseconds_to_seconds(last_chunk.prompt_eval_duration),
        generation_seconds=nanoseconds_to_seconds(last_chunk.eval_duration),
        load_seconds=nanoseconds_to_seconds(last_chunk.load_duration),
        stop_reason=last_chunk.done_reason,
    )


def nanoseconds_to_seconds(value: int | None) -> float | None:
    return None if value is None else value / NANOSECONDS_PER_SECOND


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
