"""Comanda com promoção automática: a revisão e o fechamento cobram o mesmo total.

Beta de 05/11/2026 (ge:PDV-02). Com uma promoção ativa no Croissant, a comanda
mostrava a linha a R$ 3,00 e o Pagamento dizia R$ 43,00; o fechamento cobrava
R$ 33,00, recusava com ``total_changed``, e a cada Enter a recusa voltava. Só
fechava com um desconto manual, porque só com ele a revisão de comanda perguntava
o preço ao motor. Sem desconto manual, a revisão preenchia a linha sem preço com a
ETIQUETA da sessão, e o fechamento aceitava o preço que a tela declarava.

A regra: na comanda, o preço da linha é SEMPRE o do motor, com ou sem desconto
manual, na revisão e no fechamento.
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


def _promo():
    now = timezone.now()
    Promotion.objects.create(
        ref="beta-pdv-02", name="Dez por cento", type=Promotion.PERCENT, value=10, is_active=True,
        valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1),
    )


def _body(session, *, shift=None, unit_price_q: int | None, request_id: str, expected_total_q: int | None = None) -> dict:
    item = {"line_id": "L00", "sku": "P00", "name": "Produto 0", "qty": 1}
    if unit_price_q is not None:
        item["unit_price_q"] = unit_price_q
    body = {
        "intent_version": POS_SALE_INTENT_VERSION,
        "tab_ref": "77",
        "tab_session_key": session.session_key,
        "expected_revision": build_open_tab(session)["revision"],
        "items": [item],
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


def _saved_tab(balcao):  # noqa: F811
    from shopman.orderman.models import Session

    session = balcao["session"]
    pos_service.save_pos_tab(
        channel_ref="pdv", payload=_body(session, unit_price_q=None, request_id="salvar"),
        actor="test", operator_username="marina",
    )
    return Session.objects.get(pk=session.pk)


@pytest.mark.parametrize("declarado", [None, ETIQUETA_Q])
def test_revisao_da_comanda_cobra_a_promocao_automatica(balcao, declarado):  # noqa: F811
    _promo()
    session = _saved_tab(balcao)

    review = pos_service.review_sale(
        channel_ref="pdv", payload=_body(session, unit_price_q=declarado, request_id="rev"), operator_username="marina",
    )

    assert review.total_q == 900


def test_fechamento_aceita_o_total_que_a_revisao_mostrou(balcao):  # noqa: F811
    _promo()
    session = _saved_tab(balcao)
    review = pos_service.review_sale(
        channel_ref="pdv", payload=_body(session, unit_price_q=None, request_id="rev"), operator_username="marina",
    )

    # A tela declara o preço da linha já em promoção; a revisão não declarou nenhum.
    result = pos_service.close_sale(
        channel_ref="pdv",
        payload=_body(
            session, shift=balcao["shift"], unit_price_q=900, request_id="fechar", expected_total_q=review.total_q,
        ),
        actor="test",
        operator_username="marina",
    )

    assert review.total_q == 900
    assert result.order_ref
