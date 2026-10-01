"""O cardápio lê o estoque UMA vez: hoje, as fornadas da fila e os componentes de bundle.

Antes, um request do cardápio chamava o Stockman quatro vezes: hoje; de novo
para CADA data candidata da fila de espera; e de novo para os componentes de
bundle (que quase sempre já estavam na leitura de hoje). Cada chamada
materializava todas as linhas de ``Quant`` outra vez, e esse era o custo do
estágio ``availability`` (O(linhas), não SQL).

Estes testes provam que a leitura única devolve exatamente o que a composição
antiga devolvia. O oráculo é a composição antiga escrita aqui, chamando o
``availability_for_skus`` de ANTES da mudança (a cópia congelada que mora nos
testes do Stockman), uma leitura por data — e o resultado tem de bater campo a
campo, com a fila ligada e desligada.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from shopman.offerman.models import Listing, ListingItem, Product, ProductComponent
from shopman.stockman.models import Batch, Hold, HoldStatus, Position, PositionKind, Quant
from shopman.stockman.tests.test_availability_on_dates import _reference_availability_for_skus

from shopman.shop.projections import catalog_context
from shopman.shop.services import waitlist

pytestmark = pytest.mark.django_db

DAY = timedelta(days=1)


# ── O oráculo: a composição antiga, uma leitura do Stockman por data ─────────


def _reference_scope_kwargs(channel_ref: str) -> dict:
    from shopman.shop.adapters import stock as stock_adapter

    scope = stock_adapter.get_channel_scope(channel_ref)
    return {
        "safety_margin": scope["safety_margin"],
        "allowed_positions": scope["allowed_positions"],
        "excluded_positions": scope.get("excluded_positions"),
        "expiry_margin_days": scope.get("expiry_margin_days", 0),
        "include_nonconforming": scope.get("sells_nonconforming", True),
        "allowed_quality_grade_refs": scope.get("allowed_quality_grade_refs"),
    }


def _reference_next_batch(skus: list[str], channel_ref: str) -> dict:
    """``waitlist.next_batch_availability_for_skus`` como era: uma leitura por data."""
    unique_skus = list(dict.fromkeys(sku for sku in skus if sku))
    horizon = waitlist.promise_horizon(channel_ref)
    today = timezone.localdate()
    if not unique_skus or horizon <= today:
        return {}
    kwargs = waitlist.scope_kwargs(channel_ref)
    candidate_dates = list(
        Quant.objects.filter(
            sku__in=unique_skus,
            _quantity__gt=0,
            target_date__gt=today,
            target_date__lte=horizon,
        )
        .order_by("target_date")
        .values_list("target_date", flat=True)
        .distinct()
    )
    remaining = set(unique_skus)
    result = {}
    for candidate in candidate_dates:
        if not remaining:
            break
        infos = _reference_availability_for_skus(sorted(remaining), target_date=candidate, **kwargs)
        for sku in tuple(remaining):
            info = infos.get(sku) or {}
            if Decimal(str(info.get("planned") or 0)) <= 0:
                continue
            result[sku] = (candidate, info)
            remaining.remove(sku)
    return result


def _reference_catalog_availability(skus: list[str], channel_ref: str) -> dict:
    """``catalog_context.availability_for_skus`` sem data, como era."""
    current = _reference_availability_for_skus(
        skus,
        target_date=timezone.localdate(),
        **_reference_scope_kwargs(channel_ref),
    )
    next_batches = _reference_next_batch(skus, channel_ref)
    if not next_batches:
        return current
    return {
        sku: catalog_context._merge_waitlist_availability(
            current.get(sku),
            next_batches.get(sku, (None, None))[1],
        )
        for sku in skus
    }


def _reference_bundle_availability(bundle_skus: list[str], channel_ref: str) -> dict:
    """``bundle_availability_for_skus`` como era: segunda leitura para os componentes."""
    expanded = {sku: catalog_context.expand_bundle(sku) for sku in bundle_skus}
    component_skus = sorted({c["sku"] for components in expanded.values() for c in components})
    comp_avail = _reference_availability_for_skus(
        component_skus,
        target_date=timezone.localdate(),
        **_reference_scope_kwargs(channel_ref),
    )
    return {
        sku: catalog_context.bundle_availability_from_components(
            [(Decimal(str(c["qty"])), comp_avail.get(c["sku"])) for c in components]
        )
        if components
        else None
        for sku, components in expanded.items()
    }


def _canonical(by_sku: dict) -> dict:
    out = {}
    for sku, info in by_sku.items():
        if isinstance(info, tuple):
            target, info = info
            out[sku] = (target, _canonical({sku: info})[sku])
            continue
        if info is not None and "positions" in info:
            info = dict(info)
            info["positions"] = sorted(
                info["positions"],
                key=lambda p: (p["position_ref"], p["batch"] or "", p["available"], p["reserved"]),
            )
        out[sku] = info
    return out


# ── Cenário ───────────────────────────────────────────────────────────────────

SKUS = ["FILA-PAO", "FILA-CROI", "FILA-BOLO", "FILA-ESGOTADO", "FILA-PAUSADO", "FILA-SEM", "FILA-CESTA"]


@pytest.fixture
def scenario(request):
    from shopman.shop.models import Channel

    waitlist_on = getattr(request, "param", True)
    today = timezone.localdate()
    Channel.objects.update_or_create(
        ref="web",
        defaults={
            "name": "Web",
            "config": {
                "waitlist": {"enabled": waitlist_on, "horizon_days": 3},
                "stock": {
                    "allowed_positions": ["vitrine"],
                    "sells_nonconforming": False,
                    "expiry_margin_days": 1,
                },
            },
        },
    )
    listing, _ = Listing.objects.get_or_create(ref="web", defaults={"name": "Web", "is_active": True})
    shelf = {"FILA-CROI": 0, "FILA-BOLO": 3}
    products = {}
    for sku in SKUS:
        products[sku] = Product.objects.create(
            sku=sku,
            name=sku,
            base_price_q=1000,
            shelf_life_days=shelf.get(sku),
            is_published=True,
            is_sellable=sku != "FILA-PAUSADO",
        )
        ListingItem.objects.create(listing=listing, product=products[sku], price_q=1000)
    # A cesta é um bundle: 2 pães + 1 croissant.
    ProductComponent.objects.create(parent=products["FILA-CESTA"], component=products["FILA-PAO"], qty=Decimal("2"))
    ProductComponent.objects.create(parent=products["FILA-CESTA"], component=products["FILA-CROI"], qty=Decimal("1"))

    vitrine, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    deposito, _ = Position.objects.get_or_create(
        ref="deposito",
        defaults={"name": "Depósito", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )

    def quant(sku, position, qty, *, target=None, batch=""):
        return Quant.objects.create(sku=sku, position=position, target_date=target, batch=batch, _quantity=Decimal(qty))

    def hold(q, qty, status=HoldStatus.PENDING):
        Hold.objects.create(
            sku=q.sku, quant=q, quantity=Decimal(qty), target_date=q.target_date or today, status=status, metadata={}
        )

    pao = quant("FILA-PAO", vitrine, "9")
    hold(pao, "2")
    quant("FILA-PAO", deposito, "50")  # fora do recorte do canal
    pao_amanha = quant("FILA-PAO", vitrine, "6", target=today + DAY)
    hold(pao_amanha, "6", HoldStatus.CONFIRMED)  # fornada de amanhã toda reservada
    quant("FILA-PAO", vitrine, "4", target=today + 2 * DAY)

    quant("FILA-CROI", vitrine, "1")
    quant("FILA-CROI", vitrine, "12", target=today + 3 * DAY)

    Batch.objects.create(sku="FILA-BOLO", ref="BOLO-VENCE", expiry_date=today + DAY)  # cai pela margem
    Batch.objects.create(sku="FILA-BOLO", ref="BOLO-OK", expiry_date=today + 5 * DAY)
    Batch.objects.create(sku="FILA-BOLO", ref="BOLO-MARCADO", nonconformity_percent=20)
    quant("FILA-BOLO", vitrine, "3", batch="BOLO-VENCE")
    quant("FILA-BOLO", vitrine, "4", batch="BOLO-OK")
    quant("FILA-BOLO", vitrine, "5", batch="BOLO-MARCADO")
    quant("FILA-BOLO", vitrine, "2", target=today + 2 * DAY, batch="BOLO-VENCE")
    quant("FILA-BOLO", vitrine, "8", target=today + 2 * DAY, batch="BOLO-OK")

    quant("FILA-ESGOTADO", vitrine, "0")
    quant("FILA-PAUSADO", vitrine, "5")
    quant("FILA-PAUSADO", vitrine, "5", target=today + DAY)
    return today


# ── Equivalência ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("scenario", [True, False], indirect=True, ids=["fila-ligada", "fila-desligada"])
class TestSingleReadEqualsTheOldComposition:
    def test_waitlist_next_batch(self, scenario):
        new = waitlist.next_batch_availability_for_skus(SKUS, channel_ref="web")
        assert _canonical(new) == _canonical(_reference_next_batch(SKUS, "web"))

    def test_catalog_availability(self, scenario):
        new = catalog_context.availability_for_skus(SKUS, channel_ref="web")
        assert _canonical(new) == _canonical(_reference_catalog_availability(SKUS, "web"))

    def test_today_raw_is_the_plain_stockman_read_of_today(self, scenario):
        merged, today_raw = catalog_context.availability_and_today_for_skus(
            SKUS[:2],
            channel_ref="web",
            also_today=["FILA-BOLO"],
        )
        reference_today = _reference_availability_for_skus(
            [*SKUS[:2], "FILA-BOLO"],
            target_date=scenario,
            **_reference_scope_kwargs("web"),
        )
        assert set(merged) == set(SKUS[:2])
        assert _canonical(today_raw) == _canonical(reference_today)
        assert _canonical(merged) == _canonical(_reference_catalog_availability(SKUS[:2], "web"))

    def test_bundle_reusing_today_equals_its_own_read(self, scenario):
        _merged, today_raw = catalog_context.availability_and_today_for_skus(SKUS, channel_ref="web")
        reference = _reference_bundle_availability(["FILA-CESTA"], "web")

        reused = catalog_context.bundle_availability_for_skus(
            ["FILA-CESTA"],
            channel_ref="web",
            today_availability=today_raw,
        )
        alone = catalog_context.bundle_availability_for_skus(["FILA-CESTA"], channel_ref="web")

        assert reused == reference
        assert alone == reference


class TestTheWaitlistStillPicksTheRightBatch:
    def test_fully_held_batch_is_skipped_and_the_sum_is_never_promised(self, scenario):
        today = scenario
        next_batches = waitlist.next_batch_availability_for_skus(SKUS, channel_ref="web")

        assert next_batches["FILA-PAO"][0] == today + 2 * DAY
        assert next_batches["FILA-PAO"][1]["planned"] == Decimal("4")
        assert next_batches["FILA-CROI"][0] == today + 3 * DAY
        assert "FILA-PAUSADO" not in next_batches
        assert "FILA-ESGOTADO" not in next_batches


class TestOneReadPerRequest:
    def test_waitlist_dates_add_no_stock_reads(self, scenario):
        """Com a fila ligada e fornadas em três datas, o cardápio faz o mesmo
        número de consultas que uma leitura de hoje + a pergunta das datas."""
        from shopman.stockman.services.availability import availability_for_skus_on_dates

        today = scenario
        kwargs = _reference_scope_kwargs("web")
        with CaptureQueriesContext(connection) as one_read:
            availability_for_skus_on_dates(SKUS, [today, today + DAY], **kwargs)
        with CaptureQueriesContext(connection) as old_way:
            _reference_catalog_availability(SKUS, "web")
        with CaptureQueriesContext(connection) as catalog:
            catalog_context.availability_for_skus(SKUS, channel_ref="web")

        # Hoje + 3 datas candidatas eram 4 leituras inteiras.
        assert len(catalog.captured_queries) < len(old_way.captured_queries)
        stock_reads = [q for q in catalog.captured_queries if "stockman_quant" in q["sql"] and "position" in q["sql"]]
        assert len(stock_reads) == 1, [q["sql"] for q in stock_reads]
        assert len(one_read.captured_queries) > 0
