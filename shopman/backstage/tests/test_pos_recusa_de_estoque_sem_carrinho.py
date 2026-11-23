"""PDV: a recusa de estoque da loja ("Ajuste o carrinho") não chega ao balcão (#3267, pedaço 2).

A suspeita (inferida do código): ``stock._insufficient_supply_error`` escreve
"Ajuste o carrinho e tente novamente, por favor." e ``pos._commit_refusal``
repassa ``exc.message`` como está, então o operador leria "carrinho".

Medido aqui, pelo caminho do operador (revisar e validar pela API do balcão,
com quem só tem ``operate_pos``): a recusa NÃO nasce no PDV. O canal do balcão
é ``payment.timing == "external"`` (``config/instances/nelson.json``), e o gate
duro do commit (``lifecycle.secure_stock`` → ``stock.hold(require_all=True)``)
sai antes de reservar: a venda de balcão já aconteceu, o pão saiu pela porta.
Acima do estoque ou com o item pausado, a venda vale e o que faltar vira alerta
de reserva (``stock_hold_gap``), nunca recusa. A frase que o operador lê é o
aviso da revisão, na língua do balcão.

Se um dia o balcão passar a recusar por estoque no commit, este teste quebra
no fechamento, e a frase do PDV precisa nascer junto com a recusa.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from shopman.cashman import services as cash
from shopman.cashman.models import Shift, Terminal
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.orderman.models import Order
from shopman.stockman import PositionKind
from shopman.stockman.models import Position, Quant

from shopman.backstage.tests.pos_test_runtime import bind_station, with_screen_total
from shopman.shop.models import Channel, Shop
from shopman.shop.services.pos_intent import POS_SALE_INTENT_VERSION

pytestmark = pytest.mark.django_db

SKU = "RECUSA-BAGUETE"
REVIEW = "/api/v1/backstage/pos/sale/review/"
CLOSE = "/api/v1/backstage/pos/sale/close/"


@pytest.fixture
def balcao(client):
    Shop.objects.create(name="Nelson", brand_name="Nelson")
    # O canal do balcão como o deployment o configura (config/instances/nelson.json).
    Channel.objects.create(
        ref="pdv", name="PDV", is_active=True,
        config={
            "confirmation": {"mode": "immediate"},
            "payment": {"method": "cash", "timing": "external"},
            "stock": {"check_on_commit": False, "allow_untracked": False},
        },
    )
    product = Product.objects.create(sku=SKU, name="Baguete", base_price_q=1000, is_published=True, is_sellable=True)
    listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True)
    ListingItem.objects.create(listing=listing, product=product, price_q=1000)
    vitrine, _ = Position.objects.get_or_create(
        ref="vitrine", defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    Quant.objects.create(sku=SKU, position=vitrine, _quantity=Decimal("1"))

    operator = get_user_model().objects.create_user(username="fran", password="x", is_staff=True)
    operator.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get_for_model(Shift), codename="operate_pos"),
    )
    client.force_login(operator)
    terminal = Terminal.default()
    bind_station(client, terminal.ref)
    shift = cash.open_shift(operator=operator, terminal=terminal, float_q=0)
    return client, shift, product


def _payload(shift, request_id: str) -> dict:
    return {
        "intent_version": POS_SALE_INTENT_VERSION,
        # Cinco baguetes contra uma na vitrine: a reserva não cobre.
        "items": [{"sku": SKU, "name": "Baguete", "qty": 5, "unit_price_q": 1000}],
        "fulfillment_type": "pickup",
        "payment_method": "cash",
        "payment_collection": "terminal",
        "tendered_q": 5000,
        "client_request_id": request_id,
        "cash_shift_id": shift.pk,
    }


@pytest.mark.parametrize("paused", [False, True], ids=["acima-do-estoque", "item-pausado"])
def test_venda_que_o_estoque_nao_cobre_valida_e_o_operador_nao_le_carrinho(balcao, paused):
    client, shift, product = balcao
    if paused:
        product.is_sellable = False
        product.save(update_fields=["is_sellable"])
    payload = _payload(shift, f"recusa-estoque-{'pausado' if paused else 'acima'}")

    review = client.post(REVIEW, data=payload, content_type="application/json")
    assert review.status_code == 200, review.content
    assert "carrinho" not in review.content.decode().lower()

    close = client.post(CLOSE, data=with_screen_total(payload), content_type="application/json")
    assert close.status_code == 200, close.content
    assert close.json()["ok"] is True
    assert "carrinho" not in close.content.decode().lower()
    assert Order.objects.filter(ref=close.json()["order_ref"], channel_ref="pdv").exists()
