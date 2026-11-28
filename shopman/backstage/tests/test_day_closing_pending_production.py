"""Fechamento do dia com produção aberta (WP-PE0; regra do dono de 05/11/2026).

Produção aberta IMPEDE selar o dia. Quem fecha resolve na Produção (conclui ou
cancela as ordens) ou libera com a autorização de um gerente escolhido da lista,
com PIN e motivo. A liberação fica gravada no fechamento: quem pediu, quem
autorizou, quando, por quê e quais ordens. O pendente segue no snapshot.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe

from shopman.backstage.models import DayClosing
from shopman.backstage.projections.closing import build_day_closing
from shopman.backstage.services.closing import perform_day_closing

pytestmark = pytest.mark.django_db


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        ref="croissant",
        name="Croissant",
        output_sku="CROISSANT",
        batch_size=1,
    )


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="closer", password="x")


class TestPendingProductionProjection:
    def test_open_work_orders_appear(self, recipe):
        planned = craft.plan(recipe, 10, date=date.today())
        started = craft.plan(recipe, 5, date=date.today())
        craft.start(started, quantity=5)

        closing = build_day_closing()
        assert closing.has_pending_production
        by_ref = {row.ref: row for row in closing.pending_production}
        assert by_ref[planned.ref].status == "planned"
        assert by_ref[planned.ref].status_label == "Planejada"
        assert not by_ref[planned.ref].is_overdue
        assert by_ref[started.ref].status == "started"
        assert by_ref[started.ref].status_label == "Em produção"

    def test_overdue_planned_is_flagged(self, recipe):
        craft.plan(recipe, 10, date=date.today() - timedelta(days=1))
        closing = build_day_closing()
        assert closing.pending_production[0].is_overdue

    def test_target_date_travels_in_iso(self, recipe):
        """O link do PDV para a Produção precisa da DATA, não do rótulo.

        A grade da Produção recorta por `target_date` exato e abre em hoje por
        padrão; o fechamento lista ordens com `target_date <= hoje`, ou seja, a
        atrasada é de ontem. Sem a data em ISO, "Resolver na produção" levaria a
        uma grade onde a ordem prometida não aparece. O `target_date_display`
        ("21/09") não serve: não é o que a query string aceita.
        """
        ontem = date.today() - timedelta(days=1)
        craft.plan(recipe, 10, date=ontem)

        row = build_day_closing().pending_production[0]
        assert row.target_date == ontem.isoformat()
        assert row.target_date_display == ontem.strftime("%d/%m")

    def test_finished_and_voided_are_excluded(self, recipe):
        done = craft.plan(recipe, 10, date=date.today())
        craft.finish(order=done, finished=10)
        voided = craft.plan(recipe, 4, date=date.today())
        craft.void(order=voided, reason="teste")

        closing = build_day_closing()
        assert not closing.has_pending_production
        assert closing.pending_production == ()

    def test_future_planned_is_not_pending(self, recipe):
        craft.plan(recipe, 10, date=date.today() + timedelta(days=1))
        closing = build_day_closing()
        assert not closing.has_pending_production


class TestPendingProductionPage:
    def test_closing_page_shows_pending_block(self, recipe, client):
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType

        from shopman.shop.models import Shop

        Shop.objects.get_or_create(name="Test Shop")
        user = get_user_model().objects.create_user(
            username="closing-op", password="x", is_staff=True
        )
        ct = ContentType.objects.get_for_model(DayClosing)
        user.user_permissions.add(
            Permission.objects.get(content_type=ct, codename="perform_closing")
        )
        client.force_login(user)

        wo = craft.plan(recipe, 10, date=date.today() - timedelta(days=1))
        resp = client.get("/api/v1/backstage/closing/")

        assert resp.status_code == 200
        closing = resp.json()["closing"]
        assert closing["has_pending_production"] is True
        rows = closing["pending_production"]
        assert wo.ref in [row["ref"] for row in rows]
        assert any(row["is_overdue"] for row in rows)

    def test_closing_page_hides_block_without_pending(self, client):
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType

        from shopman.shop.models import Shop

        Shop.objects.get_or_create(name="Test Shop")
        user = get_user_model().objects.create_user(
            username="closing-op2", password="x", is_staff=True
        )
        ct = ContentType.objects.get_for_model(DayClosing)
        user.user_permissions.add(
            Permission.objects.get(content_type=ct, codename="perform_closing")
        )
        client.force_login(user)

        resp = client.get("/api/v1/backstage/closing/")
        assert resp.status_code == 200
        closing = resp.json()["closing"]
        assert closing["has_pending_production"] is False
        assert closing["pending_production"] == []


@pytest.fixture
def manager(db):
    from django.contrib.auth.models import Permission
    from shopman.doorman.models import PinCredential

    manager = get_user_model().objects.create_user(username="gerente", password="x", is_staff=True)
    manager.user_permissions.add(
        Permission.objects.get(content_type__app_label="cashman", codename="adjust_shift")
    )
    PinCredential.set_for(manager, "4321")
    return manager


def _release(manager, *, pin="4321", reason="Fornada da noite segue no forno"):
    return {"reason": reason, "manager_approval": {"username": manager.username, "pin": pin}}


class TestPendingProductionBlocks:
    """Beta 05/11 (PDV-06): o aviso dizia "conclua ou estorne antes de encerrar"
    e o selo passava assim mesmo."""

    def test_open_work_order_blocks_the_closing(self, recipe, user):
        from shopman.backstage.services.closing import PendingProductionBlocksClosing

        craft.plan(recipe, 10, date=date.today())

        with pytest.raises(PendingProductionBlocksClosing) as exc:
            perform_day_closing(user=user, items=[], quantities_by_sku={})

        assert "Uma ordem de produção segue aberta" in str(exc.value)
        assert not DayClosing.objects.exists()

    def test_release_needs_a_reason_before_the_pin(self, recipe, user, manager):
        from shopman.backstage.services.closing import PendingProductionBlocksClosing

        craft.plan(recipe, 10, date=date.today())

        with pytest.raises(PendingProductionBlocksClosing) as exc:
            perform_day_closing(user=user, items=[], quantities_by_sku={}, production_release=_release(manager, reason=" "))

        assert exc.value.field == "production_release.reason"
        assert not DayClosing.objects.exists()

    def test_release_with_a_wrong_pin_is_refused(self, recipe, user, manager):
        from shopman.shop.services.pos_intent import PosIntentError

        craft.plan(recipe, 10, date=date.today())

        with pytest.raises(PosIntentError) as exc:
            perform_day_closing(user=user, items=[], quantities_by_sku={}, production_release=_release(manager, pin="0000"))

        assert exc.value.code == "manager_approval_invalid"
        assert not DayClosing.objects.exists()

    def test_release_records_who_when_and_why(self, recipe, user, manager):
        wo = craft.plan(recipe, 10, date=date.today())

        perform_day_closing(user=user, items=[], quantities_by_sku={}, production_release=_release(manager))

        closing = DayClosing.objects.get()
        release = closing.data["pending_production_release"]
        assert release["approved_by"] == "gerente"
        assert release["approved_by_id"] == manager.pk
        assert release["requested_by"] == "closer"
        assert release["reason"] == "Fornada da noite segue no forno"
        assert release["at"]
        assert release["work_orders"] == [wo.ref]

    def test_api_answers_409_with_the_code(self, recipe, client):
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType

        from shopman.shop.models import Shop

        Shop.objects.get_or_create(name="Test Shop")
        closer = get_user_model().objects.create_user(username="closing-op3", password="x", is_staff=True)
        ct = ContentType.objects.get_for_model(DayClosing)
        closer.user_permissions.add(Permission.objects.get(content_type=ct, codename="perform_closing"))
        client.force_login(closer)
        craft.plan(recipe, 10, date=date.today())

        resp = client.post("/api/v1/backstage/closing/", {"quantities": {}}, content_type="application/json")

        assert resp.status_code == 409
        body = resp.json()
        assert body["error"]["code"] == "pending_production"
        assert body["field"] == "production_release"
        assert not DayClosing.objects.exists()


class TestPendingProductionSnapshot:
    def test_closing_snapshot_records_pending(self, recipe, user, manager):
        wo = craft.plan(recipe, 10, date=date.today())
        perform_day_closing(user=user, items=[], quantities_by_sku={}, production_release=_release(manager))

        closing = DayClosing.objects.get()
        pending = closing.data["pending_production"]
        assert len(pending) == 1
        assert pending[0]["ref"] == wo.ref
        assert pending[0]["status"] == "planned"
        assert pending[0]["output_sku"] == "CROISSANT"

    def test_snapshot_empty_when_no_pending(self, user):
        perform_day_closing(user=user, items=[], quantities_by_sku={})
        closing = DayClosing.objects.get()
        assert closing.data["pending_production"] == []
        assert closing.data["pending_production_release"] is None
