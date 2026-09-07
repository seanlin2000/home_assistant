"""A small client for Home Assistant's REST and websocket APIs, shared by the setup script, the deploy, the health check, and the smoke test.

Home Assistant exposes some things only over REST (services, conversation) and others only over the websocket (long-lived tokens, pipelines,
registries, the Supervisor proxy). Every call here is one-shot: a fresh websocket per command, so callers need no connection management.
"""

import asyncio
import json
import time
from typing import Any

import httpx
import websockets

DEFAULT_PORT_CANDIDATES = ("8123", "")


def discover_base(host: str) -> str:
    """Home Assistant OS 18 serves the API on port 80 and, during onboarding, answers port 8123 with a redirect; older installs serve 8123 directly.
    Any HTTP answer below 500 counts as a live server: /api/ gives 401 without a token, and /api/onboarding turns into a 404 once onboarding is done."""
    for candidate in (f"http://{host}:8123", f"http://{host}"):
        try:
            response = httpx.get(f"{candidate}/api/", timeout=10, follow_redirects=False)
        except httpx.HTTPError:
            continue
        if response.is_redirect and response.headers.get("location"):
            target = httpx.URL(response.headers["location"])
            return f"{target.scheme}://{target.host}" + (f":{target.port}" if target.port else "")
        if response.status_code < 500:
            return candidate
    return f"http://{host}:8123"


class HomeAssistant:
    def __init__(self, host: str, token: str | None = None, base: str | None = None) -> None:
        self.host = host
        self.base = base or discover_base(host)
        self.token = token
        self.http = httpx.AsyncClient(base_url=self.base, timeout=60)
        self._ws_id = 0

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def get(self, path: str) -> Any:
        response = await self.http.get(path, headers=self.headers())
        response.raise_for_status()
        return response.json() if response.content else None

    async def post(self, path: str, payload: Any = None, ok_statuses: tuple[int, ...] = (200, 201)) -> Any:
        response = await self.http.post(path, json=payload, headers=self.headers())
        if response.status_code not in ok_statuses:
            raise RuntimeError(f"POST {path} -> {response.status_code} {response.text[:300]}")
        return response.json() if response.content else None

    async def supervisor(self, method: str, endpoint: str, data: dict[str, Any] | None = None) -> Any:
        """Supervisor calls go over the websocket `supervisor/api` command, as the frontend does. On Home Assistant 2026.9 the REST proxy at
        /api/hassio answered 401 to a valid owner token; the websocket route accepted the same token."""
        message: dict[str, Any] = {"type": "supervisor/api", "endpoint": endpoint, "method": method}
        if data is not None:
            message["data"] = data
        return await self.ws(message)

    async def ws(self, message: dict[str, Any]) -> Any:
        """One websocket command with authentication; the websocket API exposes things REST does not (tokens, pipelines, registries)."""
        async with websockets.connect(self.base.replace("http://", "ws://", 1) + "/api/websocket", max_size=None) as socket:
            await socket.recv()
            await socket.send(json.dumps({"type": "auth", "access_token": self.token}))
            auth = json.loads(await socket.recv())
            if auth.get("type") != "auth_ok":
                raise RuntimeError(f"websocket auth failed: {auth}")
            self._ws_id += 1
            await socket.send(json.dumps({"id": self._ws_id, **message}))
            while True:
                reply = json.loads(await socket.recv())
                if reply.get("id") == self._ws_id:
                    if not reply.get("success", True):
                        raise RuntimeError(f"{message['type']} failed: {reply.get('error')}")
                    return reply.get("result")

    async def close(self) -> None:
        await self.http.aclose()


async def wait_for_api(ha: HomeAssistant, timeout_seconds: int = 900, ok_statuses: tuple[int, ...] = (200, 401), poll_seconds: float = 10) -> None:
    """Block until /api/ answers. Without a token Home Assistant answers 401, which still proves it is up; a deploy that must see the
    authenticated 200 passes ok_statuses=(200,)."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = await ha.http.get("/api/", headers=ha.headers())
            if response.status_code in ok_statuses:
                return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(poll_seconds)
    raise TimeoutError(f"Home Assistant did not answer at {ha.base} within {timeout_seconds}s")


def entity_id(registry: list[dict[str, Any]], domain: str, platform: str, needle: str) -> str:
    """The first entity of a domain owned by a platform whose registry entry mentions the needle, e.g. the Wyoming stt entity for whisper."""
    matches = [entry["entity_id"] for entry in registry if entry["entity_id"].startswith(f"{domain}.") and entry["platform"] == platform and needle in json.dumps(entry).lower()]
    if not matches:
        raise LookupError(f"no {domain} entity for platform {platform} matching {needle!r}; entities: {[e['entity_id'] for e in registry if e['entity_id'].startswith(domain)]}")
    return matches[0]


async def conversation_entity_id(ha: HomeAssistant) -> str:
    registry = await ha.ws({"type": "config/entity_registry/list"})
    return entity_id(registry, "conversation", "studio_assistant", "")


async def converse(ha: HomeAssistant, text: str, agent_id: str, timeout_seconds: float = 120, conversation_id: str | None = None) -> str:
    """Ask the assistant one question through the same REST call the Assist pipeline makes, and return what it would have spoken."""
    payload: dict[str, Any] = {"text": text, "language": "en", "agent_id": agent_id}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    response = await ha.http.post("/api/conversation/process", json=payload, headers=ha.headers(), timeout=timeout_seconds)
    response.raise_for_status()
    return response.json()["response"]["speech"]["plain"]["speech"]
