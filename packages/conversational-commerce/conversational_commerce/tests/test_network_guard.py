"""A trava de rede do conftest vale: sem ela, "a suíte roda sem rede" seria promessa."""

from __future__ import annotations

import socket

import pytest


def test_creating_a_socket_is_blocked():
    with pytest.raises(RuntimeError, match="sem rede"):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def test_connecting_by_name_is_blocked():
    with pytest.raises(RuntimeError, match="sem rede"):
        socket.create_connection(("example.invalid", 443), timeout=1)


def test_resolving_a_name_is_blocked():
    with pytest.raises(RuntimeError, match="sem rede"):
        socket.getaddrinfo("example.invalid", 443)
