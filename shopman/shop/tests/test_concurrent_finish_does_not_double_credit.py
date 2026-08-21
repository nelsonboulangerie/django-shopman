"""Dois toques simultâneos no FINALIZAR não podem creditar a vitrine em dobro.

O ``production_changed`` sai FORA do ``transaction.atomic`` do
``CraftExecution.finish``, e as pernas do ledger carimbavam o marcador DEPOIS
de escrever. Entre o COMMIT da WorkOrder e o carimbo existia uma janela em que
``stock_legs_complete()`` respondia falso: a segunda requisição passava pela
idempotência (o core devolve a WO existente em vez de estourar
``TERMINAL_STATUS``), caía em ``_ensure_stock_ledger_closed``, lia o ledger
como "aberto" e reexecutava as duas pernas. Os dois operadores liam
``200 {"ok": true}``, e 24 madeleines viravam 48 na vitrine.

O invariante ``_quantity == Σ(moves.delta)`` NÃO pega este defeito: o ledger
fica internamente consistente e materialmente errado. A asserção que vale é a
daqui — o saldo da vitrine depois de dois fechamentos é igual ao de um.

Vizinho que afirmava algo mais fraco:
``packages/craftsman/.../tests/test_concurrency.py`` prova que o segundo
``finish()`` morre em ``TERMINAL_STATUS`` — verdade só SEM chave de
idempotência. A superfície do operador manda chave (derivada do payload em
``_finish_idempotency_key``), e é justamente por ela que o segundo toque passa.
"""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest
from django.conf import settings
from django.db import connections
from django.utils import timezone
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.craftsman.service import craft
from shopman.stockman import stock
from shopman.stockman.models import Position, PositionKind, Quant

from shopman.backstage.services.production import apply_finish

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        "sqlite" in settings.DATABASES["default"]["ENGINE"],
        reason="Trava de linha real (SELECT FOR UPDATE) exige PostgreSQL",
    ),
]

BATCH = Decimal("24")
FLOUR_PER_BATCH = Decimal("0.500")
ROUNDS = 20


@pytest.fixture
def vitrine(db):
    pos, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return pos


def _vitrine_qty(sku: str, vitrine) -> Decimal:
    total = Decimal("0")
    for quant in Quant.objects.filter(sku=sku, position=vitrine):
        total += quant.quantity
    return total


def _finish_twice_at_once(work_order_id) -> None:
    """Duas requisições de fechamento no mesmo instante, conexões próprias."""
    gate = threading.Barrier(2)

    def press(slot: int) -> None:
        try:
            gate.wait(timeout=10)
            apply_finish(
                work_order_id=work_order_id,
                quantity=BATCH,
                actor=f"kiosk-{slot}",
                force=True,
            )
        except Exception:  # noqa: BLE001 — quem julga o resultado é a asserção
            pass
        finally:
            connections.close_all()

    threads = [threading.Thread(target=press, args=(slot,)) for slot in (0, 1)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)


def test_two_kiosks_finishing_the_same_batch_credit_the_showcase_once(vitrine):
    """A vitrine termina com o que foi assado, não com o dobro."""
    for round_number in range(ROUNDS):
        sku = f"MD-RACE-{round_number}"
        flour = f"INS-FARINHA-RACE-{round_number}"
        recipe = Recipe.objects.create(
            ref=f"rc-race-{round_number}",
            name="Madeleine",
            output_sku=sku,
            batch_size=BATCH,
        )
        RecipeItem.objects.create(
            recipe=recipe, input_sku=flour, quantity=FLOUR_PER_BATCH, unit="kg"
        )
        stock.receive(quantity=Decimal("100"), sku=flour, reason="abertura do teste")
        flour_before = stock.available(flour)

        work_order = craft.plan(recipe, BATCH, date=timezone.localdate())
        craft.start(work_order, quantity=BATCH, actor="test")

        _finish_twice_at_once(work_order.pk)

        credited = _vitrine_qty(sku, vitrine)
        assert credited == BATCH, (
            f"rodada {round_number}: a vitrine ficou com {credited} "
            f"para uma fornada de {BATCH}"
        )
        consumed = flour_before - stock.available(flour)
        assert consumed == FLOUR_PER_BATCH, (
            f"rodada {round_number}: o insumo baixou {consumed} kg, "
            f"a receita pede {FLOUR_PER_BATCH}"
        )
