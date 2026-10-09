"""Who may call the HTTP services on this Mac: requests must name this machine in their Host header and must not come from a web page, which stops
DNS rebinding (design doc v2/12 section 3.9). The tool server and the harness both apply it."""

import secrets

from starlette.requests import Request
from starlette.responses import JSONResponse, Response


def host_allowed(request: Request, allowed_hosts: list[str]) -> bool:
    if not allowed_hosts:
        return True
    if request.headers.get("origin"):
        return False
    host = request.headers.get("host", "")
    return host in allowed_hosts or any(pattern.endswith(":*") and host.startswith(pattern[:-1]) for pattern in allowed_hosts)


def bearer_key_matches(request: Request, api_key: str) -> bool:
    presented = request.headers.get("authorization", "").removeprefix("Bearer ")
    return secrets.compare_digest(presented.encode(), api_key.encode())


def misdirected(request: Request) -> Response:
    return JSONResponse({"error": f"host {request.headers.get('host', '')!r} is not this server"}, status_code=421)


def unauthorized() -> Response:
    return JSONResponse({"error": "missing or wrong API key"}, status_code=401)
