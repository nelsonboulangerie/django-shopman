"""Production dashboard, KDS and alert surface tests."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrder

from shopman.backstage.models import OperatorAlert
from shopman.backstage.projections.production import (
    build_production_board,
    build_production_dashboard,
    build_production_kds,
    build_production_reports,
    build_work_order_card,
    resolve_production_access,
)
from shopman.shop.handlers.production_alerts import (
    check_late_started_orders,
    create_stock_short_alert,
    maybe_create_low_yield_alert,
)


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser("admin", "admin@test.com", "pass")


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        ref="prod-op-v1",
        name="Produto Operacional",
        output_sku="PROD-OP",
        batch_size=Decimal("10"),
        steps=["Mistura", "Forno"],
        meta={"max_started_minutes": 30, "capacity_per_day": 100},
    )


@pytest.mark.django_db
def test_production_dashboard_projection_summarizes_day_and_late_orders(recipe):
    craft.plan(recipe, 20, date=date.today(), position_ref="forno")
    started = craft.plan(recipe, 30, date=date.today(), position_ref="forno")
    craft.start(started, quantity=30, position_ref="forno", expected_rev=0)
    WorkOrder.objects.filter(pk=started.pk).update(started_at=timezone.now() - timedelta(minutes=45))
    finished = craft.plan(recipe, 40, date=date.today(), position_ref="forno")
    craft.finish(finished, finished=36, actor="test")

    dashboard = build_production_dashboard(selected_date=date.today(), position_ref="forno")

    assert dashboard.planned_orders == 1
    assert dashboard.started_orders == 1
    assert dashboard.finished_orders == 1
    assert dashboard.planned_qty == "90"
    assert dashboard.started_qty == "70"
    assert dashboard.finished_qty == "36"
    assert dashboard.average_yield_rate == "90%"
    assert dashboard.capacity_percent == 90
    assert dashboard.late_orders[0].ref == started.ref
    assert dashboard.late_orders[0].recipe_name == "Produto Operacional"


@pytest.mark.django_db
def test_kds_card_exposes_linked_order_refs(recipe, superuser):
    """WP-PE5: o chão mostra quantos pedidos aguardam o lote (aviso no estorno)."""
    wo = craft.plan(recipe, 10, date=date.today())
    craft.start(wo, quantity=10)
    wo.refresh_from_db()
    wo.meta = {**(wo.meta or {}), "committed_order_refs": ["ORD-1", "ORD-2"]}
    wo.save(update_fields=["meta"])

    kds = build_production_kds(selected_date=date.today())
    card = next(c for c in kds.cards if c.ref == wo.ref)
    assert card.order_refs == ("ORD-1", "ORD-2")


@pytest.mark.django_db
def test_production_kds_projection_returns_started_cards_only(recipe, superuser):
    planned = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    started = craft.plan(recipe, 12, date=date.today(), position_ref="forno", operator_ref="user:ana")
    craft.start(started, quantity=11, position_ref="forno", expected_rev=0)
    craft.finish(craft.plan(recipe, 8, date=date.today(), position_ref="forno"), finished=7, actor="test")

    access = resolve_production_access(superuser)
    kds = build_production_kds(selected_date=date.today(), position_ref="forno", access=access)

    assert kds.total_count == 1
    assert kds.cards[0].ref == started.ref
    assert kds.cards[0].started_qty == "11"
    assert kds.cards[0].current_step == "Mistura"
    assert kds.cards[0].can_finish is True
    assert planned.ref not in [card.ref for card in kds.cards]


@pytest.mark.django_db
def test_work_order_card_preserves_decimal_quantities(recipe):
    work_order = craft.plan(recipe, Decimal("1.5"), date=date.today(), position_ref="forno")
    craft.start(work_order, quantity=Decimal("1.25"), position_ref="forno", expected_rev=0)
    craft.finish(work_order, finished=Decimal("1.125"), actor="test")

    card = build_work_order_card(work_order.ref)

    assert card.planned_qty == "1.5"
    assert card.started_qty == "1.25"
    assert card.finished_qty == "1.125"
    assert card.loss == "0.125"


@pytest.mark.django_db
def test_low_yield_alert_created_once(recipe):
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    craft.start(work_order, quantity=10, position_ref="forno", expected_rev=0)
    craft.finish(work_order, finished=7, actor="test")

    OperatorAlert.objects.all().delete()
    assert maybe_create_low_yield_alert(work_order) is True
    assert maybe_create_low_yield_alert(work_order) is False
    alert = OperatorAlert.objects.get(type="production_low_yield")
    assert alert.order_ref == work_order.ref
    assert "yield de 70%" in alert.message


@pytest.mark.django_db
def test_late_started_alert_created_once(recipe):
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    craft.start(work_order, quantity=10, position_ref="forno", expected_rev=0)
    WorkOrder.objects.filter(pk=work_order.pk).update(started_at=timezone.now() - timedelta(minutes=45))

    assert check_late_started_orders(selected_date=date.today()) == 1
    assert check_late_started_orders(selected_date=date.today()) == 0
    alert = OperatorAlert.objects.get(type="production_late")
    assert alert.order_ref == work_order.ref


@pytest.mark.django_db
def test_stock_short_alert_created_once(recipe):
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")

    create_stock_short_alert(
        work_order_ref=work_order.ref,
        output_sku=work_order.output_sku,
        error="estoque insuficiente",
    )
    create_stock_short_alert(
        work_order_ref=work_order.ref,
        output_sku=work_order.output_sku,
        error="estoque insuficiente",
    )

    assert OperatorAlert.objects.filter(type="production_stock_short").count() == 1


# ── Nome do produto nas listas da Produção ─────────────────────────────────
# A bancada lê NOME; o SKU é o código que confirma qual é. As listas traziam o
# `output_sku` nas duas linhas porque `recipe_name` era preenchido com o SKU —
# "SKU / SKU". O nome vem da FICHA (`Recipe.name`), não do catálogo: a maior
# parte do quadro são massas e pré-preparos, que não têm produto vendável.


@pytest.mark.django_db
def test_linhas_da_producao_trazem_o_nome_da_ficha_e_o_sku(recipe):
    craft.plan(recipe, 10, date=date.today(), position_ref="forno")

    board = build_production_board(selected_date=date.today())
    row = next(r for r in board.matrix_rows if r.output_sku == "PROD-OP")

    assert row.recipe_name == "Produto Operacional"
    assert row.output_sku == "PROD-OP"
    assert row.planned_orders[0].recipe_name == "Produto Operacional"
    assert row.planned_orders[0].output_sku == "PROD-OP"
    assert "Produto Operacional" in {option.name for option in board.recipes}
    reports = build_production_reports()
    assert "Produto Operacional" in {option.name for option in reports.available_recipes}


@pytest.mark.django_db
def test_ficha_sem_nome_cai_no_sku_e_a_linha_continua_na_tela(db):
    """Fallback honesto: sem nome, o SKU é a resposta — a linha nunca some.

    ``Recipe.save`` valida e recusa nome vazio, então a ficha anônima só existe
    por escrita que pula a validação (import, migração, fixture). O ``update``
    abaixo é justamente isso: o guardrail é para o dado que chega torto, não
    para o caminho feliz.
    """
    sem_nome = Recipe.objects.create(
        ref="sem-nome-v1",
        name="Provisório",
        output_sku="SEM-NOME",
        batch_size=Decimal("1"),
    )
    Recipe.objects.filter(pk=sem_nome.pk).update(name="")
    sem_nome.refresh_from_db()
    craft.plan(sem_nome, 5, date=date.today())

    board = build_production_board(selected_date=date.today())
    row = next(r for r in board.matrix_rows if r.output_sku == "SEM-NOME")

    assert row.recipe_name == "SEM-NOME"
    assert row.planned_orders[0].recipe_name == "SEM-NOME"
    assert "SEM-NOME" in {option.name for option in board.recipes}
