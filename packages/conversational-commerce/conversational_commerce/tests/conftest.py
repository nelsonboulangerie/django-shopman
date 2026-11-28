"""Trava de rede da suíte: nenhum teste do pacote abre conexão.

"Sem rede" é prova mecânica, não promessa (plano do framework, decisão 10):
toda criação de socket e toda resolução de nome levantam ``NetworkBlocked``.
Um teste que precise de rede está errado; o que fala com o mundo é o
adaptador, e é ele quem prova isso no mecanismo dele.
"""

from __future__ import annotations

import socket

import pytest


class NetworkBlocked(RuntimeError):
    """Um teste do pacote tentou sair para a rede."""


def _blocked_socket(*args, **kwargs):
    raise NetworkBlocked("a suíte do conversational_commerce roda sem rede: socket.socket bloqueado")


def _blocked_getaddrinfo(*args, **kwargs):
    raise NetworkBlocked("a suíte do conversational_commerce roda sem rede: socket.getaddrinfo bloqueado")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr(socket, "socket", _blocked_socket)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked_getaddrinfo)
