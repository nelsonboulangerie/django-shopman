"""Crédito ou débito é o cliente quem escolhe no Checkout da Stripe — e a NFC-e
precisa do código certo (03/04). O adapter lê `latest_charge.payment_method_details
.card.funding` na captura, o serviço grava `payment.card_funding` no pedido, e o
adapter fiscal traduz. Sem o dado, "99 outros" — nunca "03" num débito."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from shopman.shop.adapters.payment_stripe import _card_funding, _charge_id
from shopman.shop.adapters.payment_types import PaymentResult


def _intent(charge):
    return SimpleNamespace(id="pi_1", status="succeeded", latest_charge=charge, amount_received=1000)


def test_funding_vem_da_cobranca_expandida():
    charge = SimpleNamespace(id="ch_1", payment_method_details=SimpleNamespace(card=SimpleNamespace(funding="debit")))
    assert _card_funding(_intent(charge)) == "debit"
    assert _charge_id(_intent(charge)) == "ch_1"


def test_cobranca_como_string_nao_tem_funding_e_mantem_o_id():
    assert _card_funding(_intent("ch_str")) is None
    assert _charge_id(_intent("ch_str")) == "ch_str"


def test_funding_desconhecido_ou_mock_vira_none():
    # Um MagicMock devolve MagicMock em qualquer atributo: não pode virar "funding".
    assert _card_funding(_intent(MagicMock())) is None
    charge = SimpleNamespace(id="ch_2", payment_method_details=SimpleNamespace(card=SimpleNamespace(funding="gift")))
    assert _card_funding(_intent(charge)) is None
    assert _card_funding(_intent(None)) is None


def test_funding_em_dict_tambem_e_lido():
    charge = SimpleNamespace(id="ch_3", payment_method_details={"card": {"funding": "credit"}})
    assert _card_funding(_intent(charge)) == "credit"


@pytest.mark.django_db
def test_capture_once_grava_card_funding_no_pedido():
    from shopman.shop.services import payment as payment_service

    order = SimpleNamespace(
        ref="ORD-FUND", pk=1,
        data={"payment": {"intent_ref": "PI-1", "method": "link"}},
        save=MagicMock(),
    )
    adapter = MagicMock()
    adapter.capture.return_value = PaymentResult(success=True, transaction_id="ch_9", amount_q=1000, card_funding="debit")
    with patch.object(payment_service, "_payman_intent_captured", return_value=False), \
         patch.object(payment_service, "_adapter_for_persisted_intent", return_value=adapter), \
         patch.object(payment_service, "_ack_payment_failed_alerts"), \
         patch.object(payment_service, "cancel_stale_intents"):
        payment_service._capture_once(order)

    assert order.data["payment"]["transaction_id"] == "ch_9"
    assert order.data["payment"]["card_funding"] == "debit"
    order.save.assert_called_once()


@pytest.mark.django_db
def test_capture_once_sem_funding_nao_inventa_a_chave():
    from shopman.shop.services import payment as payment_service

    order = SimpleNamespace(
        ref="ORD-NOFUND", pk=2,
        data={"payment": {"intent_ref": "PI-2", "method": "pix"}},
        save=MagicMock(),
    )
    adapter = MagicMock()
    adapter.capture.return_value = PaymentResult(success=True, transaction_id="e2e", amount_q=1000)
    with patch.object(payment_service, "_payman_intent_captured", return_value=False), \
         patch.object(payment_service, "_adapter_for_persisted_intent", return_value=adapter), \
         patch.object(payment_service, "_ack_payment_failed_alerts"), \
         patch.object(payment_service, "cancel_stale_intents"):
        payment_service._capture_once(order)

    assert "card_funding" not in order.data["payment"]
