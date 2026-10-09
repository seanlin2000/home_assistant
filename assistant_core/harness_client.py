"""The client side of the harness's HTTP API, shared by the Home Assistant component and the benchmark's pass through the service."""

from collections.abc import AsyncIterator

import httpx

from assistant_core.converse_protocol import CONVERSE_PATH, HEALTH_PATH, ConverseRequest, HarnessHealth, line_to_event
from assistant_core.models import AgentEvent

DEFAULT_TIMEOUT_SECONDS = 300.0


class HarnessClient:
    def __init__(self, base_url: str, api_key: str, client: httpx.AsyncClient | None = None, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client
        self._timeout = timeout_seconds

    async def converse(self, request: ConverseRequest) -> AsyncIterator[AgentEvent]:
        """Stream one question's events as the harness produces them; raises httpx.HTTPError when the harness cannot be reached or refuses."""
        client = self._client or httpx.AsyncClient()
        try:
            async with client.stream(
                "POST", f"{self._base_url}{CONVERSE_PATH}", content=request.model_dump_json(), headers={**self._headers, "content-type": "application/json"}, timeout=self._timeout
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.strip():
                        yield line_to_event(line)
        finally:
            if self._client is None:
                await client.aclose()

    async def health(self) -> HarnessHealth:
        client = self._client or httpx.AsyncClient()
        try:
            response = await client.get(f"{self._base_url}{HEALTH_PATH}", headers=self._headers, timeout=10.0)
            response.raise_for_status()
            return HarnessHealth.model_validate(response.json())
        finally:
            if self._client is None:
                await client.aclose()
