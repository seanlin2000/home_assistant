"""The dashboard's HTTP API and page (design doc v2/13). It reads the logs, and its chat box sends questions to the harness. A request must name this
Mac in its Host header, and a request from a web page must come from the dashboard's own page, which stops another site reading the traces or
asking questions through DNS rebinding or a forged form (design doc v2/12 section 3.9)."""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from datetime import date, datetime

import httpx
from pydantic import BaseModel, ValidationError
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from assistant_core.converse_protocol import NDJSON_MEDIA_TYPE, ConverseRequest, event_to_line
from assistant_core.models import AgentEvent
from dashboard.exchange_views import ExchangeStore
from dashboard.generation_speed import local_midnight, local_now, today_speed
from dashboard.memory_reader import MemoryReader
from dashboard.prompt_layout import prompt_layout
from dashboard.settings import STATIC_DIR, LlamaServerAccess
from dashboard.slot_views import slots_view
from utils.http_access_utils import host_named, misdirected

CHAT_SOURCE = "dashboard"  # how the exchange log labels questions typed into the chat box
Converse = Callable[[ConverseRequest], AsyncIterator[AgentEvent]]
Clock = Callable[[], datetime]


def build_app(
    store: ExchangeStore,
    allowed_hosts: list[str],
    converse: Converse | None = None,
    lifespan: Callable[[Starlette], AbstractAsyncContextManager[None]] | None = None,
    clock: Clock = local_now,
    llama_server: LlamaServerAccess | None = None,
    memory: MemoryReader | None = None,
) -> Starlette:
    async def index(_request: Request) -> Response:
        return FileResponse(STATIC_DIR / "index.html")

    async def days(_request: Request) -> Response:
        return JSONResponse([day.model_dump() for day in store.days()])

    async def latest(_request: Request) -> Response:
        newest = store.latest()
        return JSONResponse(newest.model_dump() if newest else None)

    async def today(_request: Request) -> Response:
        since = local_midnight(clock())
        return JSONResponse(today_speed(store.records_since(since), since).model_dump())

    async def exchanges(request: Request) -> Response:
        day = day_in(request)
        return JSONResponse([summary.model_dump() for summary in store.summaries(day)]) if day else not_found()

    async def exchange(request: Request) -> Response:
        day = day_in(request)
        detail = store.detail(day, request.path_params["index"]) if day else None
        return Response(detail.model_dump_json(), media_type="application/json") if detail else not_found()

    async def prompt(request: Request) -> Response:
        day = day_in(request)
        found = store.record_and_trace(day, request.path_params["index"]) if day else None
        if found is None:
            return not_found()
        record, trace = found
        if trace is None:
            return JSONResponse({"error": "this exchange's trace is gone (none was kept, or it is older than 14 days), so its prompt cannot be rebuilt"}, status_code=404)
        if llama_server is None:
            return llama_server_off()
        return await from_llama_server(lambda: prompt_layout(trace, record.model_calls, llama_server.client))

    async def slots(_request: Request) -> Response:
        if llama_server is None:
            return llama_server_off()

        async def current_slots() -> BaseModel:
            return slots_view(await llama_server.client.slots(), llama_server.pool_tokens, llama_server.conversation_tokens)

        return await from_llama_server(current_slots)

    async def memory_now(_request: Request) -> Response:
        if memory is None:
            return JSONResponse({"error": "the memory tab reads macOS's own tools, so it is off on other systems"}, status_code=503)
        try:
            view = await memory.current()
        except (OSError, TimeoutError, ValueError) as error:
            return JSONResponse({"error": f"this Mac's memory could not be read: {type(error).__name__}: {error}"}, status_code=503)
        return Response(view.model_dump_json(), media_type="application/json")

    async def ask(request: Request) -> Response:
        if converse is None:
            return JSONResponse({"error": "the chat box is off: the harness's API key was not found"}, status_code=503)
        try:
            question = ConverseRequest.model_validate_json(await request.body())
        except ValidationError as error:
            return JSONResponse({"error": error.errors(include_url=False, include_context=False)}, status_code=422)
        return StreamingResponse(event_lines(converse(question.model_copy(update={"source": CHAT_SOURCE}))), media_type=NDJSON_MEDIA_TYPE)

    async def refuse_other_hosts(request: Request, call_next: RequestResponseEndpoint) -> Response:
        return await call_next(request) if from_this_dashboard(request, allowed_hosts) else misdirected(request)

    routes = [
        Route("/", index),
        Route("/api/days", days),
        Route("/api/latest", latest),
        Route("/api/today", today),
        Route("/api/ask", ask, methods=["POST"]),
        Route("/api/days/{day}/exchanges", exchanges),
        Route("/api/days/{day}/exchanges/{index:int}", exchange),
        Route("/api/days/{day}/exchanges/{index:int}/prompt", prompt),
        Route("/api/slots", slots),
        Route("/api/memory", memory_now),
        Mount("/static", StaticFiles(directory=STATIC_DIR), name="static"),
    ]
    return Starlette(routes=routes, middleware=[Middleware(BaseHTTPMiddleware, dispatch=refuse_other_hosts)], lifespan=lifespan)


async def event_lines(events: AsyncIterator[AgentEvent]) -> AsyncIterator[str]:
    """The harness's events passed on line by line; a harness that is down or refuses ends the stream with an error line the page shows."""
    try:
        async for event in events:
            yield event_to_line(event) + "\n"
    except Exception as error:  # noqa: BLE001 - the page must hear why its question went unanswered
        yield json.dumps({"event": "error", "message": f"{type(error).__name__}: {error}"}) + "\n"


async def from_llama_server(view: Callable[[], Awaitable[BaseModel]]) -> Response:
    """A view built from llama-server's answers, or why llama-server could not give them (it is down, still loading, or refused the key)."""
    try:
        built = await view()
    except httpx.HTTPError as error:
        return JSONResponse({"error": f"llama-server did not answer: {type(error).__name__}: {error}"}, status_code=503)
    return Response(built.model_dump_json(), media_type="application/json")


def llama_server_off() -> Response:
    return JSONResponse({"error": "llama-server's API key was not found on this Mac, so the dashboard cannot ask it"}, status_code=503)


def from_this_dashboard(request: Request, allowed_hosts: list[str]) -> bool:
    origin = request.headers.get("origin")
    return host_named(request, allowed_hosts) and (origin is None or origin == f"http://{request.headers.get('host', '')}")


def day_in(request: Request) -> date | None:
    try:
        return date.fromisoformat(request.path_params["day"])
    except ValueError:
        return None


def not_found() -> Response:
    return JSONResponse({"error": "no such exchange"}, status_code=404)
