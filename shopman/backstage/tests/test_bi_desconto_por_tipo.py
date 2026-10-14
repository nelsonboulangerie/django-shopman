"""O B.I. lê o desconto por TIPO de grupo (equipe/parceiro) do snapshot do pedido.

A spec §7.1 item 4 do dono pede o desconto "registrado por tipo para o B.I.". O
motor de preço grava o tipo por linha em pricing.discount.items[] e o total do
grupo em pricing.discount.savings.amount_q (shop/modifiers.py). Aqui a soma por
tipo tem que bater com esse total: senão o B.I. mostraria um número que o pedido
não sustenta.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.backstage.projections.bi_sales import build_bi_sales


def _at(days_ago: int, hour: int = 12):
    local = timezone.localtime(timezone.now()).replace(hour=hour, minute=0, second=0, microsecond=0)
    return local - timedelta(days=days_ago)


def _record(*, kind: str | None, per_unit_q: int, qty: int) -> dict:
    record = {
        "line_id": "L1",
        "sku": "PAO",
        "type": "promotion",
        "name": "Grupo",
        "original_price_q": 1000,
        "discount_q": per_unit_q,
        "qty": qty,
    }
    if kind:
        record["discount_kind"] = kind
    return record


def _native(
    *,
    kind: str | None,
    per_unit_q: int = 0,
    qty: int = 1,
    channel_ref: str = "pdv",
    days_ago: int = 1,
    savings_q: int | None = None,
    include_untyped_record: bool = False,
):
    data: dict = {"payment": {"method": "pix"}}
    records = []
    if kind:
        records.append(_record(kind=kind, per_unit_q=per_unit_q, qty=qty))
    if include_untyped_record:
        # Desconto sem tipo (manual, cupom): não é desconto de grupo.
        records.append(_record(kind=None, per_unit_q=per_unit_q, qty=qty))
    if records:
        recorded_total = per_unit_q * qty if kind else 0
        savings = {}
        if kind:
            savings = {
                "amount_q": savings_q if savings_q is not None else recorded_total,
                "group": "Grupo",
                "kind": kind,
                "message": "Hoje você economizou por ser do grupo",
            }
        data["pricing"] = {
            "discount": {
                "total_discount_q": recorded_total + (per_unit_q * qty if include_untyped_record else 0),
                "items": records,
                **({"savings": savings} if savings else {}),
            }
        }
    order = Order.objects.create(
        ref=f"N-{Order.objects.count()}",
        channel_ref=channel_ref,
        status=Order.Status.COMPLETED,
        total_q=1000,
        data=data,
    )
    Order.objects.filter(pk=order.pk).update(created_at=_at(days_ago))
    return order


@pytest.mark.django_db
def test_bi_reads_the_discount_of_each_group_kind():
    _native(kind="equipe", per_unit_q=100, qty=2)  # 200
    _native(kind="parceiro", per_unit_q=150, qty=1, days_ago=2)  # 150
    report = build_bi_sales(date_from=_at(3).date(), date_to=_at(0).date())

    assert [(row.kind, row.amount_q) for row in report.discount_by_kind] == [
        ("equipe", 200),
        ("parceiro", 150),
    ]
    assert report.discount_kind_total_q == 350
    assert sum(row.amount_q for row in report.discount_by_kind) == report.discount_kind_total_q


@pytest.mark.django_db
def test_the_sum_by_kind_equals_the_total_the_order_recorded():
    """A soma por tipo bate, campo a campo, com o total que o motor gravou."""
    _native(kind="equipe", per_unit_q=100, qty=2, savings_q=200)
    report = build_bi_sales(date_from=_at(2).date(), date_to=_at(0).date())

    recorded = Order.objects.get().data["pricing"]["discount"]["savings"]["amount_q"]
    assert recorded == 200
    assert report.discount_kind_total_q == recorded
    assert sum(row.amount_q for row in report.discount_by_kind) == recorded


@pytest.mark.django_db
def test_discount_without_kind_and_order_without_discount_contribute_nothing():
    _native(kind=None)  # sem pricing
    _native(kind=None, per_unit_q=90, include_untyped_record=True)  # desconto sem tipo
    report = build_bi_sales(date_from=_at(2).date(), date_to=_at(0).date())

    assert report.discount_by_kind == ()
    assert report.discount_kind_total_q == 0


@pytest.mark.django_db
def test_the_channel_filter_applies_to_the_discount_reading():
    _native(kind="equipe", per_unit_q=100, qty=2, channel_ref="pdv")
    _native(kind="parceiro", per_unit_q=150, qty=1, channel_ref="web")

    everything = build_bi_sales(date_from=_at(2).date(), date_to=_at(0).date())
    only_web = build_bi_sales(date_from=_at(2).date(), date_to=_at(0).date(), channel="web")

    assert everything.discount_kind_total_q == 350
    assert [(row.kind, row.amount_q) for row in only_web.discount_by_kind] == [("parceiro", 150)]
    assert only_web.discount_kind_total_q == 150
