"""The dashboard's HTTP API and page (design doc v2/13). Everything is read-only. A request must name this Mac in its Host header, and a request from
a web page must come from the dashboard's own page, which stops another site reading the traces through DNS rebinding (design doc v2/12 section 3.9)."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import date

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from dashboard.exchange_views import ExchangeStore
from dashboard.settings import STATIC_DIR
from utils.http_access_utils import host_named, misdirected


def build_app(store: ExchangeStore, allowed_hosts: list[str], lifespan: Callable[[Starlette], AbstractAsyncContextManager[None]] | None = None) -> Starlette:
    async def index(_request: Request) -> Response:
        return FileResponse(STATIC_DIR / "index.html")

    async def days(_request: Request) -> Response:
        return JSONResponse([day.model_dump() for day in store.days()])

    async def latest(_request: Request) -> Response:
        newest = store.latest()
        return JSONResponse(newest.model_dump() if newest else None)

    async def exchanges(request: Request) -> Response:
        day = day_in(request)
        return JSONResponse([summary.model_dump() for summary in store.summaries(day)]) if day else not_found()

    async def exchange(request: Request) -> Response:
        day = day_in(request)
        detail = store.detail(day, request.path_params["index"]) if day else None
        return Response(detail.model_dump_json(), media_type="application/json") if detail else not_found()

    async def refuse_other_hosts(request: Request, call_next: RequestResponseEndpoint) -> Response:
        return await call_next(request) if from_this_dashboard(request, allowed_hosts) else misdirected(request)

    routes = [
        Route("/", index),
        Route("/api/days", days),
        Route("/api/latest", latest),
        Route("/api/days/{day}/exchanges", exchanges),
        Route("/api/days/{day}/exchanges/{index:int}", exchange),
        Mount("/static", StaticFiles(directory=STATIC_DIR), name="static"),
    ]
    return Starlette(routes=routes, middleware=[Middleware(BaseHTTPMiddleware, dispatch=refuse_other_hosts)], lifespan=lifespan)


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
