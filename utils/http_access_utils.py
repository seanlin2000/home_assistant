"""Who may call the HTTP services on this Mac: requests must name this machine in their Host header and must not come from a web page, which stops
DNS rebinding (design doc v2/12 section 3.9). The tool server and the harness both apply it."""

import os
import secrets

from starlette.requests import Request
from starlette.responses import JSONResponse, Response


def allowed_hosts_from_environment(variable: str, port: int) -> list[str]:
    """Host header values a service answers to: the comma-separated list scripts/services.sh derives from the Mac's address, or the loopback names."""
    hosts = [entry.strip() for entry in os.environ.get(variable, "").split(",") if entry.strip()]
    return hosts or [f"localhost:{port}", f"127.0.0.1:{port}"]


def host_allowed(request: Request, allowed_hosts: list[str]) -> bool:
    if not allowed_hosts:
        return True
    if request.headers.get("origin"):
        return False
    return host_named(request, allowed_hosts)


def host_named(request: Request, allowed_hosts: list[str]) -> bool:
    if not allowed_hosts:
        return True
    host = request.headers.get("host", "")
    return host in allowed_hosts or any(pattern.endswith(":*") and host.startswith(pattern[:-1]) for pattern in allowed_hosts)


def bearer_key_matches(request: Request, api_key: str) -> bool:
    presented = request.headers.get("authorization", "").removeprefix("Bearer ")
    return secrets.compare_digest(presented.encode(), api_key.encode())


def misdirected(request: Request) -> Response:
    return JSONResponse({"error": f"host {request.headers.get('host', '')!r} is not this server"}, status_code=421)


def unauthorized() -> Response:
    return JSONResponse({"error": "missing or wrong API key"}, status_code=401)
