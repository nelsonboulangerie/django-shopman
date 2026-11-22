"""Comanda com promoção de VALOR FIXO: a revisão e o fechamento cobram o total do motor.

Issue #3244. O motor rateia o desconto fixo de pedido (promoção ou cupom de valor
fixo) entre as linhas: cada uma fica com ``unit_price_q`` já abatido da sua fatia
e ``meta._disc`` com ``scope="order"``. A revisão do PDV soma o ``unit_price_q``
das linhas e só subtrai à parte o desconto MANUAL de pedido, então a fatia do
fixo automático tem de chegar dentro do preço da linha, como o motor a cobra.
Se a revisão devolvesse a etiqueta, a tela prometeria a etiqueta e o selo do
fechamento recusaria com "O total mudou" (ou o cliente pagaria a etiqueta).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from shopman.backstage.projections.pos import build_open_tab
from shopman.backstage.tests.test_pos_pagamento_uma_ida import balcao  # noqa: F401
from shopman.shop.models import Promotion
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import POS_SALE_INTENT_VERSION

pytestmark = pytest.mark.django_db

ETIQUETA_Q = 1000  # P00 na listagem do PDV
FIXO_Q = 300


def _promo_fixa():
    now = timezone.now()
    Promotion.objects.create(
        ref="fixo-de-pedido", name="Três reais", type=Promotion.FIXED, value=FIXO_Q, is_active=True,
        valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1),
    )


def _body(session, *, linhas, shift=None, request_id: str, expected_total_q: int | None = None) -> dict:
    body = {
        "intent_version": POS_SALE_INTENT_VERSION,
        "tab_ref": "77",
        "tab_session_key": session.session_key,
        "expected_revision": build_open_tab(session)["revision"],
        "items": [
            {"line_id": f"L{i:02d}", "sku": f"P{i:02d}", "name": f"Produto {i}", "qty": qty}
            for i, qty in enumerate(linhas)
        ],
        "fulfillment_type": "pickup",
        "payment_method": "cash",
        "payment_collection": "terminal",
        "client_request_id": request_id,
    }
    if shift is not None:
        body["cash_shift_id"] = shift.pk
    if expected_total_q is not None:
        body["expected_total_q"] = expected_total_q
        body["tendered_q"] = expected_total_q
    return body


def _saved_tab(balcao, *, linhas):  # noqa: F811
    from shopman.orderman.models import Session

    session = balcao["session"]
    pos_service.save_pos_tab(
        channel_ref="pdv", payload=_body(session, linhas=linhas, request_id="salvar"),
        actor="test", operator_username="marina",
    )
    return Session.objects.get(pk=session.pk)


# Etiqueta do PDV: P00 = R$ 10,00, P01 = R$ 10,01 (fixture ``balcao``).
@pytest.mark.parametrize(
    ("linhas", "etiqueta_q"),
    [((1,), 1000), ((3,), 3000), ((2, 1), 3001)],
    ids=["uma-unidade", "tres-unidades", "duas-linhas-rateadas"],
)
def test_comanda_com_fixo_de_pedido_revisa_e_fecha_pelo_total_do_motor(balcao, linhas, etiqueta_q):  # noqa: F811
    from shopman.orderman.models import Order

    _promo_fixa()
    session = _saved_tab(balcao, linhas=linhas)
    # Pré-condição: a comanda gravada carrega a fatia do fixo de pedido.
    assert all((line.get("meta") or {}).get("_disc", {}).get("scope") == "order" for line in session.items)
    total_do_motor_q = etiqueta_q - FIXO_Q
    assert sum(int(line["line_total_q"]) for line in session.items) == total_do_motor_q

    review = pos_service.review_sale(
        channel_ref="pdv", payload=_body(session, linhas=linhas, request_id="rev"), operator_username="marina",
    )
    assert review.total_q == total_do_motor_q

    result = pos_service.close_sale(
        channel_ref="pdv",
        payload=_body(
            session, linhas=linhas, shift=balcao["shift"], request_id="fechar", expected_total_q=review.total_q,
        ),
        actor="test",
        operator_username="marina",
    )

    assert result.order_ref
    assert Order.objects.get(ref=result.order_ref).total_q == total_do_motor_q
