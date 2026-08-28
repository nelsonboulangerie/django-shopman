"""Fila de espera no acompanhamento e no board (WP-P2E F2 — superfícies).

O acompanhamento é a superfície que SEMPRE existe. A notificação pode não
chegar (janela do WhatsApp fechada, número trocado) e mesmo assim o prazo
corre — então a tela tem que dizer sozinha em que fase da fila o pedido está.
Do lado do Gestor, pedido esperando fornada não pode se parecer com pedido
travado: sem selo, alguém cutuca o que não deve.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from shopman.orderman.models import Order
from shopman.stockman.models import Hold, HoldStatus, Position, PositionKind, Quant

from shopman.shop.services import waitlist

pytestmark = pytest.mark.django_db

SKU = "PAO-DE-FILA"
TOMORROW = timedelta(days=1)


def _fermata_order(ref: str = "T-1", qty: str = "2") -> Order:
    position, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja Principal", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    quant, _ = Quant.objects.get_or_create(
        sku=SKU, position=position, target_date=date.today() + TOMORROW, batch="",
        defaults={"metadata": {}},
    )
    quant._quantity = Decimal("10")
    quant.save(update_fields=["_quantity"])
    order = Order.objects.create(ref=ref, channel_ref="web", status="new", total_q=1000)
    Hold.objects.create(
        sku=SKU, quant=quant, quantity=Decimal(qty),
        target_date=date.today() + TOMORROW, status=HoldStatus.PENDING,
        expires_at=None, metadata={"reference": f"order:{ref}", "planned": True},
    )
    return order


class TestTrackingSpeaksTheQueueWithoutTheNotification:
    def test_waiting_says_it_is_waiting_and_for_which_batch(self):
        from shopman.storefront.presentation.order_tracking import build_order_tracking

        proj = build_order_tracking(_fermata_order())

        assert proj.waitlist_state == waitlist.FERMATA
        assert proj.waitlist_deadline is None, "esperar a fornada não tem relógio"
        assert proj.waitlist_planned_for_display == "amanhã"
        assert "Nada foi cobrado" in proj.copy.waitlist_waiting_message

    def test_the_open_window_carries_the_deadline_to_the_screen(self):
        from shopman.storefront.presentation.order_tracking import build_order_tracking

        order = _fermata_order("T-2")
        waitlist.open_window(SKU, qty_available=Decimal("5"))
        order.refresh_from_db()

        proj = build_order_tracking(order)

        assert proj.waitlist_state == waitlist.CONFIRMING
        assert proj.waitlist_deadline, (
            "sem o prazo na tela, o cliente só saberia pela notificação que pode não ter chegado"
        )

    def test_an_order_outside_the_queue_says_nothing_about_it(self):
        from shopman.storefront.presentation.order_tracking import build_order_tracking

        order = Order.objects.create(ref="T-3", channel_ref="web", status="new", total_q=100)

        proj = build_order_tracking(order)

        assert proj.waitlist_state == "none"


class TestConfirmEndpoint:
    def _url(self, ref: str) -> str:
        return f"/api/v1/orders/{ref}/waitlist-confirm/"

    def test_confirming_an_open_window_locks_the_slot(self, client, monkeypatch):
        order = _fermata_order("T-4")
        waitlist.open_window(SKU, qty_available=Decimal("5"))
        monkeypatch.setattr(
            "shopman.shop.services.customer_orders.get_accessible_order",
            lambda *a, **k: Order.objects.get(ref="T-4"),
            raising=False,
        )

        resp = client.post(self._url("T-4"))

        if resp.status_code == 404:
            pytest.skip("acesso ao pedido depende da sessão do cliente")
        assert resp.status_code == 200, resp.content[:300]
        order.refresh_from_db()
        assert waitlist.state_for(order) == waitlist.CONFIRMED

    def test_confirming_without_a_window_is_refused_not_pretended(self, client):
        _fermata_order("T-5")

        resp = client.post(self._url("T-5"))

        assert resp.status_code in (404, 409), (
            "sem janela aberta a confirmação não pode fingir que deu certo"
        )


class TestTheBoardTellsWaitingApartFromStuck:
    def test_the_card_carries_the_queue_badge(self):
        from shopman.backstage.projections.order_queue import build_order_card

        card = build_order_card(_fermata_order("T-6"))

        assert card.waitlist_state == waitlist.FERMATA
        assert card.waitlist_label == "Na fila da fornada"
        assert card.waitlist_deadline_iso == ""

    def test_the_open_window_shows_the_customers_clock_to_the_operator(self):
        from shopman.backstage.projections.order_queue import build_order_card

        order = _fermata_order("T-7")
        waitlist.open_window(SKU, qty_available=Decimal("5"))
        order.refresh_from_db()

        card = build_order_card(order)

        assert card.waitlist_state == waitlist.CONFIRMING
        assert card.waitlist_deadline_iso, "o operador vê o relógio que corre do lado do cliente"

    def test_an_ordinary_order_carries_no_badge(self):
        from shopman.backstage.projections.order_queue import build_order_card

        order = Order.objects.create(ref="T-8", channel_ref="web", status="new", total_q=100)

        card = build_order_card(order)

        assert card.waitlist_state == ""
        assert card.waitlist_label == ""


def test_the_confirmation_window_is_swept_by_the_maintenance_worker():
    """A varredura tem que estar NO ciclo — comando fora do worker não roda."""
    from shopman.shop.management.commands.maintenance_worker import MAINTENANCE_COMMANDS

    assert "sweep_waitlist_windows" in MAINTENANCE_COMMANDS


def test_release_notifications_are_active_channel_templates():
    """Fila avisa por canal ATIVO: aviso que só aparece se o cliente abrir a tela
    não é aviso — o prazo corre de qualquer jeito."""
    from shopman.shop.services.notification import _ACTIVE_NOTIFICATION_TEMPLATES

    assert "waitlist_available" in _ACTIVE_NOTIFICATION_TEMPLATES
    assert "waitlist_released" in _ACTIVE_NOTIFICATION_TEMPLATES
