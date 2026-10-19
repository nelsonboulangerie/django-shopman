"""A revisão do PDV mostra o total que o MOTOR cobra (A3-1, laudo CORE-SOVEREIGNTY 18/10/2026).

A revisão tinha uma segunda implementação do "maior desconto ganha", e ela
arredondava diferente do ``DiscountModifier``: ``round`` do Python leva meio
centavo para o PAR, o motor leva para CIMA. Um item de R$ 12,05 com 10% de
cortesia revisava R$ 10,85, o motor cobrava R$ 10,84, e o selo do fechamento
(``CommitSeal``) recusava a venda com ``total_changed`` em TODA tentativa: cada
nova revisão voltava a dizer R$ 10,85. O laudo mediu 2.375 divergências em
25.000 combinações (preço de 1 a 5.000 centavos × 5%, 10%, 15%, 25%, 50%).

A conta paralela foi apagada, não corrigida: a revisão pergunta ao motor. Este
arquivo prova, ponta a ponta (revisão pela API, fechamento pela API), que o total
revisado é o total que fecha:

1. o caso do laudo, sem comanda e com comanda (``tabs/save/?review=1``);
2. uma varredura de preços × percentuais, com todos os meios-centavos de
   fronteira, revisão contra fechamento, zero divergência. A varredura inteira
   do laudo (preços de 1 a 5.000) roda com ``SHOPMAN_POS_PARITY_PRICES=1-5000``,
   ou em fatias (``1-1250``, ``1251-2500``...), fora da CI: são 25.000 vendas.
"""

from __future__ import annotations

import json
import os
from decimal import ROUND_HALF_UP, Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from shopman.cashman import services as cash
from shopman.cashman.models import Shift, Terminal
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.orderman.models import Order

from shopman.backstage.models import POSTab
from shopman.backstage.projections.pos import build_open_tab
from shopman.backstage.tests.pos_test_runtime import bind_station
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import POS_SALE_INTENT_VERSION

pytestmark = pytest.mark.django_db

REVIEW_URL = "/api/v1/backstage/pos/sale/review/"
CLOSE_URL = "/api/v1/backstage/pos/sale/close/"
SAVE_URL = "/api/v1/backstage/pos/tabs/save/"
SKU = "PAO-A31"
PERCENTUAIS = (5, 10, 15, 25, 50)


@pytest.fixture
def balcao(client):
    Shop.objects.create(name="Nelson", brand_name="Nelson")
    Channel.objects.create(
        ref="pdv",
        name="PDV",
        is_active=True,
        config={
            "payment": {"method": "cash", "timing": "external"},
            "stock": {"check_on_commit": False},
        },
    )
    POSTab.objects.create(ref="00000031", label="31")
    product = Product.objects.create(
        sku=SKU, name="Pão A3-1", base_price_q=1205, is_published=True, is_sellable=True,
    )
    listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True)
    listing_item = ListingItem.objects.create(listing=listing, product=product, price_q=1205)
    operator = get_user_model().objects.create_user(username="caixa-a31", password="x", is_staff=True)
    operator.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get_for_model(Shift), codename="operate_pos"),
    )
    client.force_login(operator)
    terminal = Terminal.default()
    bind_station(client, terminal.ref)
    cash.open_shift(operator=operator, terminal=terminal, float_q=0)
    return {"client": client, "listing_item": listing_item}


def _post(client, url: str, body: dict):
    return client.post(url, data=json.dumps(body), content_type="application/json")


def _intent(price_q: int, percent: int, *, request_id: str, qty: int = 1, **extra) -> dict:
    return {
        "intent_version": POS_SALE_INTENT_VERSION,
        "items": [{
            "line_id": "L1",
            "sku": SKU,
            "name": "Pão A3-1",
            "qty": qty,
            "unit_price_q": price_q,
            "discount": {"type": "percent", "value": percent, "reason": "cortesia"},
        }],
        "fulfillment_type": "pickup",
        "payment_method": "cash",
        "payment_collection": "terminal",
        "client_request_id": request_id,
        **extra,
    }


def _motor_q(price_q: int, percent: int) -> int:
    """O preço com a cortesia pela régua do motor, meio centavo para cima."""
    off = (Decimal(price_q) * percent / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return price_q - int(off)


def _review_then_close(client, body: dict) -> tuple[int, object]:
    review = _post(client, REVIEW_URL, body)
    assert review.status_code == 200, review.content
    shown_q = review.json()["review"]["total_q"]
    closed = _post(client, CLOSE_URL, {**body, "expected_total_q": shown_q})
    return shown_q, closed


def test_o_caso_do_laudo_fecha_sem_comanda(balcao):
    """R$ 12,05 com 10% de cortesia: revisava R$ 10,85, o motor cobra R$ 10,84."""
    shown_q, closed = _review_then_close(balcao["client"], _intent(1205, 10, request_id="a31-laudo"))

    assert shown_q == 1084
    assert closed.status_code == 200, closed.content
    assert Order.objects.get(ref=closed.json()["order_ref"]).total_q == 1084


def test_o_caso_do_laudo_fecha_com_comanda(balcao):
    """A comanda gravada já passou pelo motor: a revisão lê o total dela."""
    client = balcao["client"]
    session = pos_service.open_pos_tab(channel_ref="pdv", tab_ref="31", actor="test", operator_username="caixa-a31")
    body = _intent(
        1205, 10, request_id="a31-comanda", qty=3,
        tab_ref="31", tab_session_key=session.session_key,
        expected_revision=build_open_tab(session)["revision"],
        manual_discount={"type": "percent", "value": 5, "reason": "cortesia"},
    )

    saved = _post(client, f"{SAVE_URL}?review=1", body)

    assert saved.status_code == 200, saved.content
    review = saved.json()["review"]
    session.refresh_from_db()
    motor_q = sum(int(line["line_total_q"]) for line in session.items)
    assert review["total_q"] == motor_q
    assert review["subtotal_q"] - review["discount_q"] == motor_q
    closed = _post(client, CLOSE_URL, {
        **body, "expected_revision": saved.json()["revision"], "expected_total_q": review["total_q"],
    })
    assert closed.status_code == 200, closed.content
    assert Order.objects.get(ref=closed.json()["order_ref"]).total_q == motor_q


def _sweep_prices() -> list[int]:
    wanted = os.environ.get("SHOPMAN_POS_PARITY_PRICES", "").strip()
    if wanted:
        first, last = (int(part) for part in wanted.split("-"))
        return list(range(first, last + 1))
    # Toda a fronteira de meio centavo até R$ 12,05 (o caso do laudo) para os
    # cinco percentuais, mais alguns preços exatos de controle.
    boundary = sorted({
        price for price in range(1, 1206)
        for percent in PERCENTUAIS
        if (price * percent) % 100 == 50
    })
    return boundary[::30] + [1205, 1300, 4999, 5000]


def test_revisao_e_fechamento_dao_o_mesmo_total_em_toda_a_varredura(balcao):
    client, listing_item = balcao["client"], balcao["listing_item"]
    divergentes: list[tuple[int, int, int, int]] = []
    casos = 0
    for price_q in _sweep_prices():
        listing_item.price_q = price_q
        listing_item.save(update_fields=["price_q"])
        for percent in PERCENTUAIS:
            casos += 1
            shown_q, closed = _review_then_close(
                client, _intent(price_q, percent, request_id=f"a31-{price_q}-{percent}"),
            )
            if closed.status_code != 200:
                divergentes.append((price_q, percent, shown_q, closed.status_code))
                continue
            charged_q = Order.objects.get(ref=closed.json()["order_ref"]).total_q
            if charged_q != shown_q or shown_q != _motor_q(price_q, percent):
                divergentes.append((price_q, percent, shown_q, charged_q))
    print(f"casos: {casos} divergentes: {len(divergentes)}")
    assert divergentes == []
