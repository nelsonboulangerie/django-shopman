"""Caracterização: a decisão de promessa do orquestrador É a do Stockman.

Para cada caso do corpus (rastreado com e sem saldo, sem ledger, ``demand_ok``,
``stock_only`` com plano, pausado, produção planejada para d+N, peso, margem de
segurança do canal), o mesmo mundo é perguntado por todas as portas:

- ``promise_for_sku`` do Stockman, com o recorte do canal (a autoridade);
- ``availability.decide`` e ``availability.decide_many`` do orquestrador.

Os campos da decisão têm que bater um a um. O que o orquestrador ACRESCENTA
(portão da vitrine, forma do dict, ``source``, ``failed_sku``) é composição em
cima do resultado do Stockman e fica fora da comparação, com teste próprio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.stockman import PositionKind
from shopman.stockman.models import Position, Quant
from shopman.stockman.services.availability import promise_for_sku

from shopman.shop.adapters import get_adapter
from shopman.shop.models import Channel, Shop
from shopman.shop.services import availability

pytestmark = pytest.mark.django_db


@dataclass(frozen=True)
class Case:
    name: str
    qty: str
    ready: str | None = None  # None = sem Quant pronto
    planned: str | None = None  # Quant com target_date em d+``days``
    days: int = 0  # target_date da pergunta: hoje + days
    planned_days: int = 1
    policy: str = "planned_ok"
    sellable: bool = True
    unit: str = "un"
    channel: str = "web"


CORPUS = [
    Case("rastreado_cabe", qty="2", ready="5"),
    Case("rastreado_exato", qty="5", ready="5"),
    Case("rastreado_nao_cabe", qty="6", ready="5"),
    Case("sem_ledger", qty="3"),
    Case("demand_ok_sem_saldo", qty="9", ready="0", policy="demand_ok"),
    Case("demand_ok_sem_ledger", qty="9", policy="demand_ok"),
    Case("pausado", qty="1", ready="5", sellable=False),
    Case("pausado_sem_ledger", qty="1", sellable=False),
    Case("planejado_amanha_cabe", qty="4", planned="6", days=1),
    Case("planejado_amanha_nao_cabe", qty="7", planned="6", days=1),
    Case("planejado_d3_pergunta_hoje", qty="2", planned="6", planned_days=3),
    Case("planejado_d3_pergunta_d3", qty="2", ready="1", planned="6", days=3, planned_days=3),
    Case("stock_only_ignora_plano", qty="1", planned="5", days=1, policy="stock_only"),
    Case("peso_cabe", qty="1.2", ready="1.5", unit="kg"),
    Case("peso_nao_cabe", qty="1.6", ready="1.5", unit="kg"),
    Case("margem_canal_remoto_cabe", qty="3", ready="5", channel="remoto"),
    Case("margem_canal_remoto_nao_cabe", qty="4", ready="5", channel="remoto"),
]

# Campos da decisão do Stockman e o nome que levam no dict do orquestrador.
FIELDS = {
    "approved": "approved",
    "sku": "sku",
    "requested_qty": "requested_qty",
    "available_qty": "available_qty",
    "orderable_ceiling": "orderable_ceiling",
    "is_tracked": "is_tracked",
    "reason_code": "reason_code",
    "is_paused": "is_paused",
    "is_planned": "is_planned",
    "available": "ready_qty",
    "target_date": "target_date",
}


def _world(case: Case) -> str:
    Shop.objects.get_or_create(name="Casa", defaults={"brand_name": "Casa"})
    Channel.objects.get_or_create(ref="web", defaults={"name": "Loja online", "is_active": True})
    Channel.objects.get_or_create(
        ref="remoto",
        defaults={"name": "Remoto", "is_active": True, "config": {"stock": {"safety_margin": 2}}},
    )
    sku = f"CARAC-{case.name.upper()}"
    product = Product.objects.create(
        sku=sku,
        name=case.name,
        base_price_q=500,
        unit=case.unit,
        availability_policy=case.policy,
        is_published=True,
        is_sellable=True,
    )
    for channel_ref in ("web", "remoto"):
        listing, _ = Listing.objects.get_or_create(ref=channel_ref, defaults={"name": channel_ref})
        ListingItem.objects.create(listing=listing, product=product, price_q=500)
    vitrine, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    today = timezone.localdate()
    if case.ready is not None:
        Quant.objects.create(sku=sku, position=vitrine, _quantity=Decimal(case.ready))
    if case.planned is not None:
        Quant.objects.create(
            sku=sku,
            position=vitrine,
            target_date=today + timedelta(days=case.planned_days),
            _quantity=Decimal(case.planned),
        )
    if not case.sellable:
        Product.objects.filter(sku=sku).update(is_sellable=False)
    return sku


def _kernel(sku: str, qty: Decimal, case: Case):
    scope = get_adapter("stock").get_channel_scope(case.channel)
    target = timezone.localdate() + timedelta(days=case.days)
    return promise_for_sku(
        sku,
        qty,
        target_date=target,
        safety_margin=scope["safety_margin"],
        allowed_positions=scope["allowed_positions"],
        excluded_positions=scope.get("excluded_positions"),
        expiry_margin_days=scope.get("expiry_margin_days", 0),
        include_nonconforming=scope.get("sells_nonconforming", True),
        allowed_quality_grade_refs=scope.get("allowed_quality_grade_refs"),
    )


def _shop_view(result: dict) -> dict:
    return {kernel_field: result[shop_field] for kernel_field, shop_field in FIELDS.items()}


def _kernel_view(decision) -> dict:
    return {field: getattr(decision, field) for field in FIELDS}


@pytest.mark.parametrize("case", CORPUS, ids=lambda c: c.name)
def test_every_door_returns_stockmans_promise_field_by_field(case: Case):
    sku = _world(case)
    qty = Decimal(case.qty)
    target = timezone.localdate() + timedelta(days=case.days)

    kernel = _kernel_view(_kernel(sku, qty, case))
    decided = availability.decide(sku, qty, channel_ref=case.channel, target_date=target)
    [decided_many] = availability.decide_many([(sku, qty)], channel_ref=case.channel, target_date=target)

    assert _shop_view(decided) == kernel
    assert _shop_view(decided_many) == kernel
    assert decided["source"] == decided_many["source"] == "stock.promise_decision"


def test_corpus_covers_both_answers_and_every_refusal_reason():
    """O corpus não é decorativo: aprova, recusa por falta e recusa por pausa."""
    seen = set()
    for case in CORPUS:
        sku = _world(case)
        decision = _kernel(sku, Decimal(case.qty), case)
        seen.add((decision.approved, decision.reason_code))
    assert seen == {(True, None), (False, "insufficient_supply"), (False, "paused")}


def test_listing_gate_is_composition_before_the_kernel_not_a_second_decision():
    """Fora da vitrine o orquestrador recusa antes de perguntar ao Stockman."""
    case = Case("fora_da_vitrine", qty="1", ready="5")
    sku = _world(case)
    ListingItem.objects.filter(product__sku=sku, listing__ref="web").delete()

    kernel = _kernel(sku, Decimal("1"), case)
    decided = availability.decide(sku, Decimal("1"), channel_ref="web", target_date=timezone.localdate())

    assert kernel.approved is True
    assert decided["approved"] is False
    assert decided["reason_code"] == "not_in_listing"
    assert decided["source"] == "availability.listing_gate"
