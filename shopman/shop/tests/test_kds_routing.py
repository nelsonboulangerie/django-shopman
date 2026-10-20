from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_dispatch_prefers_collection_specific_station_before_picking_catchall():
    """O feito na hora vai à estação de preparo da coleção dele, não à separação."""
    from decimal import Decimal

    from shopman.craftsman.models import ProductionMode, Recipe
    from shopman.offerman.models import Collection, CollectionItem, Product
    from shopman.orderman.models import Order, OrderItem

    from shopman.backstage.models import KDSInstance
    from shopman.shop.models import Channel
    from shopman.shop.services.kds import dispatch

    Channel.objects.create(ref="web", name="Web")

    cafes = Collection.objects.create(ref="kdsroute-cafes", name="KDSRoute Cafés")
    product = Product.objects.create(
        sku="CAPPUCCINO",
        name="Cappuccino",
        base_price_q=1200,
    )
    CollectionItem.objects.create(collection=cafes, product=product, is_primary=True)
    Recipe.objects.create(
        ref="cappuccino", name="Cappuccino", output_sku="CAPPUCCINO", batch_size=Decimal("1"),
        production_mode=ProductionMode.MADE_TO_ORDER,
    )

    cafes_kds = KDSInstance.objects.create(
        ref="kdsroute-cafes-station",
        name="KDSRoute Cafés",
        type="prep",
        target_time_minutes=3,
    )
    cafes_kds.collections.add(cafes)
    KDSInstance.objects.create(
        ref="kdsroute-encomendas",
        name="KDSRoute Encomendas",
        type="picking",
        target_time_minutes=5,
    )

    order = Order.objects.create(
        ref="ORD-KDS-CAFES-001",
        channel_ref="web",
        session_key="sk-kds-cafes-001",
        status=Order.Status.PREPARING,
        total_q=1200,
    )
    OrderItem.objects.create(
        order=order,
        line_id="1",
        sku="CAPPUCCINO",
        name="Cappuccino",
        qty="1",
        unit_price_q=1200,
        line_total_q=1200,
    )

    tickets = dispatch(order)

    assert len(tickets) == 1
    assert tickets[0].kds_instance.ref == "kdsroute-cafes-station"
    assert tickets[0].items == [
        {
            "sku": "CAPPUCCINO",
            "name": "Cappuccino",
            "qty": 1,
            "notes": "",
            "line_id": "1",
        },
    ]


@pytest.mark.django_db
def test_fire_lines_is_progressive_and_idempotent_per_line():
    """Progressive course-by-course firing — only the unfired delta each time.

    Uses a catch-all picking station (no collections) to keep routing trivial
    and Collection-free.
    """
    from shopman.orderman.models import Order, OrderItem

    from shopman.backstage.models import KDSInstance, KDSTicket
    from shopman.shop.adapters import kds as kds_adapter
    from shopman.shop.models import Channel
    from shopman.shop.services.kds import dispatch, fire_lines

    Channel.objects.create(ref="web", name="Web")
    KDSInstance.objects.create(ref="cozinha", name="Cozinha", type="picking")

    session_key = "sk-progressive-1"
    order = Order.objects.create(
        ref="ORD-PROG-001", channel_ref="web", session_key=session_key,
        status=Order.Status.NEW, total_q=3000,
    )
    for line_id, sku in (("1", "PAO"), ("2", "CAFE"), ("3", "BOLO")):
        OrderItem.objects.create(
            order=order, line_id=line_id, sku=sku, name=sku,
            qty="1", unit_price_q=1000, line_total_q=1000,
        )
    lines = [
        {"line_id": "1", "sku": "PAO", "name": "Pão", "qty": 1, "notes": "", "meta": {}},
        {"line_id": "2", "sku": "CAFE", "name": "Café", "qty": 1, "notes": "", "meta": {}},
        {"line_id": "3", "sku": "BOLO", "name": "Bolo", "qty": 1, "notes": "", "meta": {}},
    ]

    # Fire course 1 only → one ticket carrying line 1.
    first = fire_lines(session_key=session_key, lines=lines[:1])
    assert len(first) == 1
    assert {it["line_id"] for it in first[0].items} == {"1"}

    # Re-fire course 1 → no-op (already fired).
    assert fire_lines(session_key=session_key, lines=lines[:1]) == []

    # Fire courses 1+2 → only the line-2 delta is sent.
    second = fire_lines(session_key=session_key, lines=lines[:2])
    assert len(second) == 1
    assert {it["line_id"] for it in second[0].items} == {"2"}

    # Commit reconciliation: dispatch(order) fires only the still-unfired line 3.
    remainder = dispatch(order)
    assert len(remainder) == 1
    assert {it["line_id"] for it in remainder[0].items} == {"3"}

    # Everything fired → dispatch is now a no-op, ledger holds all three.
    assert dispatch(order) == []
    assert kds_adapter.fired_line_ids_for_session(session_key) == {"1", "2", "3"}
    assert KDSTicket.objects.filter(session_key=session_key).count() == 3


@pytest.mark.django_db
def test_cancelled_line_may_refire():
    """A cancelled ticket's line is absent from the ledger → it can re-fire."""
    from shopman.orderman.models import Order, OrderItem

    from shopman.backstage.models import KDSInstance
    from shopman.shop.models import Channel
    from shopman.shop.services.kds import dispatch, fire_lines

    Channel.objects.create(ref="web", name="Web")
    KDSInstance.objects.create(ref="cozinha", name="Cozinha", type="picking")

    session_key = "sk-refire-1"
    order = Order.objects.create(
        ref="ORD-REFIRE-001", channel_ref="web", session_key=session_key,
        status=Order.Status.NEW, total_q=1000,
    )
    OrderItem.objects.create(
        order=order, line_id="1", sku="PAO", name="Pão",
        qty="1", unit_price_q=1000, line_total_q=1000,
    )

    fired = dispatch(order)
    assert len(fired) == 1
    fired[0].status = "cancelled"
    fired[0].save(update_fields=["status"])

    # Same line re-fires because the cancelled ticket is out of the ledger.
    refired = fire_lines(
        session_key=session_key,
        lines=[{"line_id": "1", "sku": "PAO", "name": "Pão", "qty": 1, "notes": "", "meta": {}}],
    )
    assert len(refired) == 1
    assert {it["line_id"] for it in refired[0].items} == {"1"}


@pytest.mark.django_db
def test_empty_session_key_never_fires():
    """An empty session_key is invalid (a real source always has one): firing it
    would create an unresolvable orphan ticket that collides with every other
    empty-key ticket. fire_lines must refuse rather than create it."""
    from shopman.backstage.models import KDSInstance, KDSTicket
    from shopman.shop.services.kds import fire_lines

    KDSInstance.objects.create(ref="cozinha", name="Cozinha", type="picking")

    created = fire_lines(
        session_key="",
        lines=[{"line_id": "1", "sku": "PAO", "name": "Pão", "qty": 1, "notes": "", "meta": {}}],
    )
    assert created == []
    assert KDSTicket.objects.count() == 0


@pytest.mark.django_db
def test_empty_session_key_ticket_never_resolves_to_a_random_order():
    """A ticket with an empty session_key must not collapse onto an arbitrary
    ``filter(session_key="").first()`` order — the root cause of tickets showing
    under the wrong order_ref. _resolve_ticket_source returns None instead."""
    from shopman.orderman.models import Order

    from shopman.backstage.models import KDSInstance, KDSTicket
    from shopman.backstage.projections.kds import _resolve_ticket_source

    # An order that DOES carry the empty key (artificial/legacy data).
    Order.objects.create(
        ref="ORD-EMPTY-001", channel_ref="web", session_key="",
        status=Order.Status.PREPARING, total_q=1000,
    )
    instance = KDSInstance.objects.create(ref="cozinha", name="Cozinha", type="picking")
    ticket = KDSTicket.objects.create(session_key="", kds_instance=instance, items=[])

    assert _resolve_ticket_source(ticket) is None



def _station_setup():
    """Cafés (preparo, coleção bebidas) e Encomendas (separação, sem coleção)."""
    from shopman.offerman.models import Collection

    from shopman.backstage.models import KDSInstance

    bebidas = Collection.objects.create(ref="modo-bebidas", name="Bebidas")
    doces = Collection.objects.create(ref="modo-doces", name="Doces")
    cafes = KDSInstance.objects.create(ref="modo-cafes", name="Cafés", type="prep")
    cafes.collections.add(bebidas)
    KDSInstance.objects.create(ref="modo-encomendas", name="Encomendas", type="picking")
    return bebidas, doces


def _product(sku: str, collection, *, mode: str | None = None):
    from decimal import Decimal

    from shopman.craftsman.models import Recipe
    from shopman.offerman.models import CollectionItem, Product

    product = Product.objects.create(sku=sku, name=sku, base_price_q=500)
    CollectionItem.objects.create(collection=collection, product=product, is_primary=True)
    if mode:
        Recipe.objects.create(ref=sku.lower(), name=sku, output_sku=sku, batch_size=Decimal("1"), production_mode=mode)
    return product


def _fire(skus: list[str], *, prep_only: bool) -> dict[str, list[str]]:
    from shopman.shop.adapters import get_adapter
    from shopman.shop.adapters import kds as kds_adapter
    from shopman.shop.services.kds import _fire_lines_locked

    lines = [{"line_id": f"L{i}", "sku": sku, "name": sku, "qty": 1, "notes": "", "meta": {}} for i, sku in enumerate(skus)]
    tickets = _fire_lines_locked(
        session_key=f"modo-{prep_only}", lines=lines, get_adapter=get_adapter, kds_adapter=kds_adapter, prep_only=prep_only,
    )
    return {ticket.kds_instance.name: sorted(item["sku"] for item in ticket.items) for ticket in tickets}


@pytest.mark.django_db
def test_revenda_na_colecao_da_estacao_de_preparo_e_separacao():
    """Água e soda na coleção de Cafés, sem ficha: revenda nunca vai ao preparo."""
    from shopman.craftsman.models import ProductionMode

    bebidas, _doces = _station_setup()
    _product("ESPRESSO", bebidas, mode=ProductionMode.MADE_TO_ORDER)
    _product("AGUA", bebidas)

    assert _fire(["ESPRESSO", "AGUA"], prep_only=False) == {"Cafés": ["ESPRESSO"], "Encomendas": ["AGUA"]}


@pytest.mark.django_db
def test_balcao_presencial_so_manda_o_feito_na_hora():
    """O defeito de 20/10/2026: no balcão o café sumia e o pão pronto tocava o KDS."""
    from shopman.craftsman.models import ProductionMode

    bebidas, doces = _station_setup()
    _product("ESPRESSO", bebidas, mode=ProductionMode.MADE_TO_ORDER)
    _product("PAO", doces, mode=ProductionMode.BATCH)
    _product("AGUA", bebidas)

    assert _fire(["ESPRESSO", "PAO", "AGUA"], prep_only=True) == {"Cafés": ["ESPRESSO"]}


@pytest.mark.django_db
def test_feito_na_hora_sem_estacao_de_preparo_alerta_e_nao_vira_separacao():
    from shopman.craftsman.models import ProductionMode

    from shopman.backstage.models import OperatorAlert

    _bebidas, doces = _station_setup()
    _product("PAIN-PERDU", doces, mode=ProductionMode.MADE_TO_ORDER)

    assert _fire(["PAIN-PERDU"], prep_only=False) == {}
    alert = OperatorAlert.objects.get(type="kds_unrouted_item")
    assert "PAIN-PERDU" in alert.message


@pytest.mark.django_db
def test_em_lote_nunca_cai_na_estacao_de_preparo_da_colecao():
    """O fallback antigo casava item de um tipo com estação de outro pela coleção."""
    from shopman.craftsman.models import ProductionMode

    bebidas, _doces = _station_setup()
    _product("CHA-GELADO-LOTE", bebidas, mode=ProductionMode.BATCH)

    assert _fire(["CHA-GELADO-LOTE"], prep_only=False) == {"Encomendas": ["CHA-GELADO-LOTE"]}
