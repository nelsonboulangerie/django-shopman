"""Reação derivada roda UMA vez, depois da resposta (``request_memo.run_at_request_end``).

Medido no seed (10/10/2026): fechar uma venda do PDV com três itens com estoque
observava a falta de cada SKU três vezes (reserva, confirmação, baixa, cada uma em
sua transação), publicava o mesmo aviso SSE a cada transição do pedido e religava
pedido e fornada a cada transição. 1.100 consultas; o operador esperava todas.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.http import HttpResponse, StreamingHttpResponse

from shopman.shop.request_memo import (
    RequestMemoMiddleware,
    memoized,
    request_memo_scope,
    run_at_request_end,
)

# O ``close()`` da resposta dispara ``request_finished``, que devolve a conexão.
pytestmark = pytest.mark.django_db


class _Request:
    method = "POST"


def test_fora_de_request_roda_na_hora():
    ran: list[str] = []

    run_at_request_end("k", lambda: ran.append("agora"))

    assert ran == ["agora"]


def test_no_request_a_mesma_chave_roda_uma_vez_e_so_depois_da_resposta():
    ran: list[str] = []

    def view(_request):
        run_at_request_end(("observe", "PCHOC"), lambda: ran.append("1"))
        run_at_request_end(("observe", "MDLN"), lambda: ran.append("mdln"))
        run_at_request_end(("observe", "PCHOC"), lambda: ran.append("3"))
        assert ran == []
        return HttpResponse("ok")

    response = RequestMemoMiddleware(view)(_Request())

    # A resposta já saiu da view e nada rodou: quem chama o close() é o servidor,
    # depois de entregar o corpo.
    assert ran == []
    response.close()
    assert ran == ["mdln", "3"]


def test_uma_reacao_que_falha_nao_impede_as_outras():
    ran: list[str] = []

    def boom():
        raise RuntimeError("falhou")

    def view(_request):
        run_at_request_end("a", boom)
        run_at_request_end("b", lambda: ran.append("b"))
        return HttpResponse("ok")

    with patch("shopman.shop.request_memo.logger") as logger:
        RequestMemoMiddleware(view)(_Request()).close()

    assert ran == ["b"]
    assert "request_end_failed" in logger.exception.call_args.args[0]


def test_resposta_em_streaming_nao_espera_o_fim_do_stream():
    ran: list[str] = []

    def view(_request):
        run_at_request_end("k", lambda: ran.append("sse"))
        return StreamingHttpResponse(iter(["evento"]))

    RequestMemoMiddleware(view)(_Request())

    assert ran == ["sse"]


def test_a_reacao_tem_memo_proprio():
    seen: list[bool] = []

    def view(_request):
        with request_memo_scope():
            pass
        run_at_request_end("k", lambda: seen.append(memoized("x", lambda: True)))
        return HttpResponse("ok")

    RequestMemoMiddleware(view)(_Request()).close()

    assert seen == [True]
