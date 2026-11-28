"""A observação do pedido acima do limite é recusada, nunca cortada em silêncio.

Beta test de 05/11/2026 (PDV2-08): o detalhe da encomenda terminava em "...sunt
in culpa qui offic", sem aviso. O servidor cortava no 500º caractere e a tela não
tinha limite. Agora a tela para no mesmo limite e o servidor recusa com o campo.
"""

from __future__ import annotations

import pytest
from django.utils import timezone
from shopman.guestman.models import Customer

from shopman.shop.services.pos_intent import ORDER_NOTES_LIMIT, PosIntentError, parse_pos_sale_intent

pytestmark = pytest.mark.django_db


def _encomenda(notes: str) -> dict:
    customer, _ = Customer.objects.get_or_create(ref="obs", defaults={"first_name": "Maria"})
    return {
        "sales_mode": "order", "customer_ref": customer.ref, "fulfillment_type": "pickup",
        "delivery_date": timezone.localdate().isoformat(), "order_notes": notes,
        "items": [{"sku": "CR", "qty": 1, "unit_price_q": 900}],
    }


def test_observacao_acima_do_limite_e_recusada_com_o_campo():
    with pytest.raises(PosIntentError) as error:
        parse_pos_sale_intent(_encomenda("x" * (ORDER_NOTES_LIMIT + 1)), for_commit=False)
    assert error.value.code == "order_notes_too_long"
    assert error.value.field == "order_notes"


def test_observacao_no_limite_passa_inteira():
    intent = parse_pos_sale_intent(_encomenda("y" * ORDER_NOTES_LIMIT), for_commit=False)
    assert intent.payload["order_notes"] == "y" * ORDER_NOTES_LIMIT
