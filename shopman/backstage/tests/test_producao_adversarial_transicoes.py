"""Transição de estado errada e quadro velho: a fornada tem de recusar com o
dialeto certo (409 conflito vs 400 pedido inválido), nunca com um 500.

As telas de produção são muitas (grid do gestor, quiosque de QC, KDS, timer do
forno) e todas olham a mesma fornada. Quando duas mexem na mesma ordem, ou quando
uma tela abre uma ação impossível para o estado atual (avançar passo numa fornada
que ainda não começou, estornar uma que já saiu), o core recusa — e o que o
operador tem de ver é o mapeamento da casa:

  - conflito de estado / revisão velha  → ``ProductionConflict`` (HTTP 409)
  - passo/estado inaplicável            → ``ProductionError``    (HTTP 400)

O ``expected_rev`` no ``start`` e no ``finish`` nunca tinha teste — só o ``plan``
e o ``void`` provavam o compare-and-swap. Aqui as quatro mutações com revisão
fecham a cobertura.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import pytest
from django.utils import timezone
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.stockman.models import Position, PositionKind

from shopman.backstage.services import production as backstage_production
from shopman.backstage.services.exceptions import ProductionConflict, ProductionError

pytestmark = pytest.mark.django_db

SKU = "PAO-TRANS"


@pytest.fixture
def vitrine(db):
    pos, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return pos


@pytest.fixture
def recipe(db, vitrine):
    return Recipe.objects.create(
        ref="rc-trans",
        name="Pão",
        output_sku=SKU,
        batch_size=Decimal("1"),
        meta={"steps": ["Misturar", "Modelar", "Assar"]},
    )


def _planned(recipe) -> WorkOrder:
    return craft.plan(recipe, Decimal("40"), date=timezone.localdate())


def _started(recipe) -> WorkOrder:
    wo = _planned(recipe)
    craft.start(wo, quantity=Decimal("40"), actor="test")
    return wo


def _finished(recipe) -> WorkOrder:
    wo = _started(recipe)
    craft.finish(wo, finished=Decimal("40"), actor="test")
    return wo


def _void(recipe) -> WorkOrder:
    wo = _planned(recipe)
    craft.void(wo, reason="teste")
    return wo


def _no_arithmetic_leak(excinfo):
    assert not isinstance(excinfo.value, (InvalidOperation, ArithmeticError))


# ── START numa ordem que não está PLANNED ───────────────────────────────────

@pytest.mark.parametrize("factory", ["_started", "_finished", "_void"])
def test_start_fora_de_planned_e_conflito(recipe, factory):
    wo = globals()[factory](recipe)
    with pytest.raises(ProductionConflict) as excinfo:
        backstage_production.apply_start(
            work_order_id=wo.pk, quantity="40", actor="test"
        )
    _no_arithmetic_leak(excinfo)


# ── VOID nos estados terminais ───────────────────────────────────────────────

def test_void_de_ordem_ja_estornada_e_conflito(recipe):
    wo = _void(recipe)
    with pytest.raises(ProductionConflict):
        backstage_production.apply_void(wo.pk, actor="test")


def test_void_de_fornada_concluida_e_conflito(recipe):
    """Fornada que já saiu não estorna — o dinheiro/estoque já andou."""
    wo = _finished(recipe)
    with pytest.raises(ProductionConflict):
        backstage_production.apply_void(wo.pk, actor="test")


# ── FINISH numa ordem estornada ──────────────────────────────────────────────

def test_finish_de_ordem_estornada_e_conflito(recipe, vitrine):
    wo = _void(recipe)
    with pytest.raises(ProductionConflict):
        backstage_production.apply_finish(
            work_order_id=wo.pk, quantity="40", actor="test"
        )


# ── ADVANCE STEP fora de STARTED ─────────────────────────────────────────────

@pytest.mark.parametrize("factory", ["_planned", "_finished", "_void"])
def test_advance_step_fora_de_started_recusa(recipe, factory):
    wo = globals()[factory](recipe)
    with pytest.raises(ProductionError) as excinfo:
        backstage_production.apply_advance_step(work_order_id=wo.pk, actor="test")
    # Conflito de estado terminal também é aceitável; o que não pode é vazar 500.
    _no_arithmetic_leak(excinfo)


# ── expected_rev: o quadro que a tela leu ainda vale? ────────────────────────

def test_start_com_revisao_velha_e_conflito(recipe):
    wo = _planned(recipe)
    wo.refresh_from_db()
    with pytest.raises(ProductionConflict):
        backstage_production.apply_start(
            work_order_id=wo.pk,
            quantity="40",
            actor="test",
            expected_rev=wo.rev + 1,  # a tela leu uma revisão que não é a de agora
        )
    # E a ordem não iniciou por engano.
    wo.refresh_from_db()
    assert wo.status == WorkOrder.Status.PLANNED


def test_finish_com_revisao_velha_e_conflito(recipe, vitrine):
    wo = _started(recipe)
    wo.refresh_from_db()
    with pytest.raises(ProductionConflict):
        backstage_production.apply_finish(
            work_order_id=wo.pk,
            quantity="40",
            actor="test",
            expected_rev=wo.rev + 1,
        )
    wo.refresh_from_db()
    assert wo.status == WorkOrder.Status.STARTED


def test_finish_com_revisao_certa_fecha(recipe, vitrine):
    """O contraponto: a revisão que a tela leu ainda vale, e o finish passa."""
    wo = _started(recipe)
    wo.refresh_from_db()
    ref, total = backstage_production.apply_finish(
        work_order_id=wo.pk,
        quantity="40",
        actor="test",
        expected_rev=wo.rev,
    )
    assert ref == wo.ref
    assert total == Decimal("40")
    wo.refresh_from_db()
    assert wo.status == WorkOrder.Status.FINISHED
