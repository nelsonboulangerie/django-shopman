"""``craft.record_event``: quem está fora do Craftsman anota a execução por aqui (C11)."""

from decimal import Decimal

import pytest
from django.db import IntegrityError
from shopman.craftsman import CraftError, craft
from shopman.craftsman.models import Recipe, WorkOrderEvent


@pytest.fixture
def work_order(db):
    recipe = Recipe.objects.create(
        ref="pao-evento",
        name="Pão",
        output_sku="pao-evento",
        batch_size=Decimal("1"),
    )
    return craft.plan(recipe, 10)


def test_lanca_o_evento_na_proxima_seq_sem_mudar_a_ordem(work_order):
    rev, status = work_order.rev, work_order.status
    event = craft.record_event(
        work_order,
        kind=WorkOrderEvent.Kind.OVEN_ARMED,
        payload={"run_id": 1},
        actor="forno",
        idempotency_key="oven-arm:1",
    )

    assert event.seq == 1  # o planned é a seq 0
    assert event.kind == WorkOrderEvent.Kind.OVEN_ARMED
    assert event.payload == {"run_id": 1}
    assert event.actor == "forno"
    work_order.refresh_from_db()
    assert (work_order.rev, work_order.status) == (rev, status)


@pytest.mark.parametrize(
    "kind",
    ["planned", "adjusted", "started", "step_advanced", "finished", "voided"],
)
def test_evento_do_ciclo_so_nasce_no_verbo_da_transicao(work_order, kind):
    with pytest.raises(CraftError) as exc:
        craft.record_event(work_order, kind=kind, payload={})
    assert exc.value.code == "EVENT_KIND_NOT_RECORDABLE"


def test_chave_repetida_nao_lanca_em_dobro(work_order):
    craft.record_event(work_order, kind="oven_concluded", payload={}, idempotency_key="k")
    with pytest.raises(IntegrityError):
        craft.record_event(work_order, kind="oven_concluded", payload={}, idempotency_key="k")
