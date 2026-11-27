"""Nenhuma tela esconde perda (WP-F18; dono, 24/11).

A perda do lote é previsto menos realizado, e se abre em duas partes visíveis e
somadas: a perda declarada (as linhas de Perda da Finalização, com o defeito) e a
diferença de rendimento ("rendeu menos", com a causa gravada no evento de
fechamento, ``context.yield_deviation``). Cada parte diz a causa, quem fechou e a
hora. "Rendeu mais" aparece com a causa e nunca abate perda. A gestão do dia usa a
MESMA conta dos Relatórios (P2-16), e a soma bate com as baixas de perda do ledger.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from itertools import count

import pytest
from django.contrib.auth import get_user_model
from shopman.craftsman.models import Recipe, WorkOrder, WorkOrderEvent
from shopman.stockman.models import Move, Position

from shopman.backstage.projections.production import (
    LOSS_WITHOUT_CAUSE,
    build_production_dashboard,
    build_production_reports,
)
from shopman.backstage.services import production

pytestmark = pytest.mark.django_db

_keys = count(1)


@pytest.fixture(autouse=True)
def _postos(db):
    Position.objects.get_or_create(ref="vitrine", defaults={"name": "Vitrine", "is_saleable": True})
    Position.objects.get_or_create(ref="forno", defaults={"name": "Forno da frente", "is_default": True})


@pytest.fixture(autouse=True)
def _sem_insumo(monkeypatch):
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(ref="baguete-v1", name="Baguete", output_sku="BAGUETE", batch_size=Decimal("10"))


@pytest.fixture(autouse=True)
def _cozinha(db):
    get_user_model().objects.create_user("ana", first_name="Ana", password="x", is_staff=True)


def _lote(recipe, quantity: str = "10") -> WorkOrder:
    _, ref, _, _ = production.apply_planned(
        recipe_id=recipe.pk,
        quantity=quantity,
        target_date_value=date.today().isoformat(),
        position_ref="forno",
        actor="production:ana",
        idempotency_key=f"perda-plan-{next(_keys)}",
    )
    work_order = WorkOrder.objects.get(ref=ref)
    production.apply_start(
        work_order_id=work_order.pk,
        quantity=quantity,
        actor="production:ana",
        expected_rev=work_order.rev,
        idempotency_key=f"perda-start-{next(_keys)}",
    )
    return WorkOrder.objects.get(pk=work_order.pk)


def _fechar(work_order: WorkOrder, quantity: str, partition: list[dict], **deviation) -> WorkOrder:
    production.apply_finish(
        work_order_id=work_order.pk,
        quantity=quantity,
        actor="production:ana",
        partition=partition,
        expected_rev=WorkOrder.objects.values_list("rev", flat=True).get(pk=work_order.pk),
        idempotency_key=f"perda-finish-{next(_keys)}",
        **deviation,
    )
    return WorkOrder.objects.get(pk=work_order.pk)


def _dia():
    today = date.today().isoformat()
    return build_production_reports({"date_from": today, "date_to": today})


def _o_roteiro_do_dono(recipe):
    """Um lote com 2 de perda ("Assou demais") e outro que rendeu 3 a menos."""
    com_perda = _fechar(
        _lote(recipe),
        "10",
        [
            {"quantity": "8", "quality_grade_ref": "standard"},
            {"quantity": "2", "quality_defect_ref": "overbaked", "loss": True},
        ],
    )
    rendeu_menos = _fechar(
        _lote(recipe),
        "7",
        [{"quantity": "7", "quality_grade_ref": "standard"}],
        yield_deviation_confirmed=True,
        yield_deviation_reason="A massa rendeu menos peças",
    )
    return com_perda, rendeu_menos


def test_cada_lote_mostra_a_perda_total_e_as_partes_com_causa_quem_e_hora(recipe):
    com_perda, rendeu_menos = _o_roteiro_do_dono(recipe)

    rows = {row.ref: row for row in _dia().history_rows}

    declared = rows[com_perda.ref]
    assert (declared.qty_loss, declared.loss_declared, declared.loss_shortfall) == ("2", "2", "0")
    [part] = declared.loss_parts
    assert (part.kind_label, part.quantity_display, part.cause, part.who) == (
        "Perda declarada",
        "2 un.",
        "Assou demais",
        "Ana",
    )
    assert part.at

    short = rows[rendeu_menos.ref]
    assert (short.qty_loss, short.loss_declared, short.loss_shortfall) == ("3", "0", "3")
    [part] = short.loss_parts
    assert (part.kind_label, part.quantity_display, part.cause, part.who) == (
        "Rendeu menos",
        "3 un.",
        "A massa rendeu menos peças",
        "Ana",
    )


def test_a_linha_fala_a_lingua_da_casa(recipe):
    com_perda, _ = _o_roteiro_do_dono(recipe)

    row = next(row for row in _dia().history_rows if row.ref == com_perda.ref)

    assert row.date_display == date.today().strftime("%d/%m")
    assert row.operator_name == "Ana"
    assert row.position_name == "Forno da frente"
    assert (row.unit_label, row.qty_finished_display, row.qty_loss_display) == ("un.", "8 un.", "2 un.")


def test_a_perda_do_dia_soma_as_duas_partes_e_bate_com_o_ledger(recipe):
    _o_roteiro_do_dono(recipe)

    dashboard = build_production_dashboard()
    reports = _dia()

    [by_unit] = dashboard.loss_by_unit
    assert by_unit.heading == "Peças"
    assert (by_unit.unit_label, by_unit.total_display, by_unit.declared_display, by_unit.shortfall_display) == (
        "un.",
        "5 un.",
        "2 un.",
        "3 un.",
    )
    assert dashboard.loss_display == "5 un."
    assert dashboard.loss_hint == "2 dos 2 lotes fechados tiveram perda"
    assert dashboard.planned_hint == "2 lotes no plano do dia"
    # A gestão do dia usa a MESMA conta dos Relatórios (P2-16).
    assert sum(Decimal(row.qty_loss) for row in reports.history_rows) == Decimal("5")
    [waste] = reports.waste_rows
    assert (waste.loss_total, waste.loss_declared_display, waste.loss_shortfall_display) == ("5", "2 un.", "3 un.")
    assert {row.ref for row in dashboard.loss_lots} == {row.ref for row in reports.history_rows}
    # E bate com as baixas de perda do ledger de estoque do dia.
    written_off = sum(
        (-move.delta for move in Move.objects.filter(quant__sku="BAGUETE", kind=Move.Kind.WASTE)),
        Decimal("0"),
    )
    assert written_off == Decimal("5")


def test_diferenca_sem_causa_registrada_aparece_e_nunca_some(recipe):
    """Lote de antes da regra: a diferença está lá, a causa não. Vira parte própria."""
    _, rendeu_menos = _o_roteiro_do_dono(recipe)
    event = WorkOrderEvent.objects.get(work_order=rendeu_menos, kind=WorkOrderEvent.Kind.FINISHED)
    payload = dict(event.payload)
    payload["context"] = {key: value for key, value in payload["context"].items() if key != "yield_deviation"}
    WorkOrderEvent.objects.filter(pk=event.pk).update(payload=payload)

    row = next(row for row in _dia().history_rows if row.ref == rendeu_menos.ref)

    assert row.qty_loss == "3"
    [part] = row.loss_parts
    assert (part.kind_label, part.quantity, part.cause) == ("Rendeu menos", "3", LOSS_WITHOUT_CAUSE)


def test_rendeu_mais_aparece_com_a_causa_e_nao_abate_a_perda_declarada(recipe):
    lote = _fechar(
        _lote(recipe),
        "12",
        [
            {"quantity": "10", "quality_grade_ref": "standard"},
            {"quantity": "2", "quality_defect_ref": "overbaked", "loss": True},
        ],
        yield_deviation_confirmed=True,
        yield_deviation_reason="Peças menores que o padrão",
    )

    row = next(row for row in _dia().history_rows if row.ref == lote.ref)

    assert (row.qty_loss, row.loss_declared, row.loss_overshoot) == ("2", "2", "2")
    kinds = {part.kind: part for part in row.loss_parts}
    assert kinds["declared"].counts_as_loss is True
    assert kinds["yield_overshoot"].counts_as_loss is False
    assert kinds["yield_overshoot"].cause == "Peças menores que o padrão"
    assert build_production_dashboard().loss_display == "2 un."


def test_produtividade_e_de_quem_fechou_pelo_nome(recipe):
    _o_roteiro_do_dono(recipe)

    [row] = _dia().operator_rows

    assert row.operator_name == "Ana"
    assert row.wo_count == 2
    assert row.qty_total_display == "15 un."
    assert (row.qty_count_display, row.qty_mass_display, row.qty_volume_display) == ("15 un.", "0 g", "")
