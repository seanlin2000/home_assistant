"""The benchmark must never talk to a server it did not start."""

import socket

import pytest

from benchmark.mcp_process import ensure_port_free


def test_ensure_port_free_refuses_a_bound_port(unused_tcp_port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind(("127.0.0.1", unused_tcp_port))
        holder.listen(1)
        with pytest.raises(RuntimeError, match="already in use"):
            ensure_port_free("127.0.0.1", unused_tcp_port)
    ensure_port_free("127.0.0.1", unused_tcp_port)
