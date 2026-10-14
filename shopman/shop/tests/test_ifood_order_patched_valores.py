"""ORDER_PATCHED: o dinheiro do pedido acompanha os itens.

P0-5 do mapa de cenários de pedido. A Etapa 2 (``_apply_patch``) já relia o
pedido no iFood e trazia itens, total efetivo, estoque e cozinha para a lista
nova. Os fatos FINANCEIROS do iFood gravados na ingestão (``ifood.totals``,
``ifood.payments``, ``ifood.benefits``, ``payment.status``) ficavam com os
valores de antes. E é deles que a nota calcula a base da casa
(``fiscal_intermediary.seller_amounts``) e que o Gestor diz quanto falta
receber (``payment.balance_due_q``): a nota saía com a base velha sobre os
itens novos, e o saldo do iFood virava "sem evidência".

Nenhuma chamada sai para o iFood: a releitura é ``fetch_order`` com mock.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from shopman.orderman.models import Order

from shopman.shop.services import fiscal, ifood_events, ifood_orders, order_composition, payment
from shopman.shop.tests.test_ifood_order_patched_reconciliation import (
    CAFE,
    ORDER_ID,
    PAO,
    _line,
    _patch_event,
    _world,
)

pytestmark = pytest.mark.django_db


def _raw(items, *, benefit: tuple[str, float] | None, prepaid: float, pending: float = 0.0, methods=None) -> dict:
    """O ``GET /orders/{id}`` com subtotal, cupom (patrocinador, valor) e pagamento."""
    subtotal = round(sum(item["totalPrice"] for item in items), 2)
    discount = benefit[1] if benefit else 0.0
    raw = {
        "id": ORDER_ID,
        "displayId": "1234",
        "orderType": "DELIVERY",
        "merchant": {"id": "merchant"},
        "customer": {"name": "Cliente"},
        "delivery": {"deliveredBy": "IFOOD"},
        "items": [
            {"id": item["id"], "externalCode": item["sku"], "name": item["name"],
             "quantity": item["quantity"], "unitPrice": item["unitPrice"], "totalPrice": item["totalPrice"]}
            for item in items
        ],
        "total": {"subTotal": subtotal, "deliveryFee": 0, "additionalFees": 0, "benefits": discount,
                  "orderAmount": round(subtotal - discount, 2)},
        "payments": {"prepaid": prepaid, "pending": pending, "methods": methods or []},
        "benefits": [],
    }
    if benefit:
        sponsor, value = benefit
        raw["benefits"] = [{"value": value, "target": "CART",
                            "sponsorshipValues": [{"name": sponsor, "value": value}]}]
    return raw


_ORIGINAL = [_line(PAO, "Pão francês", 2), _line(CAFE, "Café coado", 1)]  # R$ 15,00


def _ingest(raw) -> Order:
    from shopman.shop.services import ifood_ingest

    payload = ifood_orders.map_order(raw)
    payload["merchant_id"] = "merchant"
    with patch.object(ifood_ingest.order_changed, "send"):
        order = ifood_ingest.ingest(payload)
    order.refresh_from_db()
    return order


def _patch(final_raw, *, event_id="evt-valores"):
    with (
        patch.object(ifood_events, "acknowledge", return_value=True),
        patch.object(ifood_orders, "fetch_order", return_value=final_raw),
    ):
        return ifood_events.process_events([_patch_event(event_id=event_id)])


def test_patch_rereads_totals_payments_and_benefits_and_the_note_follows():
    _world()
    # Nasceu com cupom da LOJA (R$ 1,00: desconto da casa) e pago online.
    order = _ingest(_raw(_ORIGINAL, benefit=("MERCHANT", 1.0), prepaid=14.0))
    assert fiscal.note_base_q(order) == 1400

    # O cliente dobrou o pão; o cupom agora é do iFood (repasse, não desconto).
    final = [_line(PAO, "Pão francês", 4), _line(CAFE, "Café coado", 1)]  # R$ 25,00
    summary = _patch(_raw(final, benefit=("IFOOD", 2.0), prepaid=23.0))
    assert summary["ingested"] == 1

    order.refresh_from_db()
    facts = order.data["ifood"]
    assert facts["totals"]["subtotal_q"] == 2500
    assert facts["totals"]["order_amount_q"] == 2300
    assert facts["payments"]["prepaid_q"] == 2300
    assert [b["sponsorships"][0]["sponsor"] for b in facts["benefits"]] == ["IFOOD"]
    # O que havia antes fica no registro da alteração, para auditoria.
    record = facts["patches"][-1]
    assert record["reconciled"] is True
    assert record["previous_financials"]["totals"]["order_amount_q"] == 1400
    assert record["previous_financials"]["benefits"][0]["sponsorships"][0]["sponsor"] == "MERCHANT"

    # A nota: base da casa = mercadoria nova cheia (o cupom do iFood é repasse),
    # e bate com a soma dos itens que ela declara.
    assert fiscal.note_base_q(order) == 2500
    assert sum(int(item["total_q"]) for item in fiscal._build_fiscal_items(order)) == 2500
    assert fiscal._fiscal_payment(order, order.data)["amount_q"] == 2500
    assert not fiscal._payment_below_total(fiscal._fiscal_payment(order, order.data), order)
    # O saldo: pago online, nada a receber.
    assert order.data["payment"]["status"] == "paid"
    assert payment.balance_due_q(order) == 0


def test_a_smaller_order_is_still_paid_not_unknown():
    _world()
    order = _ingest(_raw(_ORIGINAL, benefit=None, prepaid=15.0))

    _patch(_raw([_line(PAO, "Pão francês", 1)], benefit=None, prepaid=5.0))

    order.refresh_from_db()
    assert order_composition.effective_total_q(order) == 500
    assert order.data["ifood"]["payments"]["prepaid_q"] == 500
    # Antes: o pago novo (R$ 5) contra o total SELADO (R$ 15) dava "sem evidência".
    assert payment.balance_due_q(order) == 0
    assert fiscal.note_base_q(order) == 500


def test_cash_on_delivery_amount_follows_the_change():
    """Entrega da loja com dinheiro na porta: o valor a cobrar é o novo."""
    _world()
    cash = [{"method": "CASH", "type": "OFFLINE", "prepaid": False, "value": 15.0, "cash": {"changeFor": 20.0}}]
    raw = _raw(_ORIGINAL, benefit=None, prepaid=0.0, pending=15.0, methods=cash)
    raw["delivery"] = {"deliveredBy": "MERCHANT"}
    order = _ingest(raw)
    assert order.data["payment"]["tenders"][0]["amount_q"] == 1500

    final = [_line(PAO, "Pão francês", 4), _line(CAFE, "Café coado", 1)]
    cash_final = [{"method": "CASH", "type": "OFFLINE", "prepaid": False, "value": 25.0, "cash": {"changeFor": 50.0}}]
    raw_final = _raw(final, benefit=None, prepaid=0.0, pending=25.0, methods=cash_final)
    raw_final["delivery"] = {"deliveredBy": "MERCHANT"}
    _patch(raw_final)

    order.refresh_from_db()
    tender = order.data["payment"]["tenders"][0]
    assert tender["amount_q"] == 2500
    assert tender["status"] == "pending"
    assert order.data["payment"]["change_for_q"] == 5000
    assert order.data["payment"]["status"] == "pending"
    assert payment.balance_due_q(order) == 2500


def test_an_authorized_nfce_keeps_the_money_facts_and_never_emits():
    """A nota já saiu: nada se regrava e nada se emite sozinho; o aviso diz o caminho."""
    from django.utils import timezone

    from shopman.backstage.models import OperatorAlert

    _world()
    order = _ingest(_raw(_ORIGINAL, benefit=("MERCHANT", 1.0), prepaid=14.0))
    order.data = {**order.data, "nfce_access_key": "4126chave", "nfce_authorized_at": timezone.now().isoformat()}
    order.save(update_fields=["data", "updated_at"])

    with patch.object(fiscal, "emit") as emit:
        _patch(_raw([_line(PAO, "Pão francês", 4)], benefit=None, prepaid=20.0))

    emit.assert_not_called()
    order.refresh_from_db()
    assert order.data["ifood"]["totals"]["order_amount_q"] == 1400
    assert order.data["ifood"]["patches"][-1]["reconciliation"] == "blocked:fiscal_authorized"
    alert = OperatorAlert.objects.get(type="ifood_order_patched")
    assert "AINDA DÁ TEMPO DE CANCELAR" in alert.message
