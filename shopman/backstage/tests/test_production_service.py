"""Production mutation service facade tests."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from itertools import count

import pytest
from django.core.management import call_command
from django.utils import timezone
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrder, WorkOrderEvent, WorkOrderItem
from shopman.orderman.models import IdempotencyKey
from shopman.stockman.models import Batch, Position

from shopman.backstage.models import OperatorAlert
from shopman.backstage.services import production
from shopman.backstage.services.exceptions import ProductionConflict
from shopman.backstage.services.production import MissingMaterial, ProductionStockShortError

_attempts = count(1)
_raw_apply_finish = production.apply_finish
_raw_apply_planned = production.apply_planned
_raw_apply_quick_finish = production.apply_quick_finish
_raw_apply_start = production.apply_start
_raw_apply_void = production.apply_void


def _attempt_kwargs(work_order_id, kwargs, action: str):
    enriched = dict(kwargs)
    if "expected_rev" not in enriched:
        enriched["expected_rev"] = WorkOrder.objects.values_list("rev", flat=True).get(pk=work_order_id)
    enriched.setdefault("idempotency_key", f"test-{action}-{next(_attempts)}")
    return enriched


def _apply_start(*, work_order_id, **kwargs):
    return _raw_apply_start(
        work_order_id=work_order_id,
        **_attempt_kwargs(work_order_id, kwargs, "start"),
    )


def _apply_finish(*, work_order_id, **kwargs):
    return _raw_apply_finish(
        work_order_id=work_order_id,
        **_attempt_kwargs(work_order_id, kwargs, "finish"),
    )


def _apply_void(work_order_id, **kwargs):
    return _raw_apply_void(
        work_order_id,
        **_attempt_kwargs(work_order_id, kwargs, "void"),
    )


def _creation_kwargs(kwargs, action: str):
    enriched = dict(kwargs)
    enriched.setdefault("idempotency_key", f"test-{action}-{next(_attempts)}")
    return enriched


def _apply_planned(**kwargs):
    return _raw_apply_planned(**_creation_kwargs(kwargs, "plan"))


def _apply_quick_finish(**kwargs):
    return _raw_apply_quick_finish(**_creation_kwargs(kwargs, "quick-finish"))


@pytest.fixture(autouse=True)
def saleable_position(db):
    Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "is_saleable": True},
    )


@pytest.fixture
def recipe(db, saleable_position):
    return Recipe.objects.create(
        ref="svc-prod-v1",
        name="Serviço Produção",
        output_sku="SVC-PROD",
        batch_size=Decimal("10"),
    )


@pytest.mark.django_db
def test_apply_planned_start_finish_and_void(recipe):
    output_sku, wo_ref, qty, result = _apply_planned(
        recipe_id=recipe.pk,
        quantity="10",
        target_date_value=date.today().isoformat(),
        actor="production:op",
    )
    work_order = WorkOrder.objects.get(ref=wo_ref)

    assert output_sku == recipe.output_sku
    assert qty == Decimal("10")
    assert result == "created"

    started_ref, started_qty = _apply_start(
        work_order_id=work_order.pk,
        quantity="9",
        actor="production:op",
    )
    assert started_ref == wo_ref
    assert started_qty == Decimal("9")

    finished_ref, finished_qty = _apply_finish(
        work_order_id=work_order.pk,
        quantity="8",
        actor="production:op",
    )
    assert finished_ref == wo_ref
    assert finished_qty == Decimal("8")

    planned = craft.plan(recipe, 5, date=date.today())
    assert _apply_void(planned.pk, actor="production:op") == planned.ref


@pytest.mark.django_db
def test_start_retry_uses_frozen_attempt_before_mutable_position_lookup(recipe):
    station = Position.objects.create(ref="start-station", name="Start station")
    work_order = craft.plan(recipe, 10, date=date.today())
    request = {
        "work_order_id": work_order.pk,
        "quantity": "9",
        "position_id": str(station.pk),
        "operator_ref": "operator:ana",
        "note": "primeira massa",
        "actor": "production:ana",
        "expected_rev": work_order.rev,
        "idempotency_key": "start-timeout-retry",
    }

    first = _apply_start(**request)
    station.ref = "renamed-start-station"
    station.save(update_fields=["ref", "updated_at"])
    replay = _apply_start(**request)

    assert replay == first
    assert (
        WorkOrderEvent.objects.filter(
            work_order=work_order,
            kind=WorkOrderEvent.Kind.STARTED,
            idempotency_key=(f"production.start:{work_order.pk}:start-timeout-retry"),
        ).count()
        == 1
    )

    with pytest.raises(ProductionConflict):
        _apply_start(**{**request, "quantity": "8"})


@pytest.mark.django_db
def test_apply_planned_requires_explicit_duplicate_target(recipe):
    first = craft.plan(recipe, 20, date=date.today())
    second = craft.plan(recipe, 12, date=date.today())

    with pytest.raises(ProductionConflict) as exc_info:
        _apply_planned(
            recipe_id=recipe.pk,
            quantity="32",
            target_date_value=date.today().isoformat(),
            actor="production:op",
        )
    assert exc_info.value.data["cause"] == "ambiguous_work_order"

    output_sku, wo_ref, qty, result = _apply_planned(
        recipe_id=recipe.pk,
        work_order_id=first.pk,
        quantity="21",
        target_date_value=date.today().isoformat(),
        actor="production:op",
        expected_rev=first.rev,
        idempotency_key="explicit-plan-target",
    )

    first.refresh_from_db()
    second.refresh_from_db()
    assert output_sku == recipe.output_sku
    assert wo_ref == first.ref
    assert qty == Decimal("21")
    assert result == "adjusted"
    assert first.quantity == Decimal("21")
    assert first.status == WorkOrder.Status.PLANNED
    assert second.status == WorkOrder.Status.PLANNED
    assert (
        WorkOrder.objects.filter(
            recipe=recipe,
            target_date=date.today(),
            status=WorkOrder.Status.PLANNED,
        ).count()
        == 2
    )


@pytest.mark.django_db
def test_unchanged_plan_retry_uses_immutable_receipt_after_later_start(recipe):
    work_order = craft.plan(recipe, 10, date=date.today())
    request = {
        "recipe_id": recipe.pk,
        "quantity": "10",
        "target_date_value": date.today().isoformat(),
        "actor": "production:op",
        "expected_rev": work_order.rev,
        "idempotency_key": "plan-noop-retry",
    }

    first = _apply_planned(**request)
    craft.start(work_order, quantity=10, expected_rev=work_order.rev)
    replay = _apply_planned(**request)

    assert first == replay
    assert first[3] == "unchanged"
    assert (
        WorkOrderEvent.objects.filter(
            work_order=work_order,
            kind=WorkOrderEvent.Kind.PLANNING_CONFIRMED,
            idempotency_key="production.plan:plan-noop-retry",
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_created_plan_retry_survives_recipe_deactivation(recipe):
    request = {
        "recipe_id": recipe.pk,
        "quantity": "10",
        "target_date_value": date.today().isoformat(),
        "actor": "production:op",
        "expected_rev": None,
        "idempotency_key": "plan-create-retry",
    }
    first = _apply_planned(**request)
    recipe.is_active = False
    recipe.save(update_fields=["is_active", "updated_at"])

    assert _apply_planned(**request) == first
    assert WorkOrder.objects.filter(recipe=recipe).count() == 1


@pytest.mark.django_db
def test_empty_cell_clear_retry_cannot_clear_later_work_order(recipe):
    empty_request = {
        "recipe_id": recipe.pk,
        "quantity": "0",
        "target_date_value": date.today().isoformat(),
        "actor": "production:op",
        "expected_rev": None,
        "idempotency_key": "plan-empty-clear",
    }
    first = _apply_planned(**empty_request)
    receipt = IdempotencyKey.objects.get(
        scope="production:planning-attempt",
        key="production.plan:plan-empty-clear",
    )
    IdempotencyKey.objects.filter(pk=receipt.pk).update(created_at=timezone.now() - timedelta(days=30))
    call_command("cleanup_idempotency_keys", "--days", "7")
    assert IdempotencyKey.objects.filter(pk=receipt.pk).exists()

    _, wo_ref, _, _ = _apply_planned(
        recipe_id=recipe.pk,
        quantity="10",
        target_date_value=date.today().isoformat(),
        actor="production:other",
        expected_rev=None,
        idempotency_key="plan-created-later",
    )

    replay = _apply_planned(**empty_request)

    assert first == replay
    assert first[3] == "cleared"
    assert WorkOrder.objects.get(ref=wo_ref).status == WorkOrder.Status.PLANNED
    assert (
        IdempotencyKey.objects.filter(
            scope="production:planning-attempt",
            key="production.plan:plan-empty-clear",
            status="done",
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_planning_receipt_rejects_same_key_with_different_payload(recipe):
    first = {
        "recipe_id": recipe.pk,
        "quantity": "0",
        "target_date_value": date.today().isoformat(),
        "actor": "production:op",
        "expected_rev": None,
        "idempotency_key": "plan-global-receipt",
    }
    _apply_planned(**first)

    with pytest.raises(ProductionConflict):
        _apply_planned(**{**first, "quantity": "7"})

    assert not WorkOrder.objects.filter(recipe=recipe).exists()
    assert (
        IdempotencyKey.objects.filter(
            scope="production:planning-attempt",
            key="production.plan:plan-global-receipt",
            status="done",
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_internal_planning_rejects_invalid_date_instead_of_using_today(recipe):
    with pytest.raises(ValueError, match="Data de produção inválida"):
        _apply_planned(
            recipe_id=recipe.pk,
            quantity="7",
            target_date_value="not-a-date",
            actor="production:op",
            expected_rev=None,
            idempotency_key="invalid-internal-date",
        )

    assert not WorkOrder.objects.filter(recipe=recipe).exists()


@pytest.mark.django_db
def test_planning_uses_one_locked_default_position_resolution(
    recipe,
    monkeypatch,
):
    first = Position.objects.create(
        ref="default-a",
        name="Default A",
        is_default=True,
    )
    second = Position.objects.create(
        ref="default-b",
        name="Default B",
        is_default=False,
    )
    real_guard = production._check_linked_order_coverage

    def switch_default_after_guard_resolution(**kwargs):
        assert kwargs["position_ref"] == first.ref
        first.is_default = False
        first.save(update_fields=["is_default", "updated_at"])
        second.is_default = True
        second.save(update_fields=["is_default", "updated_at"])
        return real_guard(**kwargs)

    monkeypatch.setattr(
        production,
        "_check_linked_order_coverage",
        switch_default_after_guard_resolution,
    )

    _, work_order_ref, _, _ = _apply_planned(
        recipe_id=recipe.pk,
        quantity="7",
        target_date_value=date.today().isoformat(),
        actor="production:op",
        expected_rev=None,
        idempotency_key="single-default-resolution",
    )

    assert WorkOrder.objects.get(ref=work_order_ref).position_ref == first.ref


@pytest.mark.django_db
def test_apply_quick_finish_creates_finished_work_order(recipe):
    output_sku, wo_ref, qty = _apply_quick_finish(
        recipe_id=recipe.pk,
        quantity="3",
        position_id="",
        actor="production:op",
    )

    work_order = WorkOrder.objects.get(ref=wo_ref)
    assert output_sku == recipe.output_sku
    assert qty == Decimal("3")
    assert work_order.status == WorkOrder.Status.FINISHED


@pytest.mark.django_db
def test_quick_finish_done_receipt_replays_after_catalog_change_and_cleanup(recipe):
    request = {
        "recipe_id": recipe.pk,
        "quantity": "3",
        "position_id": "",
        "actor": "production:op",
        "idempotency_key": "quick-done-replay",
    }
    first = _apply_quick_finish(**request)
    receipt = IdempotencyKey.objects.get(
        scope=production.QUICK_FINISH_RECEIPT_SCOPE,
        key="quick-done-replay",
    )
    recipe.is_active = False
    recipe.save(update_fields=["is_active", "updated_at"])
    IdempotencyKey.objects.filter(pk=receipt.pk).update(created_at=timezone.now() - timedelta(days=30))

    call_command("cleanup_idempotency_keys", "--days", "7")

    assert IdempotencyKey.objects.filter(pk=receipt.pk).exists()
    assert _apply_quick_finish(**request) == first
    assert WorkOrder.objects.filter(recipe=recipe).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("attempt_data", "message"),
    [
        (
            {
                "recipe_id": 999_999,
                "quantity": "3",
                "position_id": "",
                "actor": "production:op",
                "idempotency_key": "quick-invalid-recipe-preflight",
            },
            "Receita de produção não encontrada",
        ),
        (
            {
                "recipe_id": None,
                "quantity": "3",
                "position_id": "",
                "actor": "production:op",
                "force": True,
                "override_reason": "",
                "idempotency_key": "quick-missing-reason-preflight",
            },
            "Justificativa obrigatória",
        ),
    ],
)
def test_quick_finish_invalid_command_creates_no_persistent_receipt(
    recipe,
    attempt_data,
    message,
):
    if attempt_data["recipe_id"] is None:
        attempt_data = {**attempt_data, "recipe_id": recipe.pk}

    with pytest.raises(production.ProductionError, match=message):
        _apply_quick_finish(**attempt_data)

    assert not IdempotencyKey.objects.filter(
        scope=production.QUICK_FINISH_RECEIPT_SCOPE,
        key=attempt_data["idempotency_key"],
    ).exists()
    assert not WorkOrder.objects.filter(recipe=recipe).exists()


@pytest.mark.django_db
def test_quick_finish_shortage_then_force_reuses_the_same_work_order(recipe, monkeypatch):
    missing = [
        MissingMaterial(
            sku="FARINHA",
            needed=Decimal("5"),
            available=Decimal("2"),
        )
    ]
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: missing)
    attempt = "quick-shortage-force"

    with pytest.raises(ProductionStockShortError) as exc:
        _apply_quick_finish(
            recipe_id=recipe.pk,
            quantity="3",
            position_id="",
            actor="production:op",
            idempotency_key=attempt,
        )

    stranded = WorkOrder.objects.get(ref=exc.value.work_order_ref)
    assert stranded.status == WorkOrder.Status.PLANNED
    assert WorkOrder.objects.filter(recipe=recipe).count() == 1

    _, finished_ref, qty = _apply_quick_finish(
        recipe_id=recipe.pk,
        quantity="3",
        position_id="",
        actor="production:op",
        force=True,
        override_reason="Falta confirmada pelo responsável",
        idempotency_key=attempt,
        approved_shortage=production.production_shortage_snapshot(exc.value),
    )

    assert finished_ref == stranded.ref
    assert qty == Decimal("3")
    assert WorkOrder.objects.filter(recipe=recipe).count() == 1
    stranded.refresh_from_db()
    assert stranded.status == WorkOrder.Status.FINISHED
    override = WorkOrderEvent.objects.get(
        work_order=stranded,
        kind=WorkOrderEvent.Kind.SHORTAGE_OVERRIDDEN,
    )
    assert override.payload["work_order_rev"] == stranded.rev


@pytest.mark.django_db
def test_quick_finish_done_receipt_cannot_be_promoted_to_force(recipe, monkeypatch):
    missing = [
        MissingMaterial(
            sku="FARINHA",
            needed=Decimal("5"),
            available=Decimal("2"),
        )
    ]
    monkeypatch.setattr(production, "check_finish_materials", lambda order: missing)
    request = {
        "recipe_id": recipe.pk,
        "quantity": "3",
        "position_id": "",
        "actor": "production:op",
        "idempotency_key": "quick-nonforce-wins",
    }
    with pytest.raises(ProductionStockShortError):
        _apply_quick_finish(**request)

    monkeypatch.setattr(production, "check_finish_materials", lambda order: [])
    _, work_order_ref, _ = _apply_quick_finish(**request)

    with pytest.raises(ProductionConflict) as exc_info:
        _apply_quick_finish(
            **request,
            force=True,
            override_reason="Confirmação tardia de outra tela",
        )

    assert exc_info.value.data["cause"] == "idempotency_conflict"
    receipt = IdempotencyKey.objects.get(
        scope=production.QUICK_FINISH_RECEIPT_SCOPE,
        key=request["idempotency_key"],
    )
    assert receipt.status == "done"
    assert receipt.response_body["force"] is False
    assert receipt.response_body["effective_force"] is False
    assert not WorkOrderEvent.objects.filter(
        work_order__ref=work_order_ref,
        kind=WorkOrderEvent.Kind.SHORTAGE_OVERRIDDEN,
    ).exists()


@pytest.mark.django_db
def test_quick_finish_transient_failure_before_plan_releases_execution_lease(
    recipe,
    monkeypatch,
):
    request = {
        "recipe_id": recipe.pk,
        "quantity": "3",
        "position_id": "",
        "actor": "production:op",
        "idempotency_key": "quick-pre-plan-failure",
    }
    original = production.production_core.replay_quick_plan
    monkeypatch.setattr(
        production.production_core,
        "replay_quick_plan",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("transient")),
    )

    with pytest.raises(RuntimeError, match="transient"):
        _apply_quick_finish(**request)

    receipt = IdempotencyKey.objects.get(
        scope=production.QUICK_FINISH_RECEIPT_SCOPE,
        key=request["idempotency_key"],
    )
    assert receipt.response_body["phase"] == "accepted"
    assert receipt.response_body["execution_force"] is None

    monkeypatch.setattr(production.production_core, "replay_quick_plan", original)
    _, work_order_ref, _ = _apply_quick_finish(**request)
    assert WorkOrder.objects.get(ref=work_order_ref).status == WorkOrder.Status.FINISHED


@pytest.mark.django_db
def test_quick_finish_reconciles_a_finish_committed_before_receipt_completion(
    recipe,
    monkeypatch,
):
    request = {
        "recipe_id": recipe.pk,
        "quantity": "3",
        "position_id": "",
        "actor": "production:op",
        "idempotency_key": "quick-reconcile-committed-finish",
    }
    original = production._complete_quick_finish_receipt
    monkeypatch.setattr(
        production,
        "_complete_quick_finish_receipt",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("receipt write lost")),
    )

    with pytest.raises(RuntimeError, match="receipt write lost"):
        _apply_quick_finish(**request)

    stranded = IdempotencyKey.objects.get(
        scope=production.QUICK_FINISH_RECEIPT_SCOPE,
        key=request["idempotency_key"],
    )
    assert stranded.response_body["phase"] == "executing"
    work_order = WorkOrder.objects.get(ref=stranded.response_body["work_order_ref"])
    assert work_order.status == WorkOrder.Status.FINISHED

    monkeypatch.setattr(production, "_complete_quick_finish_receipt", original)
    replay = _apply_quick_finish(**request)

    stranded.refresh_from_db()
    assert replay == (recipe.output_sku, work_order.ref, Decimal("3"))
    assert stranded.status == "done"
    assert stranded.response_body["phase"] == "finished"
    assert WorkOrder.objects.filter(recipe=recipe).count() == 1


@pytest.mark.django_db
def test_quick_finish_reclaims_an_expired_lease_before_plan(recipe):
    request = {
        "recipe_id": recipe.pk,
        "quantity": "3",
        "position_id": "",
        "actor": "production:op",
        "idempotency_key": "quick-expired-before-plan",
    }
    attempt = production._quick_finish_attempt(
        recipe_id=request["recipe_id"],
        quantity=request["quantity"],
        position_id=request["position_id"],
        partition=None,
    )
    receipt_pk, replay, first_token = production._claim_quick_finish_receipt(
        idempotency_key=request["idempotency_key"],
        attempt=attempt,
        actor=request["actor"],
        force=False,
        override_reason="",
    )
    assert replay is None
    assert first_token

    receipt = IdempotencyKey.objects.get(pk=receipt_pk)
    receipt.response_body = {
        **receipt.response_body,
        "execution_started_at": (
            timezone.now() - timedelta(seconds=production.QUICK_FINISH_EXECUTION_LEASE_SECONDS + 1)
        ).isoformat(),
    }
    receipt.save(update_fields=["response_body"])

    result = _apply_quick_finish(**request)

    receipt.refresh_from_db()
    work_order = WorkOrder.objects.get(ref=result[1])
    assert result == (recipe.output_sku, work_order.ref, Decimal("3"))
    assert work_order.status == WorkOrder.Status.FINISHED
    assert receipt.status == "done"
    assert receipt.response_body["execution_token"] != first_token
    assert WorkOrder.objects.filter(recipe=recipe).count() == 1


@pytest.mark.django_db
def test_quick_finish_tolerates_retry_reconciliation_before_original_completion(
    recipe,
    monkeypatch,
):
    request = {
        "recipe_id": recipe.pk,
        "quantity": "3",
        "position_id": "",
        "actor": "production:op",
        "idempotency_key": "quick-reconcile-interleaving",
    }
    attempt = production._quick_finish_attempt(
        recipe_id=request["recipe_id"],
        quantity=request["quantity"],
        position_id=request["position_id"],
        partition=None,
    )
    original = production._complete_quick_finish_receipt

    def reconcile_then_complete(receipt_pk, **facts):
        claimed_pk, replay, token = production._claim_quick_finish_receipt(
            idempotency_key=request["idempotency_key"],
            attempt=attempt,
            actor=request["actor"],
            force=False,
            override_reason="",
        )
        assert claimed_pk == receipt_pk
        assert replay is not None
        assert token is None
        original(receipt_pk, **facts)

    monkeypatch.setattr(
        production,
        "_complete_quick_finish_receipt",
        reconcile_then_complete,
    )

    result = _apply_quick_finish(**request)

    receipt = IdempotencyKey.objects.get(
        scope=production.QUICK_FINISH_RECEIPT_SCOPE,
        key=request["idempotency_key"],
    )
    assert result[0] == recipe.output_sku
    assert result[2] == Decimal("3")
    assert receipt.status == "done"
    assert receipt.response_body["phase"] == "finished"
    assert WorkOrder.objects.filter(recipe=recipe).count() == 1


@pytest.mark.django_db
def test_quick_finish_retry_cannot_change_the_frozen_partition(recipe, monkeypatch):
    missing = [
        MissingMaterial(
            sku="FARINHA",
            needed=Decimal("5"),
            available=Decimal("2"),
        )
    ]
    monkeypatch.setattr(production, "check_finish_materials", lambda order: missing)
    request = {
        "recipe_id": recipe.pk,
        "quantity": "3",
        "position_id": "",
        "actor": "production:op",
        "partition": [{"quantity": "3", "quality_grade_ref": "standard"}],
        "idempotency_key": "quick-frozen-partition",
    }

    with pytest.raises(ProductionStockShortError):
        _apply_quick_finish(**request)

    with pytest.raises(ProductionConflict) as exc_info:
        _apply_quick_finish(
            **{
                **request,
                "partition": [{"quantity": "3", "quality_grade_ref": "minimal"}],
                "force": True,
                "override_reason": "Não pode trocar a verdade do QC",
            }
        )

    assert exc_info.value.data["cause"] == "idempotency_conflict"
    work_order = WorkOrder.objects.get(recipe=recipe)
    assert work_order.status == WorkOrder.Status.PLANNED
    assert WorkOrder.objects.filter(recipe=recipe).count() == 1


@pytest.mark.django_db
def test_quick_finish_invalid_quality_creates_no_work_order(recipe):
    with pytest.raises(production.ProductionError, match="Grau de qualidade desconhecido"):
        _apply_quick_finish(
            recipe_id=recipe.pk,
            quantity="3",
            position_id="",
            actor="production:op",
            partition=[{"quantity": "3", "quality_grade_ref": "inventado"}],
            idempotency_key="quick-invalid-quality",
        )

    assert not WorkOrder.objects.filter(recipe=recipe).exists()
    assert not IdempotencyKey.objects.filter(
        scope=production.QUICK_FINISH_RECEIPT_SCOPE,
        key="quick-invalid-quality",
    ).exists()


@pytest.mark.django_db
def test_quick_finish_without_default_grade_creates_no_work_order(recipe):
    from shopman.shop.models import QualityGrade

    QualityGrade.objects.filter(is_default=True).update(is_default=False)

    with pytest.raises(production.ProductionError, match="exatamente um grau padrão"):
        _apply_quick_finish(
            recipe_id=recipe.pk,
            quantity="3",
            position_id="",
            actor="production:op",
            idempotency_key="quick-no-default",
        )

    assert not WorkOrder.objects.filter(recipe=recipe).exists()
    assert not IdempotencyKey.objects.filter(
        scope=production.QUICK_FINISH_RECEIPT_SCOPE,
        key="quick-no-default",
    ).exists()


@pytest.mark.django_db
def test_apply_finish_creates_stock_short_alert_after_rollback(recipe, monkeypatch):
    calls = []
    work_order = craft.plan(recipe, 1, date=date.today())
    craft.start(work_order, quantity=1, expected_rev=work_order.rev)

    def fail(*args, **kwargs):
        raise RuntimeError("estoque insuficiente")

    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    # resolve_partition consulta o catálogo (DB); estes testes são unitários do
    # caminho de erro do finish — a partição entra pronta.
    monkeypatch.setattr(
        production,
        "resolve_partition",
        lambda wo, **kw: ([{"item_ref": wo.output_sku, "quantity": "1"}], []),
    )
    monkeypatch.setattr(production.production_core, "finish_work_order", fail)
    monkeypatch.setattr(
        production,
        "_create_stock_short_alert",
        lambda **kwargs: calls.append(kwargs),
    )

    with pytest.raises(RuntimeError):
        _apply_finish(
            work_order_id=work_order.pk,
            quantity="1",
            actor="production:op",
        )

    assert calls == [{"work_order_id": work_order.pk, "error": "estoque insuficiente"}]


@pytest.mark.django_db
def test_apply_finish_does_not_alert_for_non_stock_errors(recipe, monkeypatch):
    calls = []
    work_order = craft.plan(recipe, 1, date=date.today())
    craft.start(work_order, quantity=1, expected_rev=work_order.rev)

    def fail(*args, **kwargs):
        raise RuntimeError("erro genérico")

    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    # resolve_partition consulta o catálogo (DB); estes testes são unitários do
    # caminho de erro do finish — a partição entra pronta.
    monkeypatch.setattr(
        production,
        "resolve_partition",
        lambda wo, **kw: ([{"item_ref": wo.output_sku, "quantity": "1"}], []),
    )
    monkeypatch.setattr(production.production_core, "finish_work_order", fail)
    monkeypatch.setattr(
        production,
        "_create_stock_short_alert",
        lambda **kwargs: calls.append(kwargs),
    )

    with pytest.raises(RuntimeError):
        _apply_finish(
            work_order_id=work_order.pk,
            quantity="1",
            actor="production:op",
        )

    assert calls == []


@pytest.mark.django_db
def test_apply_finish_blocks_when_materials_are_missing(recipe, monkeypatch):
    work_order = craft.plan(recipe, 10, date=date.today())
    craft.start(work_order, quantity=10, expected_rev=work_order.rev)
    missing = [MissingMaterial(sku="FARINHA", needed=Decimal("5"), available=Decimal("2"))]
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: missing)

    with pytest.raises(ProductionStockShortError) as exc:
        _apply_finish(work_order_id=work_order.pk, quantity="10", actor="production:op")

    assert exc.value.missing == missing
    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.STARTED


@pytest.mark.django_db
def test_apply_finish_fails_closed_when_inventory_backend_is_unavailable(
    recipe,
    monkeypatch,
):
    work_order = craft.plan(recipe, 10, date=date.today())
    craft.start(work_order, quantity=10, expected_rev=work_order.rev)

    class BrokenInventoryBackend:
        def available(self, needs):
            raise RuntimeError("inventory offline")

    monkeypatch.setattr(
        production,
        "_material_needs_for_work_order",
        lambda order: [object()],
    )
    monkeypatch.setattr(
        "django.utils.module_loading.import_string",
        lambda path: BrokenInventoryBackend,
    )

    with pytest.raises(
        production.ProductionError,
        match="Falha ao consultar estoque de insumos",
    ):
        _apply_finish(
            work_order_id=work_order.pk,
            quantity="10",
            actor="production:op",
            expected_rev=work_order.rev,
            idempotency_key="inventory-backend-offline",
        )

    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.STARTED
    assert not WorkOrderItem.objects.filter(
        work_order=work_order,
        kind__in=(WorkOrderItem.Kind.OUTPUT, WorkOrderItem.Kind.WASTE),
    ).exists()
    assert not Batch.objects.exists()


@pytest.mark.django_db
def test_apply_finish_force_creates_stock_short_alert(recipe, monkeypatch):
    work_order = craft.plan(recipe, 10, date=date.today())
    craft.start(work_order, quantity=10, expected_rev=work_order.rev)
    missing = [MissingMaterial(sku="FARINHA", needed=Decimal("5"), available=Decimal("2"))]
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: missing)

    _apply_finish(
        work_order_id=work_order.pk,
        quantity="9",
        actor="production:op",
        force=True,
        override_reason="Falta confirmada pelo responsável",
        approved_shortage=production.production_shortage_snapshot(
            ProductionStockShortError(work_order_ref=work_order.ref, missing=missing)
        ),
    )

    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.FINISHED
    assert OperatorAlert.objects.filter(type="production_stock_short", order_ref=work_order.ref).exists()
    override = WorkOrderEvent.objects.get(
        work_order=work_order,
        kind=WorkOrderEvent.Kind.SHORTAGE_OVERRIDDEN,
    )
    assert override.actor == "production:op"
    assert override.payload["work_order_rev"] == work_order.rev
    assert override.payload["reason"] == "Falta confirmada pelo responsável"
    assert override.payload["impact"] == {
        "kind": "material_shortage",
        "missing": [
            {
                "sku": "FARINHA",
                "needed": "5",
                "available": "2",
                "shortage": "3",
            }
        ],
    }


@pytest.mark.django_db
def test_stale_forced_finish_creates_no_override_fact_or_alert(recipe, monkeypatch):
    work_order = craft.plan(recipe, 10, date=date.today())
    craft.start(work_order, quantity=10, expected_rev=work_order.rev)
    missing = [
        MissingMaterial(
            sku="FARINHA",
            needed=Decimal("5"),
            available=Decimal("2"),
        )
    ]
    alerts = []
    monkeypatch.setattr(production, "check_finish_materials", lambda order: missing)
    monkeypatch.setattr(
        production,
        "_create_stock_short_alert",
        lambda **kwargs: alerts.append(kwargs),
    )

    with pytest.raises(production.ProductionConflict):
        _apply_finish(
            work_order_id=work_order.pk,
            quantity="9",
            actor="production:op",
            force=True,
            override_reason="Pedido stale não pode deixar auditoria",
            expected_rev=0,
            idempotency_key="stale-force",
        )

    assert alerts == []
    assert not WorkOrderEvent.objects.filter(
        work_order=work_order,
        kind=WorkOrderEvent.Kind.SHORTAGE_OVERRIDDEN,
    ).exists()


@pytest.mark.django_db
def test_apply_finish_records_batch_traceability(monkeypatch):
    recipe = Recipe.objects.create(
        ref="svc-batch-v1",
        name="Serviço Lote",
        output_sku="SVC-BATCH",
        batch_size=Decimal("10"),
        meta={"requires_batch_tracking": True, "shelf_life_days": 2},
    )
    work_order = craft.plan(recipe, 10, date=date.today())
    craft.start(work_order, quantity=10, expected_rev=work_order.rev)
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])

    _apply_finish(work_order_id=work_order.pk, quantity="8", actor="production:op")

    # O lote sai da LINHA de OUTPUT, não de WorkOrder.meta (ADR-017 §5): a
    # fórmula no meta só admitia um lote por ordem.
    line = WorkOrderItem.objects.get(work_order=work_order, kind=WorkOrderItem.Kind.OUTPUT)
    assert line.batch_ref.startswith("SVC-BATCH-")
    batch = Batch.objects.get(ref=line.batch_ref, sku="SVC-BATCH")
    assert batch.expiry_date == date.today() + production.timedelta(days=2)
    work_order.refresh_from_db()
    assert "batch_ref" not in (work_order.meta or {})


@pytest.mark.django_db
def test_batch_traceability_failure_rolls_back_finish_and_alerts(recipe, monkeypatch):
    work_order = craft.plan(recipe, 4, date=date.today())
    craft.start(work_order, quantity=4, expected_rev=work_order.rev)
    monkeypatch.setattr(production, "check_finish_materials", lambda order: [])

    def fail_batch(*args, **kwargs):
        raise RuntimeError("batch storage unavailable")

    monkeypatch.setattr(Batch.objects, "update_or_create", fail_batch)

    with pytest.raises(
        production.ProductionBatchTraceabilityError,
        match="rastreabilidade do lote falhou",
    ):
        _apply_finish(
            work_order_id=work_order.pk,
            quantity="4",
            actor="production:op",
            idempotency_key="batch-write-failure",
        )

    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.STARTED
    assert not WorkOrderItem.objects.filter(
        work_order=work_order,
        kind__in=(WorkOrderItem.Kind.OUTPUT, WorkOrderItem.Kind.WASTE),
    ).exists()
    assert OperatorAlert.objects.filter(
        type="production_batch_traceability",
        order_ref=work_order.ref,
    ).exists()


# ── qualidade da fornada (derivada das linhas — ADR-017) ─────────────


@pytest.mark.django_db
def test_finish_quality_lands_on_the_output_line(recipe):
    _, wo_ref, _, _ = _apply_planned(
        recipe_id=recipe.pk,
        quantity="10",
        target_date_value=date.today().isoformat(),
        actor="production:op",
    )
    work_order = WorkOrder.objects.get(ref=wo_ref)
    _apply_start(work_order_id=work_order.pk, quantity="10", actor="production:op")
    _apply_finish(
        work_order_id=work_order.pk,
        quantity="10",
        actor="production:op",
        quality="excellent",
    )

    line = WorkOrderItem.objects.get(work_order=work_order, kind=WorkOrderItem.Kind.OUTPUT)
    assert line.quality_grade_ref == "excellent"
    work_order.refresh_from_db()
    assert "quality" not in (work_order.meta or {})  # meta["quality"] morreu


@pytest.mark.django_db
def test_quality_is_derivable_at_the_finish_signal(recipe):
    """A campanha deriva a qualidade das linhas no production_changed do finish.

    As linhas precisam estar gravadas quando o signal dispara — senão a regra
    ``quality_min`` avaliaria uma fornada sem partição.
    """
    seen = {}

    def _spy(sender, product_ref, date, action, work_order, **kwargs):
        if action == "finished":
            from shopman.shop.services import quality as quality_service

            seen["quality"] = quality_service.derived_quality(work_order)

    from shopman.craftsman.signals import production_changed

    production_changed.connect(_spy, weak=False)
    try:
        _, wo_ref, _, _ = _apply_planned(
            recipe_id=recipe.pk,
            quantity="5",
            target_date_value=date.today().isoformat(),
            actor="production:op",
        )
        work_order = WorkOrder.objects.get(ref=wo_ref)
        _apply_start(work_order_id=work_order.pk, quantity="5", actor="production:op")
        _apply_finish(
            work_order_id=work_order.pk,
            quantity="5",
            actor="production:op",
            quality="excellent",
        )
    finally:
        production_changed.disconnect(_spy)

    assert seen["quality"] == "excellent"


@pytest.mark.django_db
def test_finish_without_quality_defaults_to_catalog_default(recipe):
    """O operador pode fechar sem pensar; o default não bloqueia nada."""
    _, wo_ref, _, _ = _apply_planned(
        recipe_id=recipe.pk,
        quantity="4",
        target_date_value=date.today().isoformat(),
        actor="production:op",
    )
    work_order = WorkOrder.objects.get(ref=wo_ref)
    _apply_start(work_order_id=work_order.pk, quantity="4", actor="production:op")
    _apply_finish(work_order_id=work_order.pk, quantity="4", actor="production:op")

    line = WorkOrderItem.objects.get(work_order=work_order, kind=WorkOrderItem.Kind.OUTPUT)
    assert line.quality_grade_ref == "standard"


@pytest.mark.django_db
def test_unknown_quality_is_rejected(recipe):
    _, wo_ref, _, _ = _apply_planned(
        recipe_id=recipe.pk,
        quantity="2",
        target_date_value=date.today().isoformat(),
        actor="production:op",
    )
    work_order = WorkOrder.objects.get(ref=wo_ref)
    _apply_start(work_order_id=work_order.pk, quantity="2", actor="production:op")
    with pytest.raises(production.ProductionError, match="Grau de qualidade desconhecido"):
        _apply_finish(
            work_order_id=work_order.pk,
            quantity="2",
            actor="production:op",
            quality="sublime",
        )


@pytest.mark.django_db
def test_unknown_or_inactive_defect_is_rejected(recipe):
    from shopman.shop.models import QualityDefect, QualityGrade

    work_order = craft.plan(recipe, 2, date=date.today())
    craft.start(work_order, quantity=2, expected_rev=0)

    with pytest.raises(production.ProductionError, match="Defeito de qualidade desconhecido"):
        production.resolve_partition(
            work_order,
            quantity="2",
            partition=[
                {
                    "quantity": "2",
                    "quality_grade_ref": "standard",
                    "quality_defect_ref": "inventado",
                }
            ],
        )

    defect = QualityDefect.objects.get(ref="misshapen")
    defect.is_active = False
    defect.save(update_fields=["is_active"])
    with pytest.raises(production.ProductionError, match="Defeito de qualidade inativo"):
        production.resolve_partition(
            work_order,
            quantity="2",
            partition=[
                {
                    "quantity": "2",
                    "quality_grade_ref": "standard",
                    "quality_defect_ref": defect.ref,
                }
            ],
        )

    grade = QualityGrade.objects.get(ref="fair")
    grade.is_active = False
    grade.save(update_fields=["is_active"])
    with pytest.raises(production.ProductionError, match="Grau de qualidade inativo"):
        production.resolve_partition(
            work_order,
            quantity="2",
            partition=[{"quantity": "2", "quality_grade_ref": grade.ref}],
        )


@pytest.mark.django_db
def test_partition_splits_lots_and_veto_goes_to_waste(recipe, monkeypatch):
    """A fornada de 10 que produz 6+3+1: dois lotes e uma perda vetada (ADR-017).

    O grupo com desconto grava o percentual RESOLVIDO no lote (congela); o
    grupo vetado (contaminated) nunca vira lote — vira WASTE com o motivo.
    """
    recipe.meta = {"requires_batch_tracking": True, "shelf_life_days": 1}
    recipe.save(update_fields=["meta"])
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])

    _, wo_ref, _, _ = _apply_planned(
        recipe_id=recipe.pk,
        quantity="10",
        target_date_value=date.today().isoformat(),
        actor="production:op",
    )
    work_order = WorkOrder.objects.get(ref=wo_ref)
    _apply_start(work_order_id=work_order.pk, quantity="10", actor="production:op")
    _apply_finish(
        work_order_id=work_order.pk,
        quantity="10",
        actor="production:op",
        partition=[
            {"quantity": "6", "quality_grade_ref": "standard"},
            {"quantity": "3", "quality_grade_ref": "minimal", "quality_defect_ref": "overbaked"},
            {"quantity": "1", "quality_defect_ref": "contaminated"},
        ],
    )

    outputs = WorkOrderItem.objects.filter(work_order=work_order, kind=WorkOrderItem.Kind.OUTPUT).order_by("batch_ref")
    assert outputs.count() == 2
    full, marked = outputs
    assert full.quality_grade_ref == "standard"
    assert marked.quality_grade_ref == "minimal"
    assert marked.batch_ref == f"{full.batch_ref}-2"

    # Dois lotes; o marcado congela o percentual do grau e o motivo do defeito.
    full_batch = Batch.objects.get(ref=full.batch_ref)
    marked_batch = Batch.objects.get(ref=marked.batch_ref)
    assert full_batch.nonconformity_percent == 0
    assert marked_batch.nonconformity_percent == 50
    assert marked_batch.nonconformity_reason == "Assou demais"

    # O veto virou perda com o motivo, nunca lote.
    waste = WorkOrderItem.objects.get(work_order=work_order, kind=WorkOrderItem.Kind.WASTE)
    assert waste.quality_defect_ref == "contaminated"
    assert waste.quantity == Decimal("1")

    work_order.refresh_from_db()
    assert work_order.finished == Decimal("9")  # 6 + 3; a perda fica fora


@pytest.mark.django_db
def test_long_output_sku_produces_distinct_batch_refs_within_storage_limit(
    recipe,
    monkeypatch,
):
    recipe.output_sku = "SKU-" + ("X" * 96)
    recipe.meta = {"requires_batch_tracking": True}
    recipe.save(update_fields=["output_sku", "meta", "updated_at"])
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    work_order = craft.plan(recipe, 2, date=date.today())
    craft.start(work_order, quantity=2, expected_rev=work_order.rev)

    _apply_finish(
        work_order_id=work_order.pk,
        quantity="2",
        actor="production:op",
        partition=[
            {"quantity": "1", "quality_grade_ref": "standard"},
            {"quantity": "1", "quality_grade_ref": "minimal"},
        ],
    )

    refs = list(
        WorkOrderItem.objects.filter(
            work_order=work_order,
            kind=WorkOrderItem.Kind.OUTPUT,
        ).values_list("batch_ref", flat=True)
    )
    assert len(refs) == len(set(refs)) == 2
    assert all(len(ref) <= 50 for ref in refs)
    assert Batch.objects.filter(ref__in=refs).count() == 2


@pytest.mark.django_db
def test_partition_declared_loss_becomes_waste_with_reason(recipe, monkeypatch):
    """Perda declarada (loss=True) vira WASTE com o motivo, sem grau e sem lote.

    A aritmética do quiosque: previsto = a preço cheio + com desconto + perda
    (QC-FORNADA §4). A perda não passa por veto — é o que não saiu do forno,
    e pede motivo mesmo quando o defeito não é de segurança alimentar.
    """
    recipe.meta = {"requires_batch_tracking": True, "shelf_life_days": 1}
    recipe.save(update_fields=["meta"])
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])

    _, wo_ref, _, _ = _apply_planned(
        recipe_id=recipe.pk,
        quantity="40",
        target_date_value=date.today().isoformat(),
        actor="production:op",
    )
    work_order = WorkOrder.objects.get(ref=wo_ref)
    _apply_start(work_order_id=work_order.pk, quantity="40", actor="production:op")
    _apply_finish(
        work_order_id=work_order.pk,
        quantity="40",
        actor="production:op",
        partition=[
            {"quantity": "32", "quality_grade_ref": "standard"},
            {"quantity": "5", "quality_grade_ref": "minimal", "quality_defect_ref": "underbaked"},
            {"quantity": "3", "quality_defect_ref": "overbaked", "loss": True},
        ],
    )

    outputs = WorkOrderItem.objects.filter(work_order=work_order, kind=WorkOrderItem.Kind.OUTPUT)
    assert outputs.count() == 2
    assert Batch.objects.filter(ref__in=[line.batch_ref for line in outputs]).count() == 2

    waste = WorkOrderItem.objects.get(work_order=work_order, kind=WorkOrderItem.Kind.WASTE)
    assert waste.quantity == Decimal("3")
    assert waste.quality_defect_ref == "overbaked"
    assert waste.quality_grade_ref == ""
    assert waste.batch_ref == ""

    work_order.refresh_from_db()
    assert work_order.finished == Decimal("37")  # 32 + 5; a perda fica fora


@pytest.mark.django_db
def test_partition_declared_loss_without_reason_fails_closed(recipe, monkeypatch):
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    work_order = craft.plan(recipe, 10, date=date.today())
    craft.start(work_order, quantity=10, expected_rev=work_order.rev)

    with pytest.raises(production.ProductionError, match="exige um motivo"):
        _apply_finish(
            work_order_id=work_order.pk,
            quantity="10",
            actor="production:op",
            partition=[
                {"quantity": "8", "quality_grade_ref": "standard"},
                {"quantity": "2", "loss": True},
            ],
        )

    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.STARTED
    assert not WorkOrderItem.objects.filter(
        work_order=work_order,
        kind__in=(WorkOrderItem.Kind.OUTPUT, WorkOrderItem.Kind.WASTE),
    ).exists()


@pytest.mark.django_db
def test_finish_overshoot_requires_confirmation_and_reason_under_lock(recipe, monkeypatch):
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    work_order = craft.plan(recipe, 10, date=date.today())
    craft.start(work_order, quantity=10, expected_rev=work_order.rev)
    request = {
        "work_order_id": work_order.pk,
        "quantity": "12",
        "actor": "production:op",
        "expected_rev": work_order.rev,
        "idempotency_key": "overshoot-confirmation",
    }

    with pytest.raises(production.ProductionError, match="Confirme explicitamente"):
        _apply_finish(**request)
    with pytest.raises(production.ProductionError, match="Informe o motivo"):
        _apply_finish(**request, yield_deviation_confirmed=True)
    with pytest.raises(production.ProductionError, match="Confirme explicitamente"):
        _apply_finish(
            **{
                **request,
                "quantity": "15",
                "idempotency_key": "overshoot-with-waste",
            },
            partition=[
                {"quantity": "10", "quality_grade_ref": "standard"},
                {
                    "quantity": "5",
                    "quality_defect_ref": "overbaked",
                    "loss": True,
                },
            ],
        )

    result = _apply_finish(
        **request,
        yield_deviation_confirmed=True,
        yield_deviation_reason="Contagem dupla conferida; unidades menores que o padrão",
    )

    assert result == (work_order.ref, Decimal("12"))
    work_order.refresh_from_db()
    event = WorkOrderEvent.objects.get(
        work_order=work_order,
        kind=WorkOrderEvent.Kind.FINISHED,
    )
    assert event.actor == "production:op"
    assert event.payload["context"]["yield_deviation"] == {
        "kind": "yield_overshoot",
        "anchor_qty": "10",
        "reported_qty": "12",
        "saleable_qty": "12",
        "deviation_qty": "2",
        "confirmed": True,
        "reason": "Contagem dupla conferida; unidades menores que o padrão",
        "actor": "production:op",
    }


@pytest.mark.django_db
def test_partition_with_only_loss_is_rejected(recipe, monkeypatch):
    """Fornada sem grupo vendável não fecha como conclusão — é void/waste."""
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    _, wo_ref, _, _ = _apply_planned(
        recipe_id=recipe.pk,
        quantity="4",
        target_date_value=date.today().isoformat(),
        actor="production:op",
    )
    work_order = WorkOrder.objects.get(ref=wo_ref)
    _apply_start(work_order_id=work_order.pk, quantity="4", actor="production:op")
    with pytest.raises(production.ProductionError):
        _apply_finish(
            work_order_id=work_order.pk,
            quantity="4",
            actor="production:op",
            partition=[{"quantity": "4", "quality_defect_ref": "overbaked", "loss": True}],
        )
