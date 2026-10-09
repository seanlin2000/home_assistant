"""The model client for llama-server, over plain HTTP (design_docs/v2/04_agent_harness.md section 3.6).

Every response request is pinned to slot 0 and every quiet request (the router, later the summaries) to slot 1, so a quiet request never pushes the
conversation out of the KV cache (design_docs/v2/02_inference_engine.md section 3.4). The last streamed chunk carries llama-server's `timings`, which
say how many prompt tokens were read fresh and how many came from the cache; they go into the request's GenerationStats.
"""

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from assistant_core.models import CLASSIFY_MAX_TOKENS, AgentPolicy, Completion, GenerationStats, LLMEvent, MalformedToolCall, Message, Role, TextDelta, ToolCall, ToolCallRequest, ToolSpec

CONVERSATION_SLOT = 0
QUIET_SLOT = 1
WARM_UP_USER_TEXT = "Hello."
REQUEST_TIMEOUT_SECONDS = 300.0
STREAM_DATA_PREFIX = "data: "
STREAM_END = "[DONE]"
MILLISECONDS_PER_SECOND = 1000


class LlamaServerClient:
    def __init__(self, base_url: str, api_key: str, model_alias: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model_alias = model_alias
        self._headers = {"Authorization": f"Bearer {api_key}"}

    @property
    def model_name(self) -> str:
        return self._model_alias

    async def chat(self, messages: list[Message], tools: list[ToolSpec], policy: AgentPolicy) -> AsyncIterator[LLMEvent]:
        body = response_request_body(messages, tools, policy)
        stream = StreamedReply()
        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=self._headers) as client:
            async with client.stream("POST", f"{self._base_url}/v1/chat/completions", json=body) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    chunk = parse_stream_line(line)
                    if chunk is None:
                        continue
                    for text in stream.absorb(chunk, started):
                        yield TextDelta(text=text)
        for event in stream.tool_call_events():
            yield event
        yield Completion(message=stream.assistant_message(), stats=stream.stats(self._model_alias, started))

    async def classify(self, system_prompt: str, user_text: str, schema: dict[str, Any], policy: AgentPolicy) -> dict[str, Any]:
        body = {
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_text}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "reply", "schema": schema}},
            "temperature": 0,
            "max_tokens": CLASSIFY_MAX_TOKENS,
            "id_slot": QUIET_SLOT,
            "cache_prompt": True,
        }
        reply = await self._post("/v1/chat/completions", body)
        return json.loads(reply["choices"][0]["message"]["content"])

    async def warm_up(self, conversation_system_prompt: str, tools: list[ToolSpec], quiet_system_prompt: str) -> None:
        """Read each slot's stable prompt once, so the first question after a restart reads only its own tokens (design doc 02 section 3.4)."""
        conversation_body = {
            "messages": [{"role": "system", "content": conversation_system_prompt}, {"role": "user", "content": WARM_UP_USER_TEXT}],
            "tools": [to_openai_tool(tool) for tool in tools] or None,
            "max_tokens": 1,
            "id_slot": CONVERSATION_SLOT,
            "cache_prompt": True,
        }
        quiet_body = {"messages": [{"role": "system", "content": quiet_system_prompt}, {"role": "user", "content": WARM_UP_USER_TEXT}], "max_tokens": 1, "id_slot": QUIET_SLOT, "cache_prompt": True}
        await self._post("/v1/chat/completions", conversation_body)
        await self._post("/v1/chat/completions", quiet_body)

    async def is_ready(self) -> bool:
        """True once llama-server has loaded the model; /health answers 503 while it loads."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._base_url}/health")
        except httpx.HTTPError:
            return False
        return response.status_code == httpx.codes.OK

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=self._headers) as client:
            response = await client.post(f"{self._base_url}{path}", json=body)
        response.raise_for_status()
        return response.json()


def response_request_body(messages: list[Message], tools: list[ToolSpec], policy: AgentPolicy) -> dict[str, Any]:
    return {
        "messages": [to_openai_message(message) for message in messages],
        "tools": [to_openai_tool(tool) for tool in tools] or None,
        "temperature": policy.temperature,
        "max_tokens": policy.max_output_tokens,
        "stream": True,
        "id_slot": CONVERSATION_SLOT,
        "cache_prompt": True,
    }


def parse_stream_line(line: str) -> dict[str, Any] | None:
    if not line.startswith(STREAM_DATA_PREFIX):
        return None
    payload = line[len(STREAM_DATA_PREFIX) :].strip()
    if payload == STREAM_END:
        return None
    return json.loads(payload)


class StreamedReply:
    """Collects one streamed completion: the text as it arrives, the tool-call fragments by index, and the closing timings."""

    def __init__(self) -> None:
        self.text_parts: list[str] = []
        self.tool_fragments: dict[int, dict[str, str]] = {}
        self.finish_reason: str | None = None
        self.timings: dict[str, Any] = {}
        self.first_token_at: float | None = None

    def absorb(self, chunk: dict[str, Any], started: float) -> list[str]:
        """Take in one chunk and return the text it adds, in order."""
        self.timings = chunk.get("timings") or self.timings
        texts: list[str] = []
        for choice in chunk.get("choices", []):
            self.finish_reason = choice.get("finish_reason") or self.finish_reason
            delta = choice.get("delta") or {}
            if (delta.get("content") or delta.get("tool_calls")) and self.first_token_at is None:
                self.first_token_at = time.perf_counter() - started
            if delta.get("content"):
                self.text_parts.append(delta["content"])
                texts.append(delta["content"])
            for fragment in delta.get("tool_calls") or []:
                self.add_tool_fragment(fragment)
        return texts

    def add_tool_fragment(self, fragment: dict[str, Any]) -> None:
        collected = self.tool_fragments.setdefault(fragment.get("index", 0), {"id": "", "name": "", "arguments": ""})
        function = fragment.get("function") or {}
        collected["id"] = fragment.get("id") or collected["id"]
        collected["name"] += function.get("name") or ""
        collected["arguments"] += function.get("arguments") or ""

    def tool_call_events(self) -> list[ToolCallRequest | MalformedToolCall]:
        return [to_tool_call_event(index, fragment) for index, fragment in sorted(self.tool_fragments.items())]

    def assistant_message(self) -> Message:
        calls = [event.call for event in self.tool_call_events() if isinstance(event, ToolCallRequest)]
        return Message(role=Role.ASSISTANT, content="".join(self.text_parts), tool_calls=calls)

    def stats(self, model: str, started: float) -> GenerationStats:
        fresh = self.timings.get("prompt_n")
        cached = self.timings.get("cache_n")
        return GenerationStats(
            model=model,
            prompt_tokens=(fresh or 0) + (cached or 0) if fresh is not None or cached is not None else None,
            fresh_prompt_tokens=fresh,
            cached_prompt_tokens=cached,
            output_tokens=self.timings.get("predicted_n"),
            time_to_first_token_seconds=self.first_token_at,
            total_seconds=time.perf_counter() - started,
            prompt_eval_seconds=milliseconds_to_seconds(self.timings.get("prompt_ms")),
            generation_seconds=milliseconds_to_seconds(self.timings.get("predicted_ms")),
            stop_reason=self.finish_reason,
            slot=CONVERSATION_SLOT,
        )


def to_tool_call_event(index: int, fragment: dict[str, str]) -> ToolCallRequest | MalformedToolCall:
    """A call whose arguments are not a JSON object is reported as malformed, so the loop keeps it out of the history."""
    try:
        arguments = json.loads(fragment["arguments"] or "{}")
    except json.JSONDecodeError:
        return MalformedToolCall(raw=f"{fragment['name']}({fragment['arguments']})")
    if not fragment["name"] or not isinstance(arguments, dict):
        return MalformedToolCall(raw=f"{fragment['name']}({fragment['arguments']})")
    return ToolCallRequest(call=ToolCall(id=fragment["id"] or f"call_{index}", name=fragment["name"], arguments=arguments))


def to_openai_message(message: Message) -> dict[str, Any]:
    if message.role == Role.TOOL:
        return {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
    converted: dict[str, Any] = {"role": message.role.value, "content": message.content}
    if message.tool_calls:
        converted["tool_calls"] = [{"id": call.id, "type": "function", "function": {"name": call.name, "arguments": json.dumps(call.arguments)}} for call in message.tool_calls]
    return converted


def to_openai_tool(tool: ToolSpec) -> dict[str, Any]:
    return {"type": "function", "function": {"name": tool.name, "description": tool.description, "parameters": tool.input_schema}}


def milliseconds_to_seconds(value: float | None) -> float | None:
    return None if value is None else value / MILLISECONDS_PER_SECOND
