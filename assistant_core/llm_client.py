"""Model clients behind one streaming interface. OllamaClient serves every local candidate and the product; the frontier baseline client lives in anthropic_client.py so production code never imports the anthropic package."""

import json
import time
from collections.abc import AsyncIterator
from typing import Any, Protocol

import ollama

from assistant_core.models import AgentPolicy, Completion, GenerationStats, LLMEvent, Message, Role, TextDelta, ToolCall, ToolCallRequest, ToolSpec

NANOSECONDS_PER_SECOND = 1_000_000_000


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
        thinking_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        last_chunk: ollama.ChatResponse | None = None
        async for chunk in await self._stream(messages, tools, policy):
            last_chunk = chunk
            if first_token_at is None and (chunk.message.content or chunk.message.tool_calls):
                first_token_at = time.perf_counter()
            if chunk.message.thinking:
                thinking_parts.append(chunk.message.thinking)
            if chunk.message.content:
                text_parts.append(chunk.message.content)
                yield TextDelta(text=chunk.message.content)
            for raw_call in chunk.message.tool_calls or []:
                call = to_tool_call(raw_call, len(tool_calls))
                tool_calls.append(call)
                yield ToolCallRequest(call=call)
        content = "".join(text_parts)
        stats = ollama_stats(self._model, last_chunk, started, first_token_at)
        yield Completion(message=Message(role=Role.ASSISTANT, content=content, thinking="".join(thinking_parts), tool_calls=tool_calls), stats=stats)

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
