"""Qualidade em lote (P19, decisão do dono 03/10): os lotes sem exceção do dia
são confirmados num ato só, tudo ou nada; as exceções seguem uma a uma."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrderEvent
from shopman.stockman import Position

from shopman.backstage.projections.production import (
    build_qc_kiosk,
    qc_partition_is_clean,
    quality_review_batch_ref,
)
from shopman.backstage.services import production
from shopman.backstage.services.exceptions import ProductionConflict
from shopman.backstage.tests.production_grants import grant_production_operator
from shopman.backstage.tests.support import production_mutation_post

BATCH_URL = "/api/v1/backstage/production/quality-review/batch/"


@pytest.fixture
def recipes(db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja Qualidade em Lote")
    Position.objects.create(ref="forno-lote", name="Forno", is_default=True)
    Position.objects.create(ref="vitrine-lote", name="Vitrine", is_saleable=True)
    return [
        Recipe.objects.create(
            ref=f"lote-{index}",
            name=f"Pão {index}",
            output_sku=f"LOTE-{index}",
            batch_size=Decimal("10"),
            meta={"shelf_life_days": 3},
        )
        for index in range(4)
    ]


def _finished(recipe, monkeypatch, *, partition=None, quantity="10", started=10, target=None, actor="production:forneiro"):
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    wo = craft.plan(recipe, 10, date=target or date.today(), position_ref="forno-lote")
    craft.start(wo, quantity=started, position_ref="forno-lote", expected_rev=0)
    wo.refresh_from_db()
    production.apply_finish(
        work_order_id=wo.pk,
        quantity=quantity,
        actor=actor,
        expected_rev=wo.rev,
        idempotency_key=f"finish-{wo.pk}",
        partition=partition or [{"quantity": quantity, "quality_grade_ref": "standard"}],
        yield_deviation_confirmed=Decimal(quantity) > started,
        yield_deviation_reason="Contagem conferida." if Decimal(quantity) > started else "",
    )
    wo.refresh_from_db()
    return wo


def _manager(username="qc-lote-gerente"):
    user = grant_production_operator(User.objects.create_user(username, password="pw", is_staff=True))
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label="backstage", codename="correct_production_qc")
    )
    return User.objects.get(pk=user.pk)


def _reviews(*work_orders):
    return WorkOrderEvent.objects.filter(
        work_order__in=work_orders,
        kind=WorkOrderEvent.Kind.QUALITY_REVIEWED,
    )


def _batch_body(work_orders, key="batch-1", target=None):
    return {
        "target_date": (target or date.today()).isoformat(),
        "items": [{"work_order_id": wo.pk, "expected_rev": wo.rev} for wo in work_orders],
        "idempotency_key": key,
    }


def test_clean_rule_is_strict():
    standard = {"quantity": "10", "quality_grade_ref": "standard", "markdown_percent": 0}
    assert qc_partition_is_clean([standard], anchor=Decimal("10"), default_grade_ref="standard")
    # Contagem diferente do que entrou, perda, desconto, outro grau, defeito,
    # partição vazia e âncora ausente: tudo é exceção.
    assert not qc_partition_is_clean([standard], anchor=Decimal("9"), default_grade_ref="standard")
    assert not qc_partition_is_clean(
        [{**standard, "quantity": "8"}, {"quantity": "2", "loss": True, "quality_defect_ref": "x"}],
        anchor=Decimal("10"),
        default_grade_ref="standard",
    )
    assert not qc_partition_is_clean([{**standard, "markdown_percent": 30}], anchor=10, default_grade_ref="standard")
    assert not qc_partition_is_clean([{**standard, "quality_grade_ref": "fair"}], anchor=10, default_grade_ref="standard")
    assert not qc_partition_is_clean([{**standard, "quality_defect_ref": "x"}], anchor=10, default_grade_ref="standard")
    assert not qc_partition_is_clean([], anchor=10, default_grade_ref="standard")
    assert not qc_partition_is_clean([standard], anchor=None, default_grade_ref="standard")


@pytest.mark.django_db
def test_projection_splits_clean_lots_from_exceptions_and_offers_one_batch_action(recipes, monkeypatch):
    clean_a = _finished(recipes[0], monkeypatch, actor="production:rafael")
    clean_b = _finished(recipes[1], monkeypatch)
    loss = _finished(
        recipes[2],
        monkeypatch,
        partition=[
            {"quantity": "8", "quality_grade_ref": "standard"},
            {"quantity": "2", "quality_defect_ref": "underproofed", "loss": True},
        ],
    )
    discounted = _finished(
        recipes[3],
        monkeypatch,
        partition=[{"quantity": "10", "quality_grade_ref": "fair", "quality_defect_ref": "misshapen"}],
    )
    User.objects.create_user("rafael", first_name="Rafael")

    kiosk = build_qc_kiosk(selected_date=date.today())
    cards = {card.pk: card for card in kiosk.orders}

    assert cards[clean_a.pk].quality_exception is False
    assert cards[clean_b.pk].quality_exception is False
    assert cards[loss.pk].quality_exception is True
    assert cards[discounted.pk].quality_exception is True
    assert cards[clean_a.pk].closed_by == "Rafael"
    assert cards[clean_b.pk].closed_by == "forneiro"
    assert cards[clean_a.pk].closed_at_display

    batch = [action for action in kiosk.actions if action.kind == "review_qc_batch"]
    assert len(batch) == 1
    assert batch[0].enabled is True
    assert batch[0].label == "2 lotes, nenhuma exceção · Confirmar"
    assert batch[0].ref == quality_review_batch_ref(
        [{"work_order_id": wo.pk, "expected_rev": wo.rev} for wo in (clean_a, clean_b)]
    )
    # A confirmação individual continua existindo para quem olha um a um.
    assert any(action.ref == f"review_qc:{loss.pk}" for action in kiosk.actions)


@pytest.mark.django_db
def test_overshoot_count_is_an_exception(recipes, monkeypatch):
    overshoot = _finished(recipes[0], monkeypatch, quantity="11", started=10)
    card = next(card for card in build_qc_kiosk(selected_date=date.today()).orders if card.pk == overshoot.pk)
    assert card.quality_exception is True
    assert not any(action.kind == "review_qc_batch" for action in build_qc_kiosk().actions)


@pytest.mark.django_db
def test_projection_reports_the_me_avise_queue_and_typical_loss(recipes, monkeypatch):
    from shopman.storefront.services import stock_alerts

    for days in (3, 2, 1):
        _finished(
            recipes[0],
            monkeypatch,
            target=date.today() - timedelta(days=days),
            partition=[
                {"quantity": "9", "quality_grade_ref": "standard"},
                {"quantity": "1", "quality_defect_ref": "underproofed", "loss": True},
            ],
        )
    stock_alerts.subscribe(
        recipes[0].output_sku, phone="+5543999990001", alert_type="production_ready", adult_declared=True
    )
    stock_alerts.subscribe(
        recipes[0].output_sku, phone="+5543999990002", alert_type="production_ready", adult_declared=True
    )
    today = _finished(recipes[0], monkeypatch)

    card = next(card for card in build_qc_kiosk(selected_date=date.today()).orders if card.pk == today.pk)
    assert card.alert_waiting_count == 2
    assert card.typical_loss_qty == "1"


@pytest.mark.django_db
def test_batch_confirms_every_clean_lot_with_the_same_record_as_one_by_one(client, recipes, monkeypatch):
    lots = [_finished(recipe, monkeypatch) for recipe in recipes[:3]]
    client.force_login(_manager())

    response = production_mutation_post(client, BATCH_URL, _batch_body(lots), content_type="application/json")

    assert response.status_code == 200, response.content
    assert response.json()["reviewed_count"] == 3
    events = list(_reviews(*lots))
    assert len(events) == 3
    for event in events:
        assert event.actor == "production:qc-lote-gerente"
        assert event.payload["attempt"]["work_order_id"] == event.work_order_id
        assert event.idempotency_key == f"production.quality-review:{event.work_order_id}:batch-1"
    kiosk = build_qc_kiosk(selected_date=date.today())
    assert all(card.quality_reviewed for card in kiosk.orders)
    assert not any(action.kind == "review_qc_batch" for action in kiosk.actions)

    replay = production_mutation_post(client, BATCH_URL, _batch_body(lots), content_type="application/json")
    assert replay.status_code == 200, replay.content
    assert _reviews(*lots).count() == 3


@pytest.mark.django_db
def test_batch_is_all_or_nothing_on_a_stale_lot(recipes, monkeypatch):
    lots = [_finished(recipe, monkeypatch) for recipe in recipes[:3]]
    items = [{"work_order_id": wo.pk, "expected_rev": wo.rev} for wo in lots]
    items[2]["expected_rev"] = lots[2].rev - 1

    with pytest.raises(ProductionConflict):
        production.apply_quality_review_batch(
            items=items,
            target_date=date.today(),
            actor="production:gerente",
            idempotency_key="batch-stale",
        )

    assert not _reviews(*lots).exists()


@pytest.mark.django_db
def test_batch_refuses_a_lot_with_exception_and_saves_nothing(recipes, monkeypatch):
    clean = _finished(recipes[0], monkeypatch)
    loss = _finished(
        recipes[1],
        monkeypatch,
        partition=[
            {"quantity": "8", "quality_grade_ref": "standard"},
            {"quantity": "2", "quality_defect_ref": "underproofed", "loss": True},
        ],
    )

    with pytest.raises(ProductionConflict) as exc:
        production.apply_quality_review_batch(
            items=[{"work_order_id": wo.pk, "expected_rev": wo.rev} for wo in (clean, loss)],
            target_date=date.today(),
            actor="production:gerente",
            idempotency_key="batch-exception",
        )

    assert exc.value.data["cause"] == "quality_batch_has_exception"
    assert not _reviews(clean, loss).exists()


@pytest.mark.django_db
def test_batch_refuses_a_lot_from_another_day(recipes, monkeypatch):
    today = _finished(recipes[0], monkeypatch)
    yesterday = _finished(recipes[1], monkeypatch, target=date.today() - timedelta(days=1))

    with pytest.raises(ProductionConflict) as exc:
        production.apply_quality_review_batch(
            items=[{"work_order_id": wo.pk, "expected_rev": wo.rev} for wo in (today, yesterday)],
            target_date=date.today(),
            actor="production:gerente",
            idempotency_key="batch-date",
        )

    assert exc.value.data["cause"] == "quality_batch_wrong_date"
    assert not _reviews(today, yesterday).exists()


@pytest.mark.django_db
def test_batch_on_a_previous_day_uses_that_day_projection(client, recipes, monkeypatch):
    yesterday = date.today() - timedelta(days=1)
    lots = [_finished(recipe, monkeypatch, target=yesterday) for recipe in recipes[:2]]
    client.force_login(_manager())

    response = production_mutation_post(
        client, BATCH_URL, _batch_body(lots, key="batch-yesterday", target=yesterday), content_type="application/json"
    )

    assert response.status_code == 200, response.content
    assert _reviews(*lots).count() == 2


@pytest.mark.django_db
def test_batch_requires_the_same_capability_as_one_lot(client, recipes, monkeypatch):
    lots = [_finished(recipe, monkeypatch) for recipe in recipes[:2]]
    floor = grant_production_operator(User.objects.create_user("qc-lote-chao", password="pw", is_staff=True))
    client.force_login(floor)

    denied = production_mutation_post(client, BATCH_URL, _batch_body(lots), content_type="application/json")

    assert denied.status_code == 403
    assert not _reviews(*lots).exists()


@pytest.mark.django_db
def test_batch_rejects_a_set_different_from_the_projected_action(client, recipes, monkeypatch):
    lots = [_finished(recipe, monkeypatch) for recipe in recipes[:2]]
    client.force_login(_manager())

    class _Capture:
        session = client.session

        def post(self, path, body, **kwargs):
            self.body = body

    capture = _Capture()
    # Prova emitida para o conjunto de UM lote; o pedido tenta passar dois.
    production_mutation_post(capture, BATCH_URL, _batch_body(lots[:1], key="batch-forged"))
    forged = {**capture.body, "items": _batch_body(lots)["items"]}

    response = client.post(BATCH_URL, forged, content_type="application/json")

    assert response.status_code == 400, response.content
    assert not _reviews(*lots).exists()


@pytest.mark.django_db
def test_exception_lot_is_confirmed_one_by_one_and_correction_needs_a_real_reason(client, recipes, monkeypatch):
    loss = _finished(
        recipes[0],
        monkeypatch,
        partition=[
            {"quantity": "8", "quality_grade_ref": "standard"},
            {"quantity": "2", "quality_defect_ref": "underproofed", "loss": True},
        ],
    )
    client.force_login(_manager())
    url = reverse("api-backstage-wo-quality-correction", args=[loss.pk])
    partition = [
        {"quantity": "9", "quality_grade_ref": "standard"},
        {"quantity": "1", "quality_defect_ref": "underproofed", "loss": True},
    ]

    blank = production_mutation_post(
        client,
        url,
        {"expected_rev": loss.rev, "partition": partition, "reason": "  ", "idempotency_key": "fix-blank"},
        content_type="application/json",
    )
    assert blank.status_code == 400

    reason = "Uma peça estava na outra bandeja; conferida na vitrine."
    fixed = production_mutation_post(
        client,
        url,
        {"expected_rev": loss.rev, "partition": partition, "reason": reason, "idempotency_key": "fix-real"},
        content_type="application/json",
    )
    assert fixed.status_code == 200, fixed.content
    event = WorkOrderEvent.objects.get(work_order=loss, kind=WorkOrderEvent.Kind.QUALITY_CORRECTED)
    assert reason in str(event.payload)


@pytest.mark.django_db
def test_card_carries_the_output_unit_so_grams_are_not_summed_with_pieces(recipes, monkeypatch):
    """Lote de preparo medido em gramas e pão contado em peças chegam à tela
    com a unidade de cada um (UX-P1b): o cartão do conjunto limpo agrupa por ela."""
    from shopman.offerman.models import Product

    Product.objects.create(sku="LOTE-0", name="Pão 0", unit="un", base_price_q=1000)
    dough = Recipe.objects.create(
        ref="massa-lote",
        name="Massa Tradição",
        output_sku="MASSA-LOTE",
        batch_size=Decimal("1000"),
        meta={"output_unit": "g"},
    )
    bread = _finished(recipes[0], monkeypatch)
    dough_wo = _finished(dough, monkeypatch)

    cards = {card.pk: card for card in build_qc_kiosk(selected_date=date.today()).orders}

    assert cards[bread.pk].output_unit == "un"
    assert cards[dough_wo.pk].output_unit == "g"
