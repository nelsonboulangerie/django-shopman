"""Canal SSE ``cash`` do PDV — os fatos que outra estação precisa ver sem F5.

Turno aberto/fechado, devolução (pendente e entregue) e o silêncio deliberado
da venda. O pedido de troco tem arquivo próprio (test_pos_change_request.py).

Todo publish é adiado para o COMMIT (ADR-016), e os próprios sinais do cashman
já saem por ``on_commit`` — daí o ``django_capture_on_commit_callbacks`` em
volta de cada mutação: sem ele, nada sai e o assert mentiria nas duas direções.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from shopman.cashman import services as cash
from shopman.cashman.models import Terminal
from shopman.orderman.models import Order

from shopman.shop.models import Channel

pytestmark = pytest.mark.django_db


@pytest.fixture
def operator():
    return get_user_model().objects.create_user(username="marina", password="x", is_staff=True)


@pytest.fixture
def enviados(monkeypatch):
    caixa: list[tuple[str, str, dict, str | None]] = []
    monkeypatch.setattr(
        "shopman.shop.handlers._sse_emitters._publish_backstage",
        lambda kind, event_type, payload, scope: caixa.append((kind, event_type, payload, scope)),
    )
    return caixa


def _cash_events(enviados) -> list[tuple[dict, str | None]]:
    return [(payload, scope) for kind, _, payload, scope in enviados if kind == "cash"]


def test_abrir_o_turno_anuncia_no_canal_de_caixa(operator, enviados, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        shift = cash.open_shift(operator=operator, float_q=10000)

    eventos = _cash_events(enviados)
    assert {"kind": "shift_opened", "ref": str(shift.pk)} in [payload for payload, _ in eventos]
    # O escopo é o terminal: o dia do balcão + totem já nasce endereçável.
    assert (
        {"kind": "shift_opened", "ref": str(shift.pk)},
        Terminal.default().ref,
    ) in eventos


def test_fechar_o_turno_anuncia_no_canal_de_caixa(operator, enviados, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        shift = cash.open_shift(operator=operator, float_q=10000)
    enviados.clear()

    with django_capture_on_commit_callbacks(execute=True):
        cash.close_shift(shift, counted_q=10000, actor=operator)

    payloads = [payload for payload, _ in _cash_events(enviados)]
    assert {"kind": "shift_closed", "ref": str(shift.pk)} in payloads


def test_devolucao_entregue_anuncia_com_o_ref_do_pedido(operator, enviados, django_capture_on_commit_callbacks):
    """A linha ``refund`` no livro é o FATO; a pendência some da lista de todos."""
    with django_capture_on_commit_callbacks(execute=True):
        shift = cash.open_shift(operator=operator, float_q=10000)
    enviados.clear()

    with django_capture_on_commit_callbacks(execute=True):
        cash.record(
            "refund",
            shift=shift,
            operator=operator,
            amount_q=-500,
            order_ref="ORD-SSE-REFUND",
            reason="devolução de venda cancelada",
        )

    payloads = [payload for payload, _ in _cash_events(enviados)]
    assert {"kind": "refund", "ref": "ORD-SSE-REFUND"} in payloads


def test_venda_cancelada_anuncia_devolucao_pendente(enviados, django_capture_on_commit_callbacks):
    """Cancelar não é devolver: no cancel pode NASCER uma pendência de gaveta.

    O evento é sinal, não estado: sai em todo cancel/return, sem conferir se
    havia dinheiro capturado — quem recebe refaz o fetch canônico e a Projection
    (``pending_cash_refunds``) responde a verdade. Cancelamento é raro; um
    refetch em vão é mais barato que duplicar a derivação aqui.
    """
    Channel.objects.create(ref="counter", name="Balcão", is_active=True)
    order = Order.objects.create(
        ref="ORD-SSE-CANCEL", channel_ref="counter", status=Order.Status.NEW, total_q=1000
    )

    with django_capture_on_commit_callbacks(execute=True):
        order.transition_status(Order.Status.CANCELLED, actor="test")

    payloads = [payload for payload, _ in _cash_events(enviados)]
    assert {"kind": "refund_pending", "ref": "ORD-SSE-CANCEL"} in payloads


def test_venda_e_movimento_nao_anunciam_no_canal_de_caixa(operator, enviados, django_capture_on_commit_callbacks):
    """O silêncio é decisão: venda e sangria são fatos da PRÓPRIA estação.

    Empurrar um refetch para o balcão inteiro a cada venda seria o poll de
    volta, só que empurrado — o canal carrega só o que é cross-estação.
    """
    with django_capture_on_commit_callbacks(execute=True):
        shift = cash.open_shift(operator=operator, float_q=10000)
    enviados.clear()

    with django_capture_on_commit_callbacks(execute=True):
        cash.record("sale", shift=shift, operator=operator, amount_q=2500, order_ref="ORD-SSE-SALE")
        cash.record(
            "cash_out",
            shift=shift,
            operator=operator,
            approved_by=operator,
            amount_q=-1000,
            reason="teste",
        )

    assert _cash_events(enviados) == []
