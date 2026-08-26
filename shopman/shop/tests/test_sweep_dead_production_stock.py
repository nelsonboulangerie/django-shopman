"""Resíduo de processo de WO morta é zerado pelo ledger — e SÓ ele.

O fantasma que o sweeper caça: quant em posição de processo (ou lote
``started``) com ``target_date`` vencida conta como ``in_production`` no
``total_promisable`` até a shelf-life vencer — estoque prometido que nunca
vai existir. A janela é "WO morta", nunca idade: enquanto a WO vive
(planned/started), o quant é a matéria do finish tardio e quem cobra é o
alerta ``production_unfinished``, não a vassoura.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone
from shopman.craftsman import STOCK_CONSUMED_KEY, STOCK_REALIZED_KEY
from shopman.craftsman.contrib.stockman.handlers import STARTED_BATCH
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.stockman.models import Hold, HoldStatus, Move, Position, PositionKind, Quant

pytestmark = pytest.mark.django_db

SKU = "PAO-DEAD"
YESTERDAY = date.today() - timedelta(days=1)


@pytest.fixture
def producao(db):
    return Position.objects.create(
        ref="producao", name="Produção", kind=PositionKind.PROCESS, is_saleable=False
    )


@pytest.fixture
def vitrine(db):
    return Position.objects.create(
        ref="vitrine", name="Vitrine", kind=PositionKind.PHYSICAL, is_saleable=True
    )


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        ref="rc-dead", name="Pão", output_sku=SKU, batch_size=Decimal("1")
    )


def _quant(position, *, sku=SKU, target=YESTERDAY, qty="10", batch=""):
    return Quant.objects.create(
        sku=sku, position=position, target_date=target, batch=batch,
        _quantity=Decimal(qty),
    )


def _wo(recipe, *, status, target=YESTERDAY, meta=None):
    """WO direto no banco, sem signals — simula exatamente o cenário do resíduo:
    o ajuste do handler de void nunca rodou (ou falhou engolido)."""
    return WorkOrder.objects.create(
        recipe=recipe,
        output_sku=SKU,
        quantity=Decimal("10"),
        status=status,
        target_date=target,
        meta=meta or {},
    )


def _run(*args):
    call_command("sweep_dead_production_stock", *args, stdout=StringIO())


def _closed_ledger_meta():
    now = timezone.now().isoformat()
    return {STOCK_CONSUMED_KEY: now, STOCK_REALIZED_KEY: now}


# ── Zera o inerte ────────────────────────────────────────────────────────────


def test_zeroes_started_residue_of_voided_wo(recipe, producao):
    quant = _quant(producao, batch=STARTED_BATCH)
    _wo(recipe, status=WorkOrder.Status.VOID)

    _run()

    quant.refresh_from_db()
    assert quant.quantity == 0
    # Nunca delete: a linha fica, e a remoção é um lançamento ADJUST legível.
    move = Move.objects.get(quant=quant, kind=Move.Kind.ADJUST)
    assert move.delta == Decimal("-10")
    assert "sem WO ativa" in move.reason


def test_zeroes_process_quant_without_any_wo(recipe, producao):
    quant = _quant(producao)

    _run()

    quant.refresh_from_db()
    assert quant.quantity == 0


def test_zeroes_started_batch_without_position(recipe):
    # batch='started' conta como in_production mesmo sem posição.
    quant = _quant(None, batch=STARTED_BATCH)
    _wo(recipe, status=WorkOrder.Status.VOID)

    _run()

    quant.refresh_from_db()
    assert quant.quantity == 0


def test_zeroes_residue_when_finished_wo_closed_its_ledger(recipe, producao):
    # Sobra de rendimento antiga com o ledger FECHADO: ninguém mais vai
    # realizar este quant — é inerte.
    quant = _quant(producao, batch=STARTED_BATCH)
    _wo(recipe, status=WorkOrder.Status.FINISHED, meta=_closed_ledger_meta())

    _run()

    quant.refresh_from_db()
    assert quant.quantity == 0


# ── Nunca decide pelo operador ───────────────────────────────────────────────


def test_preserves_quant_of_live_started_wo(recipe, producao):
    # A fornada esquecida de ontem que a expedição ainda pode concluir hoje:
    # o quant é a matéria do finish tardio. Alerta cobra; vassoura não toca.
    quant = _quant(producao, batch=STARTED_BATCH)
    _wo(recipe, status=WorkOrder.Status.STARTED)

    _run()

    quant.refresh_from_db()
    assert quant.quantity == Decimal("10")
    assert not Move.objects.filter(quant=quant).exists()


def test_preserves_quant_of_live_planned_wo(recipe, producao):
    quant = _quant(producao)
    _wo(recipe, status=WorkOrder.Status.PLANNED)

    _run()

    quant.refresh_from_db()
    assert quant.quantity == Decimal("10")


def test_one_live_wo_protects_the_shared_quant(recipe, producao):
    # Quant planejado é compartilhado por (sku, data): uma WO void e uma viva
    # no mesmo par — o quant fica intacto até a última morrer.
    quant = _quant(producao)
    _wo(recipe, status=WorkOrder.Status.VOID)
    _wo(recipe, status=WorkOrder.Status.STARTED)

    _run()

    quant.refresh_from_db()
    assert quant.quantity == Decimal("10")


def test_preserves_quant_when_finished_ledger_is_open(recipe, producao):
    # Sem os carimbos das pernas, o quant ainda é reivindicado pelo
    # sweep_unrealized_production (ou por conferência humana já alertada).
    quant = _quant(producao, batch=STARTED_BATCH)
    _wo(recipe, status=WorkOrder.Status.FINISHED, meta={})

    _run()

    quant.refresh_from_db()
    assert quant.quantity == Decimal("10")


# ── Escopo ───────────────────────────────────────────────────────────────────


def test_preserves_today_target(recipe, producao):
    quant = _quant(producao, target=date.today())

    _run()

    quant.refresh_from_db()
    assert quant.quantity == Decimal("10")


def test_preserves_saleable_positions(recipe, vitrine):
    # Vitrine com data passada não é resíduo de processo — fora do escopo.
    quant = _quant(vitrine)

    _run()

    quant.refresh_from_db()
    assert quant.quantity == Decimal("10")


def test_preserves_quant_with_active_hold(recipe, producao):
    quant = _quant(producao)
    Hold.objects.create(
        sku=SKU,
        quant=quant,
        quantity=Decimal("2"),
        target_date=YESTERDAY,
        status=HoldStatus.PENDING,
        expires_at=timezone.now() + timedelta(hours=1),
    )

    _run()

    quant.refresh_from_db()
    assert quant.quantity == Decimal("10")


def test_dry_run_writes_nothing(recipe, producao):
    quant = _quant(producao, batch=STARTED_BATCH)
    _wo(recipe, status=WorkOrder.Status.VOID)

    _run("--dry-run")

    quant.refresh_from_db()
    assert quant.quantity == Decimal("10")
    assert not Move.objects.filter(quant=quant).exists()
