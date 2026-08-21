"""Fornada concluída com o ledger pela metade volta a ser realizada.

O ``production_changed`` sai FORA do atomic do ``finish()``: uma queda no meio
do handler deixa a WorkOrder ``finished`` e commitada com o estoque incompleto,
e o retry do operador morre em ``TERMINAL_STATUS``. O sweeper é a saída, e o
marcador por perna é o que o torna seguro — ``_handle_finished`` credita o
``actual`` cheio a cada execução, então re-rodar sem guarda credita a vitrine
em dobro e consome o insumo duas vezes.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone
from shopman.craftsman import STOCK_CONSUMED_KEY, STOCK_REALIZED_KEY
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder
from shopman.craftsman.service import craft
from shopman.stockman import stock
from shopman.stockman.exceptions import StockError
from shopman.stockman.models import Position, PositionKind, Quant
from shopman.stockman.services.movements import StockMovements
from shopman.stockman.services.planning import StockPlanning

from shopman.backstage.models import OperatorAlert

pytestmark = pytest.mark.django_db

SKU = "PAO-SWEEP"
FLOUR = "INS-FARINHA-SWEEP"


@pytest.fixture
def vitrine(db):
    pos, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return pos


@pytest.fixture
def recipe(db, vitrine):
    recipe = Recipe.objects.create(
        ref="rc-sweep", name="Pão", output_sku=SKU, batch_size=Decimal("1")
    )
    RecipeItem.objects.create(
        recipe=recipe, input_sku=FLOUR, quantity=Decimal("1"), unit="kg"
    )
    StockMovements.receive(quantity=Decimal("500"), sku=FLOUR, reason="seed do teste")
    return recipe


@pytest.fixture
def realize_explodes(monkeypatch):
    def _boom(*args, **kwargs):
        raise StockError("QUANT_NOT_FOUND", product=SKU)

    monkeypatch.setattr(StockPlanning, "realize", classmethod(_boom))


def _vitrine_qty(vitrine) -> Decimal:
    quant = Quant.objects.filter(sku=SKU, position=vitrine, target_date=None).first()
    return quant.quantity if quant else Decimal("0")


def _finish_50(recipe):
    work_order = craft.plan(recipe, Decimal("50"), date=timezone.localdate())
    craft.start(work_order, quantity=Decimal("50"), actor="test")
    return work_order


def _age(work_order):
    """Envelhece a fornada para além do limiar do sweeper."""
    WorkOrder.objects.filter(pk=work_order.pk).update(
        finished_at=timezone.now() - timedelta(hours=2)
    )


def test_happy_path_stamps_both_legs(recipe, vitrine):
    work_order = _finish_50(recipe)
    craft.finish(work_order, finished=Decimal("50"), actor="test")

    work_order.refresh_from_db()
    assert work_order.meta[STOCK_CONSUMED_KEY]
    assert work_order.meta[STOCK_REALIZED_KEY]


def test_sweeper_realizes_the_batch_that_never_landed(recipe, vitrine, realize_explodes,
                                                      monkeypatch):
    work_order = _finish_50(recipe)
    with pytest.raises(StockError):
        craft.finish(work_order, finished=Decimal("50"), actor="test")

    work_order.refresh_from_db()
    assert _vitrine_qty(vitrine) == Decimal("0")
    assert work_order.meta.get(STOCK_CONSUMED_KEY)  # o insumo JÁ baixou
    assert not work_order.meta.get(STOCK_REALIZED_KEY)
    _age(work_order)

    monkeypatch.undo()  # o realize volta a funcionar (deploy terminou, banco voltou)
    call_command("sweep_unrealized_production", "--minutes", "1")

    work_order.refresh_from_db()
    assert _vitrine_qty(vitrine) == Decimal("50")
    assert work_order.meta[STOCK_REALIZED_KEY]


def test_sweeper_does_not_consume_the_ingredient_twice(recipe, vitrine, realize_explodes,
                                                       monkeypatch):
    """A falha típica é PARCIAL: insumo baixou, vitrine não."""
    work_order = _finish_50(recipe)
    with pytest.raises(StockError):
        craft.finish(work_order, finished=Decimal("50"), actor="test")
    after_finish = stock.available(FLOUR)
    assert after_finish == Decimal("450")
    _age(work_order)

    monkeypatch.undo()
    call_command("sweep_unrealized_production", "--minutes", "1")

    assert stock.available(FLOUR) == Decimal("450")


def test_sweeper_leaves_a_healthy_batch_alone(recipe, vitrine):
    """A armadilha: re-rodar uma fornada sã credita a vitrine EM DOBRO."""
    work_order = _finish_50(recipe)
    craft.finish(work_order, finished=Decimal("50"), actor="test")
    assert _vitrine_qty(vitrine) == Decimal("50")
    _age(work_order)

    call_command("sweep_unrealized_production", "--minutes", "1")

    assert _vitrine_qty(vitrine) == Decimal("50")
    assert stock.available(FLOUR) == Decimal("450")


def test_unrecoverable_batch_becomes_an_operator_alert(recipe, vitrine, realize_explodes):
    """O que o automático não resolve tem que chegar em alguém."""
    work_order = _finish_50(recipe)
    with pytest.raises(StockError):
        craft.finish(work_order, finished=Decimal("50"), actor="test")
    _age(work_order)

    call_command("sweep_unrealized_production", "--minutes", "1")

    alert = OperatorAlert.objects.filter(type="stock_discrepancy").first()
    assert alert is not None
    assert work_order.ref in alert.message


def test_backfill_protects_batches_finished_before_the_markers(recipe, vitrine):
    """Toda fornada do histórico nasce sem marcador — e é sã.

    Sem o backfill da ``craftsman/0005``, o PRIMEIRO ciclo do sweeper leria o
    histórico inteiro como "não realizado" e reprocessaria as duas pernas de
    cada fornada já fechada.
    """
    import importlib

    from django.apps import apps as django_apps

    backfill = importlib.import_module(
        "shopman.craftsman.migrations.0005_backfill_stock_ledger_markers"
    )

    work_order = _finish_50(recipe)
    craft.finish(work_order, finished=Decimal("50"), actor="test")
    # Fornada anterior aos marcadores: meta limpo, estoque já correto.
    WorkOrder.objects.filter(pk=work_order.pk).update(meta={})
    _age(work_order)

    backfill.stamp_finished_work_orders(django_apps, None)

    work_order.refresh_from_db()
    assert work_order.meta[STOCK_CONSUMED_KEY]
    assert work_order.meta[STOCK_REALIZED_KEY]

    call_command("sweep_unrealized_production", "--minutes", "1")

    assert _vitrine_qty(vitrine) == Decimal("50")
    assert stock.available(FLOUR) == Decimal("450")


def test_sweeper_ignores_a_batch_finished_moments_ago(recipe, vitrine, realize_explodes):
    """Fornada recém-fechada pode ter o handler ainda rodando: não mexer."""
    work_order = _finish_50(recipe)
    with pytest.raises(StockError):
        craft.finish(work_order, finished=Decimal("50"), actor="test")

    call_command("sweep_unrealized_production", "--minutes", "15")

    assert not OperatorAlert.objects.filter(type="stock_discrepancy").exists()


def test_sweeper_will_not_reconsume_a_batch_from_last_month(recipe, vitrine):
    """O piso de data: fornada antiga com ledger aberto NÃO é reprocessada.

    A seleção sem piso lia a história inteira. Os marcadores nasceram em 17/08
    e a ``craftsman/0005`` carimbou o que existia naquele instante, mas todo
    caminho que grava ``FINISHED`` direto no banco (o ``seed``) nasce sem eles.
    Com o ``maintenance_worker`` a cada 5 min, o primeiro ciclo depois de um
    reseed reconsumia os insumos de cada fornada histórica: no staging de 19/08
    foram 280 movimentos de "Consumo de produção" somando −223,610 kg, 264
    deles em dois minutos, e zero alertas.

    O caso é o do ``test_backfill_protects_...`` de cima visto pelo outro lado:
    lá o backfill carimba e o sweeper respeita o carimbo; aqui NÃO há carimbo
    nenhum (é o que um reseed produz), e o que segura é o piso.
    """
    work_order = _finish_50(recipe)
    craft.finish(work_order, finished=Decimal("50"), actor="test")
    flour_before = stock.available(FLOUR)

    # Fornada do mês passado, sem marcador — exatamente o que um reseed grava.
    WorkOrder.objects.filter(pk=work_order.pk).update(
        meta={}, finished_at=timezone.now() - timedelta(days=30)
    )

    call_command("sweep_unrealized_production", "--minutes", "1")

    assert stock.available(FLOUR) == flour_before
    assert _vitrine_qty(vitrine) == Decimal("50")
    work_order.refresh_from_db()
    assert not work_order.meta.get(STOCK_CONSUMED_KEY)  # nem carimbou por cima


def test_sweeper_still_reaches_a_batch_from_this_morning(recipe, vitrine, realize_explodes,
                                                         monkeypatch):
    """Controle positivo do piso: dentro da janela, o sweeper continua agindo."""
    work_order = _finish_50(recipe)
    with pytest.raises(StockError):
        craft.finish(work_order, finished=Decimal("50"), actor="test")
    WorkOrder.objects.filter(pk=work_order.pk).update(
        finished_at=timezone.now() - timedelta(hours=6)
    )

    monkeypatch.undo()
    call_command("sweep_unrealized_production", "--minutes", "1")

    work_order.refresh_from_db()
    assert _vitrine_qty(vitrine) == Decimal("50")
    assert work_order.meta[STOCK_REALIZED_KEY]
