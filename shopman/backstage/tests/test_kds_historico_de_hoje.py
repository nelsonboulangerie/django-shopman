"""O Histórico de hoje da estação (decisão do dono, 13/10/2026).

K1: só o turno de HOJE (desde 0h, hora da loja) e só da estação aberta.
K2: o pedido que já saiu da cozinha só se VÊ; Reabrir só quando a régua do
servidor (``recall_block_reason``) deixa, e quando não deixa a linha diz o motivo.

E os dois furos de auditoria que o histórico expôs:
- reabrir (desfazer o Pronto) não apaga mais o Pronto sem rastro;
- "Recebi o cancelamento" grava QUEM deu a ciência.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.utils import timezone
from rest_framework.test import APIClient
from shopman.orderman.models import Order

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.backstage.projections.kds import HISTORY_LIMIT, build_kds_history
from shopman.backstage.services import kds as kds_backstage
from shopman.backstage.services.exceptions import KDSInstanceNotFound
from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db


@pytest.fixture
def station():
    Shop.objects.create(name="Loja")
    return KDSInstance.objects.create(ref="lanches", name="Lanches", type="prep", target_time_minutes=10)


@pytest.fixture
def people():
    user_model = get_user_model()
    user_model.objects.create_user(username="rafa", first_name="Rafael Souza", password="x")
    user_model.objects.create_user(username="ana", first_name="Ana", password="x")


def _order(ref: str, status=Order.Status.READY, **data) -> Order:
    return Order.objects.create(
        ref=ref, channel_ref="pos", session_key=f"sk-{ref}", status=status, total_q=1000,
        data={"fulfillment_type": "pickup", **data},
    )


def _ticket(station, order, *, status="done", **fields) -> KDSTicket:
    return KDSTicket.objects.create(
        session_key=order.session_key,
        kds_instance=station,
        items=[{"sku": "CRQ", "name": "Croque", "qty": 2}, {"sku": "CAF", "name": "Café", "qty": 1}],
        status=status,
        **fields,
    )


def _at(hour: int, minute: int, *, days_ago: int = 0):
    day = timezone.localdate() - timedelta(days=days_ago)
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


def test_history_is_today_and_this_station_only(station):
    other = KDSInstance.objects.create(ref="cafes", name="Cafés", type="prep")
    today = _ticket(station, _order("PDV-1"), completed_at=timezone.now(), completed_by="rafa", completed_via="station")
    _ticket(station, _order("PDV-2"), completed_at=_at(22, 0, days_ago=1))
    _ticket(other, _order("PDV-3"), completed_at=timezone.now())
    _ticket(station, _order("PDV-4"), status="in_progress")  # ainda no quadro

    history = build_kds_history(station.ref)

    assert [entry.ticket.pk for entry in history.entries] == [today.pk]
    assert history.total == 1


def test_history_line_tells_who_did_what_and_how_long(station, people):
    order = _order("PDV-0131", kds_started={})
    ticket = _ticket(station, order)
    received = timezone.now() - timedelta(minutes=11)
    started = received + timedelta(minutes=2)
    done = started + timedelta(minutes=9)
    KDSTicket.objects.filter(pk=ticket.pk).update(
        created_at=received, completed_at=done, completed_by="rafa", completed_via="station",
    )
    order.data["kds_started"] = {str(ticket.pk): {"at": started.isoformat(), "by": "rafa"}}
    order.save(update_fields=["data"])

    [entry] = build_kds_history(station.ref).entries

    hhmm = lambda dt: timezone.localtime(dt).strftime("%H:%M")  # noqa: E731
    assert entry.steps == (
        f"recebido {hhmm(received)}",
        f"iniciado {hhmm(started)} Rafael",
        f"Pronto {hhmm(done)} Rafael (tela)",
    )
    assert entry.prep_display == "9 min"
    assert entry.items_summary == "2x Croque, 1x Café"
    assert entry.state == "done"
    assert entry.can_reopen is True
    assert entry.reopen_block_reason == ""


@pytest.mark.parametrize("status", [Order.Status.DISPATCHED, Order.Status.COMPLETED])
def test_order_that_left_the_kitchen_is_only_seen(station, status):
    _ticket(station, _order(f"PDV-{status}", status=status), completed_at=timezone.now())

    [entry] = build_kds_history(station.ref).entries

    assert entry.can_reopen is False
    assert "não volta à cozinha" in entry.reopen_block_reason
    assert "PDV ou pelo Gestor" in entry.reopen_block_reason


def test_undo_keeps_the_pronto_it_erased(station, people):
    order = _order("PDV-0140")
    ticket = _ticket(station, order, completed_at=timezone.now() - timedelta(minutes=7),
                     completed_by="rafa", completed_via="station")

    kds_backstage.recall_ticket(ticket_pk=ticket.pk, actor="ana")

    ticket.refresh_from_db()
    assert ticket.status == "in_progress"
    assert ticket.completed_at is None
    [record] = ticket.reopenings
    assert record["completed_by"] == "rafa"
    assert record["completed_via"] == "station"
    assert record["undone_by"] == "ana"
    assert record["completed_at"] and record["undone_at"]

    # Pronto de novo: o histórico mostra o Pronto desfeito e o de agora.
    ticket.status = "done"
    ticket.completed_at = timezone.now()
    ticket.completed_by = "rafa"
    ticket.completed_via = "station"
    ticket.save()
    [entry] = build_kds_history(station.ref).entries
    [undone] = entry.undone
    assert undone.startswith("Pronto ") and " Rafael (tela) → desfeito " in undone
    assert undone.endswith(" Ana")


def test_gestor_undo_of_auto_ready_also_keeps_the_trail(station):
    from shopman.shop.adapters import kds as kds_adapter

    order = _order("PDV-0150")
    ticket = _ticket(station, order, completed_at=timezone.now(), completed_by="kds.all_done")

    assert kds_adapter.reopen_done_tickets(order.session_key, [ticket.pk], actor="ana") == [ticket.pk]

    ticket.refresh_from_db()
    assert ticket.reopenings[0]["undone_by"] == "ana"
    assert ticket.reopenings[0]["completed_by"] == "kds.all_done"


def test_cancel_acknowledgement_records_who(station, people):
    order = _order("PDV-0160", status=Order.Status.CANCELLED)
    ticket = _ticket(station, order, status="cancelled", cancelled_at=timezone.now())

    kds_backstage.acknowledge_ticket(ticket_pk=ticket.pk, actor="ana")

    ticket.refresh_from_db()
    assert ticket.acknowledged_by == "ana"
    [entry] = build_kds_history(station.ref).entries
    assert entry.state == "cancelled"
    assert entry.steps[-2].startswith("Cancelado ")
    assert entry.steps[-1].startswith("ciente ") and entry.steps[-1].endswith(" Ana")
    assert entry.can_reopen is False
    assert entry.reopen_block_reason == ""
    assert entry.prep_display == ""


def test_system_actor_has_no_name_on_the_line(station):
    _ticket(station, _order("PDV-0170"), completed_at=timezone.now(),
            completed_by="system:counter_kds_handoff", completed_via="order_advanced")

    [entry] = build_kds_history(station.ref).entries

    assert entry.steps[-1].endswith("(Gestor)")
    assert "system" not in entry.steps[-1]


def test_search_by_code_reaches_the_whole_day_and_limit_caps(station):
    for n in range(HISTORY_LIMIT + 5):
        _ticket(station, _order(f"PDV-{n:04d}"), completed_at=timezone.now() - timedelta(seconds=n))

    history = build_kds_history(station.ref)
    assert len(history.entries) == HISTORY_LIMIT
    assert history.total == HISTORY_LIMIT + 5

    found = build_kds_history(station.ref, query="0104")
    assert [e.ticket.order_ref for e in found.entries] == ["PDV-0104"]
    assert found.total == 1


def test_history_of_unknown_or_exit_station_is_404(station):
    KDSInstance.objects.create(ref="saida", name="Saída", type="expedition")
    for ref in ("nao-existe", "saida"):
        with pytest.raises(KDSInstanceNotFound):
            build_kds_history(ref)


def test_history_endpoint_is_separate_from_the_board(station):
    user = get_user_model().objects.create_user(username="op", password="x", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="operate_kds"))
    _ticket(station, _order("PDV-0200"), completed_at=timezone.now())
    client = APIClient()
    client.force_authenticate(user)

    response = client.get(f"/api/v1/backstage/kds/{station.ref}/history/", {"q": "0200"})

    assert response.status_code == 200
    body = response.json()["history"]
    assert body["total"] == 1
    assert body["entries"][0]["ticket"]["order_ref"] == "PDV-0200"
    assert client.get("/api/v1/backstage/kds/nao-existe/history/").status_code == 404
