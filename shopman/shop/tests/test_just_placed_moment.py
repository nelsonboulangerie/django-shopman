"""Momento "acabei de fazer o pedido" — uso único, preso à sessão.

Substitui a tela /confirmado, que foi removida. O checkout marca a sessão; o
primeiro carregamento do acompanhamento consome e celebra. As voltas seguintes
mostram só o acompanhamento, e um link compartilhado nunca mostra a celebração
de outra pessoa (o gatilho não vive na URL).
"""

from __future__ import annotations

from types import SimpleNamespace

from shopman.shop.services.customer_orders import (
    JUST_PLACED_SESSION_KEY,
    consume_just_placed,
    mark_just_placed,
)


class _Session(dict):
    """Dict com o atributo ``modified`` que a SessionBase do Django expõe."""

    modified = False


def _request(session: dict | None = None):
    return SimpleNamespace(session=_Session(session or {}))


def test_marca_e_consome_uma_unica_vez():
    req = _request()
    mark_just_placed(req, "WEB-1")

    assert consume_just_placed(req, "WEB-1") is True, "primeiro acesso celebra"
    assert consume_just_placed(req, "WEB-1") is False, "o refresh não repete"
    assert JUST_PLACED_SESSION_KEY not in req.session


def test_nao_vaza_para_outro_pedido():
    req = _request()
    mark_just_placed(req, "WEB-1")

    assert consume_just_placed(req, "WEB-2") is False
    assert consume_just_placed(req, "WEB-1") is True, "o pedido certo ainda celebra"


def test_sessao_limpa_nao_celebra():
    """Link compartilhado / outro navegador: sem marca, sem celebração."""
    assert consume_just_placed(_request(), "WEB-1") is False


def test_marcar_de_novo_substitui_o_anterior():
    """Dois pedidos seguidos: só o último conta como 'acabei de fazer'."""
    req = _request()
    mark_just_placed(req, "WEB-1")
    mark_just_placed(req, "WEB-2")

    assert consume_just_placed(req, "WEB-1") is False
    assert consume_just_placed(req, "WEB-2") is True


def test_request_sem_sessao_nao_explode():
    """Chamada fora de um request de browser (comando, worker) é no-op."""
    sem_sessao = SimpleNamespace()
    mark_just_placed(sem_sessao, "WEB-1")
    assert consume_just_placed(sem_sessao, "WEB-1") is False


def test_ref_vazia_e_no_op():
    req = _request()
    mark_just_placed(req, "")
    assert dict(req.session) == {}
    assert consume_just_placed(req, "") is False
