"""Refuse to fetch anything that is not a public web address.

The model chooses which URLs fetch_page reads, and a web page can tell the model which URL to choose. Without this check an injected instruction could
point the tool server at the router, the Home Assistant VM, Ollama's API, or a cloud metadata service. Every hostname is resolved first and every
resolved address must be globally routable; redirects are checked hop by hop by the caller, and the address a connection reached is checked once
more. An address carrying a username or password is refused too: nothing the assistant reads needs a login sent in the URL.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse, urlunparse

import httpx

Resolver = Callable[[str], Awaitable[list[str]]]

ALLOWED_SCHEMES = ("http", "https")
BLOCKED_HOSTNAMES = ("localhost", "localhost.localdomain", "metadata.google.internal")


class UnsafeUrl(ValueError):
    """The URL points somewhere the tool server must not connect to."""


async def system_resolver(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


def is_public_address(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address.split("%")[0])
    except ValueError:
        return False
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped is not None:
        parsed = parsed.ipv4_mapped
    return parsed.is_global and not parsed.is_multicast


async def ensure_public_url(url: str, resolver: Resolver = system_resolver) -> list[str]:
    """Raise UnsafeUrl unless url uses http(s), carries no username or password, and every address its host resolves to is public; return those
    addresses so the caller can connect to one of them instead of resolving the name a second time (a hostile zone can answer the second lookup differently)."""
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrl(f"scheme '{parsed.scheme}' is not allowed")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeUrl("the address carries a username or password")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise UnsafeUrl("no host in url")
    if host in BLOCKED_HOSTNAMES or host.endswith((".local", ".internal", ".localhost", ".lan", ".home", ".arpa")):
        raise UnsafeUrl(f"host '{host}' is not a public name")
    try:
        addresses = [host] if is_ip_literal(host) else await resolver(host)
    except (OSError, ValueError) as error:
        raise UnsafeUrl(f"could not resolve '{host}': {error}") from error
    if not addresses:
        raise UnsafeUrl(f"'{host}' resolved to nothing")
    for address in addresses:
        if not is_public_address(address):
            raise UnsafeUrl(f"'{host}' resolves to non-public address {address}")
    return addresses


def refuse_unless_public_peer(response: httpx.Response) -> None:
    """Raise UnsafeUrl if the socket behind this response reached a non-public address. Injected transports (tests) carry no network stream and pass."""
    stream = response.extensions.get("network_stream")
    peer = stream.get_extra_info("server_addr") if stream is not None else None
    if peer and not is_public_address(str(peer[0])):
        raise UnsafeUrl(f"connection reached non-public address {peer[0]}")


def pin_url_to_address(url: str, address: str) -> str:
    """The same URL with its host replaced by an already-checked address. The original name travels in the Host header and in TLS instead."""
    parsed = urlparse(url)
    host = f"[{address}]" if ":" in address else address
    netloc = f"{host}:{parsed.port}" if parsed.port else host
    return urlunparse(parsed._replace(netloc=netloc))


def host_header(url: str) -> str:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    return f"{hostname}:{parsed.port}" if parsed.port else hostname


def is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True
