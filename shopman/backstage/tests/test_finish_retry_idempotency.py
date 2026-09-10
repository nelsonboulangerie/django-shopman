"""O retry do operador depois de um erro pós-commit não pode ser um beco.

O hazard inverso: o ``production_changed`` sai FORA do atomic do ``finish()``,
então um receiver POSTERIOR ao de estoque que estoure faz uma fornada 100%
commitada devolver erro ao operador. Ele aperta de novo — e o segundo finish
morre em ``TERMINAL_STATUS``, porque a WorkOrder já está ``finished``. A fornada
fica correta no banco e impossível de fechar na tela.

O core sempre soube resolver isso (``idempotency_key`` em
``CraftExecution.finish`` devolve a WO existente no replay); o backstage é que
nunca passava a chave.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.craftsman.models import Recipe, WorkOrder, WorkOrderItem
from shopman.craftsman.signals import production_changed
from shopman.stockman.models import Batch, Position, PositionKind, Quant

from shopman.backstage.services import production as backstage_production
from shopman.backstage.services.exceptions import ProductionConflict

pytestmark = pytest.mark.django_db

SKU = "PAO-RETRY"


@pytest.fixture
def vitrine(db):
    pos, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return pos


@pytest.fixture
def recipe(db, vitrine):
    return Recipe.objects.create(ref="rc-retry", name="Pão", output_sku=SKU, batch_size=Decimal("1"))


@pytest.fixture
def a_later_receiver_explodes():
    """Receiver POSTERIOR ao de estoque: tudo commitado, e mesmo assim erro.

    O de estoque é o #0 (o app ``craftsman.contrib.stockman`` vem antes de
    ``shop`` no INSTALLED_APPS), então quem conecta agora roda depois dele.
    """
    state = {"armed": True}

    def _boom(sender, **kwargs):
        if state["armed"] and kwargs.get("action") == "finished":
            state["armed"] = False  # só o primeiro finish estoura
            raise RuntimeError("um receiver posterior estourou")

    production_changed.connect(_boom, dispatch_uid="test-later-receiver", weak=False)
    try:
        yield state
    finally:
        production_changed.disconnect(dispatch_uid="test-later-receiver")


def _vitrine_qty(vitrine) -> Decimal:
    quant = Quant.objects.filter(sku=SKU, position=vitrine, target_date=None).first()
    return quant.quantity if quant else Decimal("0")


def test_receiver_failure_rolls_back_and_retry_closes_the_batch(recipe, vitrine, a_later_receiver_explodes):
    _, wo_ref, _ = _first_attempt_rolls_back(recipe, vitrine)
    work_order = WorkOrder.objects.get(ref=wo_ref)

    # O operador aperta de novo, com exatamente os mesmos dados.
    ref_again, total = backstage_production.apply_finish(
        work_order_id=work_order.pk,
        quantity="40",
        actor="test",
        expected_rev=work_order.rev,
        idempotency_key="receiver-failure-retry",
    )

    assert ref_again == wo_ref
    assert total == Decimal("40")
    # E o replay não creditou a vitrine de novo.
    assert _vitrine_qty(vitrine) == Decimal("40")


def test_retry_with_a_different_quantity_is_still_a_conflict(recipe, vitrine):
    """Fechar de novo com OUTRO número não é retry: é conflito, e tem que doer."""
    from django.utils import timezone
    from shopman.craftsman.service import craft

    work_order = craft.plan(recipe, Decimal("40"), date=timezone.localdate())
    craft.start(work_order, quantity=Decimal("40"), actor="test")
    work_order.refresh_from_db()
    backstage_production.apply_finish(
        work_order_id=work_order.pk,
        quantity="40",
        actor="test",
        expected_rev=work_order.rev,
        idempotency_key="accepted-finish",
    )
    work_order.refresh_from_db()

    with pytest.raises(ProductionConflict):
        backstage_production.apply_finish(
            work_order_id=work_order.pk,
            quantity="35",
            actor="test",
            expected_rev=work_order.rev,
            idempotency_key="different-finish",
        )


def test_finish_replay_never_rewrites_historical_batch(recipe, vitrine):
    """Recipe/catalog edits and manual lot corrections stay immutable on retry."""
    from datetime import date, timedelta

    from shopman.craftsman.service import craft

    recipe.meta = {"requires_batch_tracking": True, "shelf_life_days": 2}
    recipe.save(update_fields=["meta", "updated_at"])
    work_order = craft.plan(recipe, Decimal("40"), date=date.today())
    craft.start(work_order, quantity=Decimal("40"), actor="test")
    work_order.refresh_from_db()
    attempt_rev = work_order.rev
    backstage_production.apply_finish(
        work_order_id=work_order.pk,
        quantity="40",
        actor="test",
        expected_rev=attempt_rev,
        idempotency_key="immutable-batch-finish",
    )

    output = WorkOrderItem.objects.get(
        work_order=work_order,
        kind=WorkOrderItem.Kind.OUTPUT,
    )
    assert output.meta["batch_traceability"]["expiry_date"] == str(date.today() + timedelta(days=2))
    batch = Batch.objects.get(ref=output.batch_ref)
    corrected_expiry = date.today() + timedelta(days=5)
    batch.expiry_date = corrected_expiry
    batch.notes = "Correção manual auditada"
    batch.save(update_fields=["expiry_date", "notes"])
    recipe.meta = {"requires_batch_tracking": True, "shelf_life_days": 30}
    recipe.save(update_fields=["meta", "updated_at"])

    backstage_production.apply_finish(
        work_order_id=work_order.pk,
        quantity="40",
        actor="test",
        expected_rev=attempt_rev,
        idempotency_key="immutable-batch-finish",
    )

    batch.refresh_from_db()
    assert batch.expiry_date == corrected_expiry
    assert batch.notes == "Correção manual auditada"


def _first_attempt_rolls_back(recipe, vitrine):
    """Plan/start, then prove that a later receiver cannot leak a partial finish."""
    from django.utils import timezone
    from shopman.craftsman.service import craft

    work_order = craft.plan(recipe, Decimal("40"), date=timezone.localdate())
    craft.start(work_order, quantity=Decimal("40"), actor="test")
    work_order.refresh_from_db()

    with pytest.raises(RuntimeError):
        backstage_production.apply_finish(
            work_order_id=work_order.pk,
            quantity="40",
            actor="test",
            expected_rev=work_order.rev,
            idempotency_key="receiver-failure-retry",
        )

    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.STARTED
    assert _vitrine_qty(vitrine) == Decimal("0")
    return recipe.output_sku, work_order.ref, Decimal("40")
