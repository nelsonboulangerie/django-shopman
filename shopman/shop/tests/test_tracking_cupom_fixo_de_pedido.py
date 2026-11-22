"""No acompanhamento, o cupom sai uma vez só, e a conta fecha com o total (#3246).

A conta do acompanhamento é: linhas (com a promoção do produto já abatida e o
cupom devolvido à linha) menos os descontos do resumo (cupom, pontos) mais a
entrega, igual ao total do pedido. O cupom de valor FIXO é desconto de PEDIDO:
o motor o rateia no preço das linhas e grava um registro sem ``line_id`` e sem
``sku``, que não casa com linha nenhuma. Se a linha não recebe de volta a sua
fatia, o resumo subtrai o cupom de novo e a cliente vê o desconto duas vezes.

O pedido nasce pelo fluxo de verdade (sessão, modifiers, ``CommitService``), para
que os registros selados sejam os que o motor grava.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.orderman.models import Order
from shopman.orderman.tests.commit_support import seal_for

from shopman.shop.models import Channel, Coupon, Promotion, Shop
from shopman.shop.projections.order_tracking import build_tracking
from shopman.shop.services import sessions

pytestmark = pytest.mark.django_db


@pytest.fixture
def channel(db):
    Shop.objects.get_or_create(name="Test Shop")
    Product.objects.create(sku="PAO-3246", name="Pão", base_price_q=1500, is_published=True, is_sellable=True)
    Product.objects.create(sku="BOLO-3246", name="Bolo", base_price_q=2200, is_published=True, is_sellable=True)
    return Channel.objects.get_or_create(ref="web", defaults={"name": "Web"})[0]


def _coupon(*, code: str, type_: str, value: int, min_order_q: int = 0) -> None:
    now = timezone.now()
    promo = Promotion.objects.create(
        ref=f"cupom-3246-{code.lower()}",
        name=code,
        type=type_,
        value=value,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
        min_order_q=min_order_q,
    )
    Coupon.objects.create(code=code, promotion=promo, max_uses=0, is_active=True)


def _commit(channel, *, lines: list[tuple[str, int, int]], code: str, django_capture_on_commit_callbacks) -> Order:
    session = sessions.create_session(channel.ref)
    ops = [
        {"op": "add_line", "sku": sku, "name": sku, "qty": qty, "unit_price_q": price_q}
        for sku, qty, price_q in lines
    ]
    ops += [
        {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
        {"op": "set_data", "path": "coupon_code", "value": code},
        {"op": "set_data", "path": "payment", "value": {"method": "cash"}},
    ]
    sessions.modify_session(session_key=session.session_key, channel_ref=channel.ref, ops=ops)
    with django_capture_on_commit_callbacks(execute=True):
        result = sessions.commit_session(
            session_key=session.session_key,
            channel_ref=channel.ref,
            idempotency_key=sessions.new_idempotency_key(),
            seal=seal_for(session.session_key, channel.ref),
        )
    return Order.objects.get(ref=result.order_ref)


def _assert_conta_fecha(order, *, coupon_q: int, list_q: int) -> None:
    data = build_tracking(order)
    lines_q = sum(item.bill_line_total_q or item.line_total_q for item in data.items)
    summary_q = sum(line.amount_q for line in data.discount_lines)
    coupon_rows = [line for line in data.discount_lines if line.is_coupon]

    assert [line.amount_q for line in coupon_rows] == [coupon_q], "o cupom sai uma vez só, no resumo"
    assert lines_q == list_q, "a linha leva de volta o cupom: soma das linhas é o preço sem cupom"
    assert lines_q - summary_q + (data.delivery_fee_q or 0) == data.total_q == order.total_q, (
        f"linhas {lines_q} - resumo {summary_q} + entrega {data.delivery_fee_q or 0} != total {order.total_q}"
    )


@pytest.mark.parametrize(
    "lines",
    [
        [("PAO-3246", 5, 1500)],  # rateio exato: 500 / 5
        [("PAO-3246", 6, 1500)],  # rateio inexato: 84 × 6 = 504
        [("PAO-3246", 2, 1500), ("BOLO-3246", 1, 2200)],  # duas linhas
    ],
)
def test_cupom_fixo_de_pedido_sai_uma_vez_so(channel, lines, django_capture_on_commit_callbacks):
    _coupon(code="PRIMEIRACOMPRA", type_=Promotion.FIXED, value=500, min_order_q=3000)

    order = _commit(channel, lines=lines, code="PRIMEIRACOMPRA",
                    django_capture_on_commit_callbacks=django_capture_on_commit_callbacks)

    coupon_q = int(order.snapshot["pricing"]["coupon"]["discount_q"])
    list_q = sum(qty * price_q for _sku, qty, price_q in lines)
    assert coupon_q >= 500, "setup: o cupom fixo tem de valer"
    assert order.total_q == list_q - coupon_q
    _assert_conta_fecha(order, coupon_q=coupon_q, list_q=list_q)


def test_cupom_percentual_controle(channel, django_capture_on_commit_callbacks):
    _coupon(code="DEZ3246", type_=Promotion.PERCENT, value=10)

    order = _commit(channel, lines=[("PAO-3246", 3, 1500)], code="DEZ3246",
                    django_capture_on_commit_callbacks=django_capture_on_commit_callbacks)

    assert order.total_q == 4500 - 450, "setup: o cupom percentual tem de valer"
    _assert_conta_fecha(order, coupon_q=450, list_q=4500)
