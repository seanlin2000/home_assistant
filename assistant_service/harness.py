"""What the service does for one question, and the housekeeping it does every minute, with no HTTP in sight (design doc v2/04 sections 3.1 and 3.5).

The answer itself is the shared agent loop in assistant_core, the same code the benchmark runs in-process. The harness adds what a long-running
service owns: the tool server connection per question, the conversation's state, the exchange log, and keeping llama-server's slots warm.
"""

import logging
import time
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack

import httpx

from assistant_core import agent_loop
from assistant_core.converse_protocol import ConverseRequest, HarnessHealth
from assistant_core.exchange_record import exchange_record_from_transcript
from assistant_core.llama_server_client import LlamaServerClient
from assistant_core.mcp_http import HttpMcpToolBox, McpProtocolError
from assistant_core.models import AgentEvent, AgentPolicy, AnswerDelta, Done, Message, Transcript
from assistant_core.prompts import system_prompt
from assistant_core.router import ROUTER_SYSTEM_PROMPT
from assistant_core.tools import ToolBox, UnavailableToolBox
from assistant_service.conversation_state import ConversationState
from assistant_service.exchange_log import ExchangeLog

_LOGGER = logging.getLogger(__name__)

MODEL_UNREACHABLE_ANSWER = "I can't reach the model right now."
TOOL_SERVER_ERRORS = (httpx.HTTPError, McpProtocolError)
SECONDS_PER_MINUTE = 60


class Harness:
    def __init__(self, llm: LlamaServerClient, tool_server_url: str, policy: AgentPolicy, state: ConversationState, exchange_log: ExchangeLog, quiet_minutes: float) -> None:
        self._llm = llm
        self._tool_server_url = tool_server_url
        self._policy = policy
        self._state = state
        self._exchange_log = exchange_log
        self._quiet_seconds = quiet_minutes * SECONDS_PER_MINUTE
        self._slots_warm = False

    async def converse(self, request: ConverseRequest) -> AsyncIterator[AgentEvent]:
        """Answer one question, logging the exchange when its transcript arrives."""
        self._state.record_exchange(request.conversation_id)
        async with AsyncExitStack() as stack:
            tools = await self._open_tool_box(stack)
            async for event in self._answer_or_apologise(request.conversation, tools):
                if isinstance(event, Done):
                    self._exchange_log.append(exchange_record_from_transcript(event.transcript, source=request.source))
                yield event

    async def warm_up(self) -> None:
        """Both slots read their stable prompts, so the next question reads only its own tokens (design doc v2/02 section 3.4)."""
        try:
            async with AsyncExitStack() as stack:
                tools = await self._open_tool_box(stack)
                await self._llm.warm_up(system_prompt(), await tools.list_tools(), ROUTER_SYSTEM_PROMPT)
            self._slots_warm = True
        except httpx.HTTPError as error:
            _LOGGER.warning("warm-up failed, retrying in a minute: %s", error)

    async def check_in(self, now: float | None = None) -> None:
        """The once-a-minute housekeeping: warm the slots again after llama-server comes back, and forget conversations Home Assistant has forgotten."""
        await self._rewarm_after_recovery()
        self._forget_quiet_conversations(time.time() if now is None else now)

    async def health(self) -> HarnessHealth:
        llama_server = await self._llm.is_ready()
        tool_server = await self._tool_server_answers()
        return HarnessHealth(status="ok" if llama_server and tool_server else "degraded", llama_server=llama_server, tool_server=tool_server)

    async def _open_tool_box(self, stack: AsyncExitStack) -> ToolBox:
        """The tool server for this question, or no tools when it cannot be reached: the model then answers from knowledge with the loop's caveat."""
        try:
            return await stack.enter_async_context(HttpMcpToolBox(self._tool_server_url, timeout_seconds=self._policy.tool_timeout_seconds))
        except TOOL_SERVER_ERRORS as error:
            _LOGGER.warning("tool server unavailable (%s); answering without it", error)
            return UnavailableToolBox()

    async def _answer_or_apologise(self, conversation: list[Message], tools: ToolBox) -> AsyncIterator[AgentEvent]:
        try:
            async for event in agent_loop.run(conversation, self._llm, tools, self._policy):
                yield event
        except httpx.HTTPError as error:
            _LOGGER.warning("llama-server unavailable: %s", error)
            self._slots_warm = False
            yield AnswerDelta(text=MODEL_UNREACHABLE_ANSWER)
            yield Done(transcript=unanswered_transcript(self._llm.model_name, conversation, str(error)))

    async def _rewarm_after_recovery(self) -> None:
        if not await self._llm.is_ready():
            self._slots_warm = False
            return
        if not self._slots_warm:
            await self.warm_up()

    def _forget_quiet_conversations(self, now: float) -> None:
        for conversation_id in self._state.quiet_since(now - self._quiet_seconds):
            self._state.forget(conversation_id)

    async def _tool_server_answers(self) -> bool:
        health_url = httpx.URL(self._tool_server_url).copy_with(path="/healthz")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(health_url)
        except httpx.HTTPError:
            return False
        return response.status_code == httpx.codes.OK


def unanswered_transcript(model: str, conversation: list[Message], error: str) -> Transcript:
    return Transcript(model=model, system_prompt=system_prompt(), conversation=list(conversation), spoken_text=MODEL_UNREACHABLE_ANSWER, final_answer=MODEL_UNREACHABLE_ANSWER, error=error)
