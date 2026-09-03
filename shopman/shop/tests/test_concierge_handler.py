"""Handler da diretiva ``concierge.turn``: laço, terminal e transitório."""

from __future__ import annotations

from types import SimpleNamespace

import anthropic
import httpx
import pytest
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError

from shopman.shop.concierge import service
from shopman.shop.handlers import ALL_HANDLERS
from shopman.shop.handlers.concierge import MAX_LOOPS, ConciergeTurnHandler
from shopman.shop.models import Conversation


def _directive(conversation_id=1):
    return SimpleNamespace(payload={"conversation_id": conversation_id})


def test_handler_registrado_com_o_topico_do_service():
    assert ConciergeTurnHandler.topic == service.TURN_TOPIC == "concierge.turn"
    assert "shopman.shop.handlers.concierge.ConciergeTurnHandler" in ALL_HANDLERS


def test_roda_de_novo_enquanto_ha_mensagem_pendente(monkeypatch):
    results = iter([
        service.TurnResult(conversation_id=1, pending_more=True),
        service.TurnResult(conversation_id=1, pending_more=True),
        service.TurnResult(conversation_id=1, pending_more=False),
    ])
    calls: list[int] = []

    def fake_run_turn(conversation_id, *, client=None):
        calls.append(conversation_id)
        return next(results)

    monkeypatch.setattr(service, "run_turn", fake_run_turn)
    ConciergeTurnHandler().handle(message=_directive(1), ctx={})
    assert calls == [1, 1, 1]


def test_laco_tem_teto(monkeypatch):
    calls: list[int] = []

    def sempre_pendente(conversation_id, *, client=None):
        calls.append(conversation_id)
        return service.TurnResult(conversation_id=conversation_id, pending_more=True)

    monkeypatch.setattr(service, "run_turn", sempre_pendente)
    ConciergeTurnHandler().handle(message=_directive(9), ctx={})
    assert len(calls) == MAX_LOOPS


def test_conversa_inexistente_e_terminal(monkeypatch):
    def missing(conversation_id, *, client=None):
        raise Conversation.DoesNotExist()

    monkeypatch.setattr(service, "run_turn", missing)
    with pytest.raises(DirectiveTerminalError):
        ConciergeTurnHandler().handle(message=_directive(404), ctx={})


def test_payload_sem_conversation_id_e_terminal():
    with pytest.raises(DirectiveTerminalError):
        ConciergeTurnHandler().handle(message=SimpleNamespace(payload={}), ctx={})


def test_erro_de_conexao_e_transitorio(monkeypatch):
    def offline(conversation_id, *, client=None):
        raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.test"))

    monkeypatch.setattr(service, "run_turn", offline)
    with pytest.raises(DirectiveTransientError):
        ConciergeTurnHandler().handle(message=_directive(1), ctx={})


def test_rate_limit_e_5xx_sao_transitorios(monkeypatch):
    request = httpx.Request("POST", "https://api.anthropic.test")

    def too_many(conversation_id, *, client=None):
        raise anthropic.RateLimitError("slow down", response=httpx.Response(429, request=request), body=None)

    monkeypatch.setattr(service, "run_turn", too_many)
    with pytest.raises(DirectiveTransientError):
        ConciergeTurnHandler().handle(message=_directive(1), ctx={})

    def upstream_down(conversation_id, *, client=None):
        raise anthropic.InternalServerError("boom", response=httpx.Response(503, request=request), body=None)

    monkeypatch.setattr(service, "run_turn", upstream_down)
    with pytest.raises(DirectiveTransientError):
        ConciergeTurnHandler().handle(message=_directive(1), ctx={})


def test_erro_de_programa_escapa_como_esta(monkeypatch):
    """Bug não é transitório: não pode virar retry infinito com backoff."""
    def bug(conversation_id, *, client=None):
        raise KeyError("quote")

    monkeypatch.setattr(service, "run_turn", bug)
    with pytest.raises(KeyError):
        ConciergeTurnHandler().handle(message=_directive(1), ctx={})
