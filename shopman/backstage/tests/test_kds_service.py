"""KDS mutation service tests."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.backstage.services import kds
from shopman.backstage.services.exceptions import KDSError, KDSTicketNotFound


@pytest.fixture
def ticket(db):
    order = Order.objects.create(ref="KDS-SVC-1", channel_ref="web", session_key="sk-kds-svc-1", total_q=1000)
    instance = KDSInstance.objects.create(ref="prep-svc", name="Preparo", type="prep")
    return KDSTicket.objects.create(
        session_key=order.session_key,
        kds_instance=instance,
        items=[{"sku": "A", "name": "Item", "qty": 1}],
    )


@pytest.mark.django_db
def test_start_ticket_is_idempotent(ticket):
    """Idempotente é "a segunda chamada deixa o mesmo estado", sem mock."""
    kds.start_ticket(ticket_pk=ticket.pk, actor="kds:op")
    kds.start_ticket(ticket_pk=ticket.pk, actor="kds:outro")

    ticket.refresh_from_db()
    assert ticket.status == "in_progress"


@pytest.mark.django_db
def test_start_ticket_raises_for_cancelled_ticket(ticket):
    ticket.status = "cancelled"
    ticket.cancelled_at = timezone.now()
    ticket.save(update_fields=["status", "cancelled_at"])

    with pytest.raises(KDSError):
        kds.start_ticket(ticket_pk=ticket.pk, actor="kds:op")


@pytest.mark.django_db
def test_start_ticket_raises_for_done_ticket(ticket):
    ticket.status = "done"
    ticket.completed_at = timezone.now()
    ticket.save(update_fields=["status", "completed_at"])

    with pytest.raises(KDSError):
        kds.start_ticket(ticket_pk=ticket.pk, actor="kds:op")


@pytest.mark.django_db
def test_mark_ticket_done_delegates_to_core(ticket, monkeypatch):
    core = Mock()
    monkeypatch.setattr(kds.kds_core, "complete_ticket", core)

    result = kds.mark_ticket_done(ticket_pk=ticket.pk, actor="kds:op")

    assert result.pk == ticket.pk
    core.assert_called_once_with(ticket, actor="kds:op")


@pytest.mark.django_db
def test_mark_ticket_done_raises_for_missing_ticket():
    with pytest.raises(KDSTicketNotFound):
        kds.mark_ticket_done(ticket_pk=999999, actor="kds:op")


@pytest.mark.django_db
def test_mark_ticket_done_surfaces_lifecycle_block_reason(ticket, monkeypatch):
    # Gate do lifecycle (ex.: pagamento não capturado) ≠ "ticket não está
    # aberto": a razão real do core chega intacta ao operador.
    from shopman.shop.services import kds as kds_core

    def blocked(*args, **kwargs):
        raise kds_core.TicketCompletionBlocked("Pagamento ainda não foi confirmado.")

    monkeypatch.setattr(kds.kds_core, "complete_ticket", blocked)

    with pytest.raises(KDSError, match="Pagamento ainda não foi confirmado."):
        kds.mark_ticket_done(ticket_pk=ticket.pk, actor="kds:op")


@pytest.mark.django_db
def test_mark_ticket_done_requires_acknowledging_item_cancellation(ticket):
    KDSTicket.objects.create(
        session_key=ticket.session_key,
        kds_instance=ticket.kds_instance,
        items=[{"line_id": "removed", "sku": "B", "name": "Item retirado", "qty": 1}],
        status="cancelled",
        cancelled_at=timezone.now(),
    )

    with pytest.raises(KDSError, match="Toque em Recebi o cancelamento"):
        kds.mark_ticket_done(ticket_pk=ticket.pk, actor="kds:op")

    ticket.refresh_from_db()
    assert ticket.status == "pending"


@pytest.mark.django_db
def test_mark_ticket_done_replay_is_noop_success(ticket, monkeypatch):
    # Segundo bump (outra estação) = sucesso no-op, mesma semântica do replay
    # da Saída — nunca "Ticket não está aberto".
    ticket.status = "done"
    ticket.completed_at = timezone.now()
    ticket.save(update_fields=["status", "completed_at"])
    core = Mock()
    monkeypatch.setattr(kds.kds_core, "complete_ticket", core)

    result = kds.mark_ticket_done(ticket_pk=ticket.pk, actor="kds:op")

    assert result.pk == ticket.pk
    core.assert_not_called()


@pytest.mark.django_db
def test_mark_ticket_done_raises_for_cancelled_ticket(ticket):
    ticket.status = "cancelled"
    ticket.cancelled_at = timezone.now()
    ticket.save(update_fields=["status", "cancelled_at"])

    with pytest.raises(KDSError):
        kds.mark_ticket_done(ticket_pk=ticket.pk, actor="kds:op")


@pytest.mark.django_db
def test_recall_ticket_reopens_done(ticket):
    ticket.status = "done"
    ticket.completed_at = timezone.now()
    ticket.save(update_fields=["status", "completed_at"])

    result = kds.recall_ticket(ticket_pk=ticket.pk, actor="kds:op")

    assert result.status == "in_progress"
    assert result.completed_at is None


@pytest.mark.django_db
def test_recall_ticket_raises_when_not_done(ticket):
    with pytest.raises(KDSError):
        kds.recall_ticket(ticket_pk=ticket.pk, actor="kds:op")


@pytest.mark.django_db
def test_acknowledge_ticket_marks_cancelled(ticket):
    ticket.status = "cancelled"
    ticket.cancelled_at = timezone.now()
    ticket.save(update_fields=["status", "cancelled_at"])

    result = kds.acknowledge_ticket(ticket_pk=ticket.pk, actor="kds:op")

    assert result.acknowledged_at is not None


@pytest.mark.django_db
def test_acknowledge_ticket_raises_when_not_cancelled(ticket):
    with pytest.raises(KDSError):
        kds.acknowledge_ticket(ticket_pk=ticket.pk, actor="kds:op")


@pytest.mark.django_db
def test_future_ticket_rejects_all_mutations(ticket):
    order = Order.objects.get(session_key=ticket.session_key)
    order.data = {"delivery_date": (timezone.localdate() + timedelta(days=1)).isoformat()}
    order.save(update_fields=["data", "updated_at"])

    with pytest.raises(KDSError, match="somente para consulta"):
        kds.start_ticket(ticket_pk=ticket.pk, actor="kds:op")
    with pytest.raises(KDSError, match="somente para consulta"):
        kds.mark_ticket_done(ticket_pk=ticket.pk, actor="kds:op")

    ticket.status = "done"
    ticket.completed_at = timezone.now()
    ticket.save(update_fields=["status", "completed_at"])
    with pytest.raises(KDSError, match="somente para consulta"):
        kds.recall_ticket(ticket_pk=ticket.pk, actor="kds:op")

    ticket.status = "cancelled"
    ticket.cancelled_at = timezone.now()
    ticket.save(update_fields=["status", "cancelled_at"])
    with pytest.raises(KDSError, match="somente para consulta"):
        kds.acknowledge_ticket(ticket_pk=ticket.pk, actor="kds:op")

    ticket.refresh_from_db()
    assert ticket.acknowledged_at is None

