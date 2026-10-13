"""Venda de balcão SEM comanda precifica pelo mesmo motor da venda com comanda (P0-1).

O defeito, provado em execução (docs/reference/cenarios-de-pedido.md, P0-1): no
Happy Hour (ou na Xepa), a venda direta do PDV era revisada pela soma da vitrine,
R$ 12,00; o fechamento aplicava o desconto no kernel, selava R$ 7,20 e
reescrevia o pagamento calado (``change_q=480``,
``pos_reconciled_from_amount_q=1200``): troco que ninguém deu na gaveta e
maquininha passada acima da nota.

A regra que estes testes fixam: a revisão mostra o total do MOTOR, e o
fechamento que chega com outro total é recusado com ``total_changed``, nunca
reconciliado sem o operador ver.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.core.cache import cache
from shopman.orderman.models import Order, Session

from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import PosIntentError
from shopman.shop.tests.test_pos_cash_ledger import _Counter

pytestmark = pytest.mark.django_db

BRT = ZoneInfo("America/Sao_Paulo")
NO_HAPPY_HOUR = datetime(2026, 10, 10, 17, 30, tzinfo=BRT)


@pytest.fixture
def balcao():
    cache.clear()
    with patch("django.utils.timezone.now", return_value=NO_HAPPY_HOUR):
        counter = _Counter()
    from shopman.shop.models import RuleConfig

    RuleConfig.objects.create(
        ref="happy_hour", rule_path="shopman.shop.rules.pricing.HappyHourRule",
        label="Happy Hour", params={"discount_percent": 40, "start": "17:00", "end": "18:00"}, enabled=True,
    )
    cache.clear()
    yield counter
    cache.clear()


def _payload(**overrides) -> dict:
    payload = {
        # A vitrine do PDV mostra o preço cheio: é o que a tela manda.
        "items": [{"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1200}],
        "customer_name": "Cliente",
        "payment_method": "cash",
    }
    payload.update(overrides)
    return payload


def _review(**overrides):
    with patch("django.utils.timezone.now", return_value=NO_HAPPY_HOUR):
        return pos_service.review_sale(channel_ref="pdv", payload=_payload(**overrides), operator_username="marina")


def _close(counter, **overrides):
    with patch("django.utils.timezone.now", return_value=NO_HAPPY_HOUR):
        return counter.close(**overrides)


def test_revisao_sem_comanda_mostra_o_total_do_motor(balcao):
    review = _review(tendered_q=2000)

    assert review.subtotal_q == 720
    assert review.total_q == 720
    # O troco que a tela manda devolver é o de verdade: R$ 20,00 por R$ 7,20.
    assert review.change_q == 1280
    # O desconto automático não é desconto do operador: não pede gerente.
    assert review.discount_q == 0
    assert review.requires_manager_approval is False


def test_revisao_sem_comanda_nao_deixa_sessao_para_tras(balcao):
    before = Session.objects.count()

    _review()

    assert Session.objects.count() == before


def test_fechamento_com_o_total_da_vitrine_e_recusado_sem_fechar_nada(balcao):
    with pytest.raises(PosIntentError) as refused:
        _close(
            balcao,
            client_request_id="pos:p0-1-vitrine",
            expected_total_q=1200,
            payment_tenders=[{"method": "cash", "amount_q": 1200, "collection": "terminal"}],
            tendered_q=1200,
        )

    assert refused.value.code == "total_changed"
    assert refused.value.context == {"old_total_q": 1200, "new_total_q": 720}
    assert not Order.objects.filter(data__client_request_id="pos:p0-1-vitrine").exists()


def test_fechamento_com_o_total_do_motor_cobra_o_que_a_tela_mostrou(balcao):
    result = _close(
        balcao,
        client_request_id="pos:p0-1-motor",
        expected_total_q=720,
        payment_tenders=[{"method": "cash", "amount_q": 1000, "collection": "terminal"}],
        tendered_q=1000,
    )

    order = Order.objects.get(ref=result.order_ref)
    payment = order.data["payment"]
    assert order.total_q == 720
    assert payment["amount_q"] == 720
    assert "pos_reconciled_from_amount_q" not in payment
    assert payment["change_q"] == 280


def test_divergencia_no_commit_recusa_em_vez_de_reescrever_o_pagamento(balcao):
    # Rede de segurança: se a prévia e o kernel discordarem, o commit recusa
    # (``expected_total_q`` no contexto do Orderman), em vez de reconciliar calado.
    with patch.object(pos_service, "_stamp_engine_prices", lambda *a, **k: None):
        with pytest.raises(PosIntentError) as refused:
            _close(balcao, client_request_id="pos:p0-1-rede", expected_total_q=1200)

    assert refused.value.code == "total_changed"
    assert refused.value.context == {"old_total_q": 1200, "new_total_q": 720}
    assert refused.value.field == "expected_total_q"
    assert not Order.objects.filter(data__client_request_id="pos:p0-1-rede").exists()
