"""The harness's HTTP API: POST /v1/converse streams one question's events as newline-delimited JSON, GET /health reports the dependencies
(design doc v2/04 section 3.2). It listens on the network so the Home Assistant VM can reach it, so every request must carry the API key, name this
Mac in its Host header, and come from no web page."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from assistant_core.converse_protocol import CONVERSE_PATH, HEALTH_PATH, NDJSON_MEDIA_TYPE, ConverseRequest, event_to_line
from assistant_core.models import AgentEvent
from assistant_service.harness import Harness
from utils.http_access_utils import bearer_key_matches, host_allowed, misdirected, unauthorized


@dataclass
class AccessRules:
    api_key: str
    allowed_hosts: list[str]

    def refusal_for(self, request: Request) -> Response | None:
        if not host_allowed(request, self.allowed_hosts):
            return misdirected(request)
        if not bearer_key_matches(request, self.api_key):
            return unauthorized()
        return None


def build_app(harness: Harness, access: AccessRules, lifespan: Callable[[Starlette], AbstractAsyncContextManager[None]] | None = None) -> Starlette:
    async def converse(request: Request) -> Response:
        refusal = access.refusal_for(request)
        if refusal:
            return refusal
        try:
            converse_request = ConverseRequest.model_validate_json(await request.body())
        except ValidationError as error:
            return JSONResponse({"error": error.errors(include_url=False, include_context=False)}, status_code=422)
        return StreamingResponse(event_lines(harness.converse(converse_request)), media_type=NDJSON_MEDIA_TYPE)

    async def health(request: Request) -> Response:
        refusal = access.refusal_for(request)
        if refusal:
            return refusal
        return JSONResponse((await harness.health()).model_dump())

    routes = [Route(CONVERSE_PATH, converse, methods=["POST"]), Route(HEALTH_PATH, health, methods=["GET"])]
    return Starlette(routes=routes, lifespan=lifespan)


async def event_lines(events: AsyncIterator[AgentEvent]) -> AsyncIterator[str]:
    async for event in events:
        yield event_to_line(event) + "\n"
