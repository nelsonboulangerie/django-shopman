"""V6-BI: o que a v4 do "Sobrou ou faltou?" e das Vendas mostra a mais.

- a resposta agrupada por coleção e turno ("Faltou nos folhados de manhã");
- o "Comparar com" escolhível (típico de 4 e de 8 semanas, ou o dia anterior só);
- o que aconteceu depois que acabou: canais fora do ar (``ShelfOutage``) e os
  "Me avise" do site; o lote que o plano tinha e não fechou; os pedidos do dia;
- "Levar ao plano": a nota do porquê ao lado da sugestão do Planejamento;
- Vendas: recorte por canal em todos os quadros, nome do canal no lugar da chave
  crua, e a base "mesmo período do ano passado";
- o custo vivo da ficha técnica (ADR-023) que dá o "R$ de custo" da sobra;
- o Histórico do Gestor recortado por produto (o "Abrir os N pedidos").
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder
from shopman.offerman.models import Collection, CollectionItem, Product
from shopman.orderman.models import Order, OrderItem
from shopman.stockman import Hold, HoldStatus, Move, Position, Quant
from shopman.stockman.models import Batch

from shopman.backstage.models import DayClosing, PlanCarryNote, ShelfOutage
from shopman.backstage.projections.bi_over_short import build_bi_over_short
from shopman.backstage.projections.bi_production import build_bi_production
from shopman.backstage.projections.bi_sales import build_bi_sales

pytestmark = pytest.mark.django_db

EVERY_DAY = {
    day: {"open": "07:00", "close": "18:00"}
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
}


@pytest.fixture
def shop(db):
    from shopman.shop.models import Shop

    shop, _ = Shop.objects.get_or_create(name="Loja B.I.")
    shop.opening_hours = EVERY_DAY
    shop.save()
    return shop


@pytest.fixture
def day() -> date:
    return timezone.localdate() - timedelta(days=1)


def _recipe(sku: str, name: str, collection: Collection | None = None) -> Recipe:
    product, _ = Product.objects.get_or_create(sku=sku, defaults={"name": name, "base_price_q": 1000})
    if collection is not None:
        CollectionItem.objects.get_or_create(collection=collection, product=product, defaults={"is_primary": True})
    return Recipe.objects.create(ref=f"{sku.lower()}-v1", name=name, output_sku=sku, batch_size=Decimal("10"))


def _lot(recipe: Recipe, day: date, qty: int, at: time = time(6, 30), status=WorkOrder.Status.FINISHED) -> WorkOrder:
    finished = status == WorkOrder.Status.FINISHED
    wo = WorkOrder.objects.create(
        recipe=recipe,
        output_sku=recipe.output_sku,
        quantity=Decimal(qty),
        finished=Decimal(qty) if finished else None,
        status=status,
        target_date=day,
    )
    if finished:
        WorkOrder.objects.filter(pk=wo.pk).update(finished_at=timezone.make_aware(datetime.combine(day, at)))
    return wo


_seq = iter(range(1, 100_000))


def _sale(day: date, at: time, sku: str, qty: int, channel: str = "pdv") -> Order:
    order = Order.objects.create(
        ref=f"V6-{next(_seq)}", channel_ref=channel, status=Order.Status.COMPLETED, total_q=qty * 1000
    )
    OrderItem.objects.create(
        order=order, line_id="l1", sku=sku, name=sku, qty=Decimal(qty), unit_price_q=1000, line_total_q=qty * 1000
    )
    Order.objects.filter(pk=order.pk).update(created_at=timezone.make_aware(datetime.combine(day, at)))
    return order


def _row(report, sku):
    return next(row for row in report.rows if row.sku == sku)


# ── A resposta agrupada ──────────────────────────────────────────────────────


def test_answer_groups_a_collection_and_names_the_shift(shop, day):
    folhados = Collection.objects.create(ref="folhados-v6", name="Folhados")
    croissant = _recipe("CRO6", "Croissant", folhados)
    pain = _recipe("PCH6", "Pain au Chocolat", folhados)
    baguete = _recipe("BGT6", "Baguete")
    _lot(croissant, day, 10)
    _lot(pain, day, 10)
    _lot(baguete, day, 40)
    _sale(day, time(9, 0), "CRO6", 10)  # acabou às 09:00 (manhã)
    _sale(day, time(10, 0), "PCH6", 10)  # acabou às 10:00 (manhã)
    _sale(day, time(13, 0), "BGT6", 20)  # última venda às 13:00: parou à tarde

    report = build_bi_over_short(day=day)

    assert [(g.label, g.kind, g.shift, g.count) for g in report.answer_short] == [
        ("Folhados", "collection", "morning", 2)
    ]
    assert [(g.label, g.kind, g.shift) for g in report.answer_over] == [("Baguete", "product", "afternoon")]


def test_leftover_selling_until_close_has_no_shift(shop, day):
    baguete = _recipe("BGT7", "Baguete")
    _lot(baguete, day, 40)
    _sale(day, time(17, 30), "BGT7", 20)

    assert _row(build_bi_over_short(day=day), "BGT7").shift == ""


# ── Comparar com ─────────────────────────────────────────────────────────────


def test_compare_base_changes_the_days(shop, day):
    assert len(build_bi_over_short(day=day, compare="last").compare_days) == 1
    assert len(build_bi_over_short(day=day, compare="typical8").compare_days) == 8
    report = build_bi_over_short(day=day, compare="inventada")
    assert report.compare == "typical"
    assert len(report.compare_days) == 4


def test_endpoint_reads_compare_from_the_url(client, shop, day):
    viewer = User.objects.create_user("bi-v6", password="pw", is_staff=True)
    viewer.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get_for_model(DayClosing), codename="view_bi")
    )
    client.force_login(viewer)
    response = client.get(reverse("api-backstage-bi-over-short"), {"day": day.isoformat(), "compare": "last"})
    assert response.json()["bi"]["compare"] == "last"


# ── Depois que acabou, o plano e os pedidos ──────────────────────────────────


def test_channels_off_the_air_are_grouped_by_minute(shop, day):
    from shopman.shop.models import Channel

    Channel.objects.update_or_create(ref="pdv", defaults={"name": "PDV", "is_active": True})
    Channel.objects.update_or_create(
        ref="ifood", defaults={"name": "iFood", "is_active": True, "display_order": 3}
    )
    croissant = _recipe("CRO8", "Croissant")
    _lot(croissant, day, 10)
    _sale(day, time(9, 0), "CRO8", 10)
    at = timezone.make_aware(datetime.combine(day, time(10, 40)))
    ShelfOutage.objects.create(sku="CRO8", channel_ref="ifood", reason="sold_out", started_at=at)
    ShelfOutage.objects.create(sku="CRO8", channel_ref="pdv", reason="sold_out", started_at=at)

    row = _row(build_bi_over_short(day=day), "CRO8")

    assert len(row.unavailable) == 1
    assert row.unavailable[0].at == "10:40"
    assert set(row.unavailable[0].channels) == {"PDV", "iFood"}
    # O PDV não sai do ar sozinho: o grupo não é automático.
    assert row.unavailable[0].automatic is False


def test_the_missing_lot_and_the_orders_of_the_day(shop, day):
    croissant = _recipe("CRO9", "Croissant")
    _lot(croissant, day, 20)
    _lot(croissant, day, 24, status=WorkOrder.Status.PLANNED)
    _lot(croissant, day, 99, status=WorkOrder.Status.VOID)
    _sale(day, time(9, 0), "CRO9", 12)
    _sale(day, time(9, 30), "CRO9", 8)

    row = _row(build_bi_over_short(day=day), "CRO9")

    assert row.planned_lots == 2  # o cancelado não conta
    assert row.planned == "44"
    assert len(row.lots) == 1
    assert row.orders == 2


def test_carry_to_plan_writes_the_why_and_the_plan_reads_it(client, shop, day):
    croissant = _recipe("CRO10", "Croissant")
    _lot(croissant, day, 20)
    _sale(day, time(9, 0), "CRO10", 20)
    manager = User.objects.create_superuser("bi-v6-carry", password="pw")
    client.force_login(manager)

    response = client.post(
        reverse("api-backstage-bi-over-short-carry"), {"day": day.isoformat()}, content_type="application/json"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["carried"] == 1
    note = PlanCarryNote.objects.get(sku="CRO10")
    assert note.verdict == "short"
    assert note.source_day == day
    assert note.facts["soldout_at"] == "09:00"
    assert note.target_date.isoformat() == body["plan_day"]

    # Levar de novo não repete a frase.
    client.post(reverse("api-backstage-bi-over-short-carry"), {"day": day.isoformat()}, content_type="application/json")
    assert PlanCarryNote.objects.filter(sku="CRO10").count() == 1

    from shopman.backstage.projections.production import _plan_carry_notes

    notes = _plan_carry_notes(note.target_date)
    assert notes["CRO10"][0].soldout_at == "09:00"


def test_carry_to_plan_needs_whoever_plans_production(client, shop, day):
    viewer = User.objects.create_user("bi-v6-viewer", password="pw", is_staff=True)
    viewer.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get_for_model(DayClosing), codename="view_bi")
    )
    client.force_login(viewer)
    response = client.post(
        reverse("api-backstage-bi-over-short-carry"), {"day": day.isoformat()}, content_type="application/json"
    )
    assert response.status_code == 403
    assert not PlanCarryNote.objects.exists()


# ── Vendas por canal ─────────────────────────────────────────────────────────


def test_sales_channel_filter_cuts_every_number_and_names_the_channel(shop, day):
    from shopman.shop.models import Channel

    Channel.objects.update_or_create(ref="pdv", defaults={"name": "PDV", "is_active": True})
    Channel.objects.update_or_create(ref="whatsapp", defaults={"name": "WhatsApp", "is_active": True})
    _recipe("PAO1", "Pão")
    _sale(day, time(9, 0), "PAO1", 3, channel="pdv")
    _sale(day, time(9, 0), "PAO1", 4, channel="pdv")
    _sale(day, time(10, 0), "PAO1", 5, channel="whatsapp")

    everything = build_bi_sales(date_from=day, date_to=day)
    assert everything.orders_total == 3
    assert {(row.channel_ref, row.name, row.kind) for row in everything.by_channel} == {
        ("pdv", "PDV", "counter"),
        ("whatsapp", "WhatsApp", "whatsapp"),
    }
    assert [option.ref for option in everything.channels] == ["pdv", "whatsapp"]

    whatsapp = build_bi_sales(date_from=day, date_to=day, channel="whatsapp")
    assert whatsapp.channel == "whatsapp"
    assert whatsapp.orders_total == 1
    assert whatsapp.revenue_total_q == 5000
    assert [row.qty for row in whatsapp.top_skus] == ["5"]
    # Os chips continuam oferecendo todos os canais da janela.
    assert len(whatsapp.channels) == 2

    unknown = build_bi_sales(date_from=day, date_to=day, channel="nao-existe")
    assert unknown.channel == ""
    assert unknown.orders_total == 3


def test_sales_compare_with_the_same_period_last_year(shop, day):
    report = build_bi_sales(date_from=day, date_to=day, compare="year")
    assert report.compare == "year"
    assert report.previous.date_from == day.replace(year=day.year - 1).isoformat()
    assert build_bi_sales(date_from=day, date_to=day).previous.date_from == (day - timedelta(days=1)).isoformat()


# ── Custo vivo (ADR-023) ─────────────────────────────────────────────────────


def test_live_cost_is_recipe_times_preferred_material_cost(shop):
    from shopman.buyman.models import Material, Supplier, SupplierMaterialCost

    from shopman.shop.adapters.cost import RecipeCostBackend

    supplier = Supplier.objects.create(ref="moinho-v6", name="Moinho")
    flour = Material.objects.create(sku="FARINHA-V6", name="Farinha", unit="g")
    butter = Material.objects.create(sku="MANTEIGA-V6", name="Manteiga", unit="g")
    recipe = _recipe("CUSTO1", "Croissant")  # rende 10
    RecipeItem.objects.create(recipe=recipe, input_sku="FARINHA-V6", quantity=Decimal("1000"), unit="g")
    RecipeItem.objects.create(recipe=recipe, input_sku="MANTEIGA-V6", quantity=Decimal("0.5"), unit="kg")
    backend = RecipeCostBackend()

    # Sem custo de algum insumo: None, nunca zero.
    SupplierMaterialCost.objects.create(supplier=supplier, material=flour, cost_q=1000, is_preferred=True)
    assert backend.get_cost("CUSTO1") is None

    # Insumo em g sem embalagem tem custo por kg (CMP-07): farinha R$ 10/kg × 1000 g
    # = 1000; manteiga R$ 60/kg × 500 g = 3000; ÷ 10.
    SupplierMaterialCost.objects.create(supplier=supplier, material=butter, cost_q=6000, is_preferred=True)
    assert backend.get_cost("CUSTO1") == 400
    assert backend.get_cost("SEM-FICHA") is None


# ── Histórico do Gestor por produto ──────────────────────────────────────────


def test_order_history_filters_by_product_including_the_counter(client, shop, day):
    manager = User.objects.create_superuser("bi-v6-history", password="pw")
    client.force_login(manager)
    _recipe("HIST1", "Croissant")
    counter = _sale(day, time(9, 0), "HIST1", 2)
    Order.objects.filter(pk=counter.pk).update(
        data={"origin_channel": "pos", "pos": {"sales_mode": "counter"}},
        completed_at=timezone.make_aware(datetime.combine(day, time(9, 1))),
    )
    other = _sale(day, time(9, 5), "OUTRO", 1)
    Order.objects.filter(pk=other.pk).update(completed_at=timezone.make_aware(datetime.combine(day, time(9, 6))))

    response = client.get(
        reverse("api-backstage-order-history"),
        {"date_from": day.isoformat(), "date_to": day.isoformat(), "sku": "HIST1"},
    )

    assert response.status_code == 200
    history = response.json()["history"]
    assert [row["ref"] for row in history["items"]] == [counter.ref]
    assert history["sku"] == "HIST1"
    assert history["sku_name"] == "Croissant"



def _finished_stock(wo, batch):
    position, _ = Position.objects.get_or_create(ref="bi-batches", defaults={"name": "Vitrine"})
    quant, _ = Quant.objects.get_or_create(sku=wo.output_sku, batch=batch, position=position)
    Move.objects.create(
        quant=quant,
        delta=wo.finished,
        kind=Move.Kind.MAKE,
        reason=f"Recebido de produção: Finalização do lote: {wo.ref}",
    )
    return quant


def _attach_sale_holds(order, day, allocations):
    entries = []
    for quant, qty in allocations:
        hold = Hold.objects.create(
            sku=quant.sku,
            quant=quant,
            quantity=qty,
            target_date=day,
            status=HoldStatus.FULFILLED,
            metadata={"reference": f"order:{order.ref}"},
        )
        Move.objects.create(quant=quant, delta=-qty, kind=Move.Kind.SELL, reason=f"Entrega hold:{hold.pk}")
        entries.append({"sku": quant.sku, "hold_id": f"hold:{hold.pk}", "qty": str(qty)})
    Order.objects.filter(pk=order.pk).update(data={"hold_ids": entries})


def _lot_batch(quant, expiry):
    Batch.objects.create(ref=quant.batch, sku=quant.sku, expiry_date=expiry)


def _freeze_cost(wo, day, total_q, gaps=()):
    WorkOrder.objects.filter(pk=wo.pk).update(meta={"cost_snapshot": {
        "frozen_at": datetime.combine(day, time(6, 30), tzinfo=timezone.get_current_timezone()).isoformat(),
        "total_q": total_q,
        "unit_cost_q": total_q // int(wo.finished) if total_q is not None else None,
        "output_quantity": str(wo.finished),
        "lines": [],
        "gaps": list(gaps),
    }})


def test_batch_margin_is_the_whole_batch_once_the_lot_expires(day):
    recipe = _recipe("BIMARGIN", "Pão da casa")
    complete = _lot(recipe, day, 10)
    incomplete = _lot(recipe, day, 10)
    old = _lot(recipe, day - timedelta(days=1), 10)
    _freeze_cost(complete, day, 1800)
    _freeze_cost(incomplete, day, None, ["Farinha sem preço de compra."])
    first_stock = _finished_stock(complete, "bi-margin-first")
    second_stock = _finished_stock(incomplete, "bi-margin-second")
    _lot_batch(first_stock, day)
    _lot_batch(second_stock, day)
    sale = _sale(day, time(9), recipe.output_sku, 5)
    OrderItem.objects.filter(order=sale).update(line_total_q=4001)
    _attach_sale_holds(sale, day, [(first_stock, 3), (second_stock, 2)])
    cancelled = _sale(day, time(10), recipe.output_sku, 1)
    _attach_sale_holds(cancelled, day, [(first_stock, 1)])
    Order.objects.filter(pk=cancelled.pk).update(status=Order.Status.CANCELLED)
    _sale(day, time(11), recipe.output_sku, 4)

    report = build_bi_production(date_from=old.target_date, date_to=day)
    rows = {row.ref: row for row in report.batch_margins}
    first = rows[complete.ref]
    # Venceu ontem com 7 sobrando: a margem é a da fornada inteira, sobra incluída.
    assert (first.lot_status, first.revenue_q, first.total_q, first.margin_q) == ("closed", 2401, 1800, 601)
    assert (first.traced_quantity, first.output_quantity, first.sells_until) == ("3", "10", day.isoformat())
    second = rows[incomplete.ref]
    assert (second.cost_status, second.revenue_q, second.total_q, second.margin_q) == (
        "incomplete", 1600, None, None,
    )
    assert second.gaps == ("Farinha sem preço de compra.",)
    assert (rows[old.ref].cost_status, rows[old.ref].lot_status, rows[old.ref].margin_q) == (
        "missing", "untraceable", None,
    )


def test_batch_margin_waits_while_the_lot_is_on_sale(day):
    recipe = _recipe("BIOPEN", "Bolo")
    wo = _lot(recipe, day, 10)
    _freeze_cost(wo, day, 1800)
    quant = _finished_stock(wo, "bi-margin-open")
    today = timezone.localdate()
    _lot_batch(quant, today)  # vale até hoje: ainda em venda
    sale = _sale(day, time(9), recipe.output_sku, 3)
    _attach_sale_holds(sale, day, [(quant, 3)])

    row = build_bi_production(date_from=day, date_to=day).batch_margins[0]
    assert (row.lot_status, row.sells_until, row.revenue_q, row.margin_q) == ("open", today.isoformat(), 3000, None)


def test_batch_margin_counts_the_sale_of_the_next_day(day):
    recipe = _recipe("BINEXT", "Pão do dia seguinte")
    wo = _lot(recipe, day, 10)
    _freeze_cost(wo, day, 1800)
    quant = _finished_stock(wo, "bi-margin-next")
    today = timezone.localdate()
    _lot_batch(quant, today)
    sale = _sale(today, time(9), recipe.output_sku, 10)
    _attach_sale_holds(sale, today, [(quant, 10)])

    # Esgotou hoje, na validade: encerrou, e a venda de hoje entra na fornada de ontem.
    row = build_bi_production(date_from=day, date_to=day).batch_margins[0]
    assert (row.lot_status, row.traced_quantity, row.revenue_q, row.margin_q) == ("closed", "10", 10000, 8200)


def test_expired_lot_without_sales_is_the_whole_cost_lost(day):
    recipe = _recipe("BILOST", "Brioche")
    wo = _lot(recipe, day, 10)
    _freeze_cost(wo, day, 1800)
    _lot_batch(_finished_stock(wo, "bi-margin-lost"), day)

    row = build_bi_production(date_from=day, date_to=day).batch_margins[0]
    assert (row.lot_status, row.revenue_q, row.margin_q) == ("closed", 0, -1800)


def test_batch_margin_does_not_attribute_sales_from_a_shared_daily_batch(day):
    recipe = _recipe("BISHARED", "Baguete")
    first = _lot(recipe, day - timedelta(days=1), 5)
    second = _lot(recipe, day, 5)
    quant = _finished_stock(first, "bi-margin-shared")
    _finished_stock(second, quant.batch)
    _freeze_cost(second, day, 900)
    sale = _sale(day, time(9), recipe.output_sku, 2)
    _attach_sale_holds(sale, day, [(quant, 2)])

    rows = build_bi_production(date_from=day, date_to=day).batch_margins
    assert [(row.ref, row.revenue_q) for row in rows] == [(second.ref, 0)]
    # Lote que o estoque não separa: sem margem, nunca o custo inteiro como prejuízo.
    assert (rows[0].lot_status, rows[0].margin_q) == ("untraceable", None)
