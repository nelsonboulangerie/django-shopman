"""Prazo de pagamento vencido: acompanhamento e pagamento contam a MESMA história.

Regressão do ping-pong: `_payment_info` (tracking) ignorava `expires_at` e
mantinha `payment_pending`, oferecendo "Pagar agora"; a tela de pagamento via o
mesmo prazo como vencido, não achava ação pendente e devolvia o cliente para o
acompanhamento. Clicar levava de volta ao ponto de partida, com as duas telas
dizendo coisas opostas.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from shopman.shop.services import payment_status
from shopman.shop.projections.order_tracking import _payment_info

pytestmark = pytest.mark.django_db


def _com_prazo(order, *, expires_in_minutes: int):
    """Usa a fixture ``order`` do conftest (mesmo padrão dos testes da projection)."""
    from shopman.orderman.models import Order as _Order

    quando = timezone.now() + timedelta(minutes=expires_in_minutes)
    data = dict(order.data or {})
    data["payment"] = {
        "method": "pix",
        "intent_ref": "PIX-1",
        "status": "pending",
        "expires_at": quando.isoformat(),
    }
    _Order.objects.filter(pk=order.pk).update(status="confirmed", data=data)
    order.refresh_from_db()
    return order


def test_prazo_vencido_nao_conta_como_pagamento_pendente(order):
    order = _com_prazo(order, expires_in_minutes=-1)

    pending, confirmed, key, _ = _payment_info(order)

    assert pending is False, "PIX morto não pode virar CTA de pagar"
    assert confirmed is False
    assert key == "payment_expired"


def test_dentro_do_prazo_continua_pendente(order):
    order = _com_prazo(order, expires_in_minutes=5)

    pending, _, key, _ = _payment_info(order)

    assert pending is True
    assert key == "payment_pending"


def test_as_duas_telas_concordam_sobre_a_expiracao(order):
    """A regra da expiração tem uma fonte só — não duas que podem divergir."""
    vencido = _com_prazo(order, expires_in_minutes=-1)
    assert payment_status.payment_deadline_passed(vencido) is True
    assert _payment_info(vencido)[2] == "payment_expired"


def test_dentro_do_prazo_as_duas_concordam_que_esta_vivo(order):
    vivo = _com_prazo(order, expires_in_minutes=5)
    assert payment_status.payment_deadline_passed(vivo) is False
    assert _payment_info(vivo)[0] is True
