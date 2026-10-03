"""UX-G2: "pronto" automático com desfazer e desfazer de 5 s em Entregar/Despachar.

SUITE-UX §5.1 (decisões do dono): o sistema faz o que sabe, com guarda.

- Pronto automático: só quando TODAS as estações concluíram; o desfazer reabre o
  ticket e devolve o pedido ao preparo; o que sai da casa (aviso de pronto,
  iFood) espera a janela e vira no-op se desfeito.
- Entregar/Despachar: o toque do Gestor/Saída não grava a transição; a gravação
  vem quando a janela vence; desfazer dentro da janela não deixa rastro lá fora.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Directive, Order, OrderItem

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.shop.directives import IFOOD_STATUS_CALLBACK, ORDER_HANDOFF_COMMIT, ORDER_LIFECYCLE_PHASE
from shopman.shop.handlers.handoff_commit import HandoffCommitHandler
from shopman.shop.handlers.lifecycle_phase import LifecyclePhaseHandler
from shopman.shop.models import Channel, Shop
from shopman.shop.services import kds as kds_core
from shopman.shop.services import operator_orders, order_undo

pytestmark = pytest.mark.django_db


@pytest.fixture
def channel(db):
    Shop.objects.create(name="Loja")
    return Channel.objects.create(ref="web", name="Loja online", config={})


def _order(ref: str, *, status=Order.Status.PREPARING, fulfillment="pickup", channel_ref="web", **extra) -> Order:
    order = Order.objects.create(
        ref=ref,
        channel_ref=channel_ref,
        session_key=f"sk-{ref}",
        status=status,
        total_q=1500,
        data={"customer": {"name": "Ana"}, "fulfillment_type": fulfillment, "payment": {"method": "cash"}, **extra},
    )
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=1500, line_total_q=1500)
    return order


def _ticket(order: Order, station: str, *, status: str = "pending", printed: bool = False) -> KDSTicket:
    instance, _ = KDSInstance.objects.get_or_create(ref=station, defaults={"name": station, "type": "prep"})
    return KDSTicket.objects.create(
        session_key=order.session_key, kds_instance=instance, status=status,
        items=[{"sku": "PAO", "name": "Pão", "qty": 1}],
    )


def _phase_directives(order: Order, phase: str):
    return Directive.objects.filter(topic=ORDER_LIFECYCLE_PHASE, payload__order_ref=order.ref, payload__phase=phase)


def _notifications(order: Order, template: str):
    return Directive.objects.filter(topic="notification.send", payload__order_ref=order.ref, payload__template=template)


def _run(handler, directive: Directive) -> None:
    directive.refresh_from_db()
    handler.handle(message=directive, ctx={})


def _expire_auto_ready(order: Order) -> None:
    order.refresh_from_db()
    data = dict(order.data)
    data["auto_ready"] = {**data["auto_ready"], "undo_until": (timezone.now() - timedelta(seconds=1)).isoformat()}
    Order.objects.filter(pk=order.pk).update(data=data)
    order.refresh_from_db()


def _expire_handoff(order: Order) -> None:
    order.refresh_from_db()
    data = dict(order.data)
    data["pending_handoff"] = {**data["pending_handoff"], "commit_at": (timezone.now() - timedelta(seconds=1)).isoformat()}
    Order.objects.filter(pk=order.pk).update(data=data)
    order.refresh_from_db()


def _set_fulfillment(channel: Channel, **values) -> None:
    channel.config = {**(channel.config or {}), "fulfillment": {**((channel.config or {}).get("fulfillment") or {}), **values}}
    channel.save()


# ── Pronto automático: guarda (a) ────────────────────────────────────────


def test_auto_ready_only_when_every_station_concluded(channel):
    order = _order("UNDO-A1")
    t1 = _ticket(order, "lanches")
    t2 = _ticket(order, "cafes")

    kds_core.complete_ticket(t1, actor="kds:op")
    order.refresh_from_db()
    assert order.status == Order.Status.PREPARING
    assert "auto_ready" not in order.data

    kds_core.complete_ticket(t2, actor="kds:op")
    order.refresh_from_db()
    assert order.status == Order.Status.READY
    record = order.data["auto_ready"]
    assert record["ticket_ids"] == [t2.pk]
    assert record["token"]
    assert order_undo.ready_hold(order)


def test_printed_station_still_open_holds_auto_ready(channel):
    """A estação sem tela também é estação: sem o "Pronto" dela, não há pronto."""
    order = _order("UNDO-A2")
    screen = _ticket(order, "forno")
    _ticket(order, "lanches-papel")  # aberta: ninguém deu o pronto do papel

    kds_core.complete_ticket(screen, actor="kds:op")
    order.refresh_from_db()
    assert order.status == Order.Status.PREPARING


def test_auto_ready_disabled_keeps_order_preparing(channel):
    _set_fulfillment(channel, auto_ready=False)
    order = _order("UNDO-A3")
    ticket = _ticket(order, "lanches")

    kds_core.complete_ticket(ticket, actor="kds:op")
    order.refresh_from_db()
    assert order.status == Order.Status.PREPARING
    advance = next(a for a in operator_orders.operational_actions(order) if a.ref == "advance")
    assert advance.label == "Marcar pronto"


def test_manual_ready_moves_to_the_menu_while_the_kitchen_works(channel):
    order = _order("UNDO-A4")
    _ticket(order, "lanches")

    advance = next(a for a in operator_orders.operational_actions(order) if a.ref == "advance")
    assert advance.priority == "menu"
    assert advance.label == "Marcar pronto"


def test_manual_ready_stays_primary_without_kitchen_ticket(channel):
    order = _order("UNDO-A5")
    advance = next(a for a in operator_orders.operational_actions(order) if a.ref == "advance")
    assert advance.priority == "primary"


# ── Pronto automático: guarda (c) — o aviso espera a janela ──────────────


def test_ready_phase_is_scheduled_for_the_end_of_the_window(channel):
    order = _order("UNDO-C1")
    ticket = _ticket(order, "lanches")
    before = timezone.now()

    kds_core.complete_ticket(ticket, actor="kds:op")
    order.refresh_from_db()

    directive = _phase_directives(order, "on_ready").get()
    assert directive.payload["hold_token"] == order.data["auto_ready"]["token"]
    assert directive.available_at >= before + timedelta(seconds=29)
    assert not _notifications(order, "order_ready").exists()


def test_held_ready_phase_notifies_after_the_window(channel):
    order = _order("UNDO-C2")
    ticket = _ticket(order, "lanches")
    kds_core.complete_ticket(ticket, actor="kds:op")
    order.refresh_from_db()
    directive = _phase_directives(order, "on_ready").get()

    _run(LifecyclePhaseHandler(), directive)

    order.refresh_from_db()
    assert order.data["lifecycle"]["on_ready"] == "done"
    assert _notifications(order, "order_ready").count() == 1
    # Idempotente: rodar de novo não avisa duas vezes.
    _run(LifecyclePhaseHandler(), directive)
    assert _notifications(order, "order_ready").count() == 1


def test_no_window_notifies_at_once(channel):
    _set_fulfillment(channel, ready_undo_seconds=0)
    order = _order("UNDO-C3")
    ticket = _ticket(order, "lanches")
    kds_core.complete_ticket(ticket, actor="kds:op")
    order.refresh_from_db()

    assert "auto_ready" not in order.data
    directive = _phase_directives(order, "on_ready").get()
    assert "hold_token" not in directive.payload
    assert directive.available_at <= timezone.now()


def test_counter_order_has_no_window(channel):
    Channel.objects.create(ref="pdv", name="PDV", config={})
    order = _order("UNDO-C4", channel_ref="pdv", origin_channel="pos", pos={"sales_mode": "counter"})
    ticket = _ticket(order, "lanches")
    kds_core.complete_ticket(ticket, actor="kds:op")
    order.refresh_from_db()
    assert "auto_ready" not in order.data


# ── Pronto automático: guarda (b) — desfazer ─────────────────────────────


def test_undo_auto_ready_reopens_the_ticket_and_silences_the_held_notice(channel):
    order = _order("UNDO-B1")
    ticket = _ticket(order, "lanches")
    kds_core.complete_ticket(ticket, actor="kds:op")
    order.refresh_from_db()
    token = order.data["auto_ready"]["token"]
    held = _phase_directives(order, "on_ready").get()

    order_undo.undo_auto_ready(order, token=token, actor="gestor:ana")

    order.refresh_from_db()
    ticket.refresh_from_db()
    assert order.status == Order.Status.PREPARING
    assert "auto_ready" not in order.data
    assert ticket.status == "in_progress"
    assert order.events.filter(type="auto_ready_undone").exists()

    _run(LifecyclePhaseHandler(), held)
    order.refresh_from_db()
    assert "on_ready" not in (order.data.get("lifecycle") or {})
    assert not _notifications(order, "order_ready").exists()


def test_undo_auto_ready_after_the_window_is_refused(channel):
    order = _order("UNDO-B2")
    ticket = _ticket(order, "lanches")
    kds_core.complete_ticket(ticket, actor="kds:op")
    order.refresh_from_db()
    token = order.data["auto_ready"]["token"]
    _expire_auto_ready(order)

    with pytest.raises(order_undo.UndoRefused, match="prazo"):
        order_undo.undo_auto_ready(order, token=token, actor="gestor:ana")
    order.refresh_from_db()
    assert order.status == Order.Status.READY


def test_undo_auto_ready_with_a_stale_token_is_refused(channel):
    order = _order("UNDO-B3")
    ticket = _ticket(order, "lanches")
    kds_core.complete_ticket(ticket, actor="kds:op")
    order.refresh_from_db()

    with pytest.raises(order_undo.UndoRefused):
        order_undo.undo_auto_ready(order, token="outro", actor="gestor:ana")


def test_ready_again_after_undo_is_a_new_hold(channel):
    """O pronto desfeito e refeito ganha outra directive: o recibo do primeiro não a engole."""
    order = _order("UNDO-B4")
    ticket = _ticket(order, "lanches")
    kds_core.complete_ticket(ticket, actor="kds:op")
    order.refresh_from_db()
    first = order.data["auto_ready"]["token"]
    order_undo.undo_auto_ready(order, token=first, actor="gestor:ana")
    ticket.refresh_from_db()

    kds_core.complete_ticket(ticket, actor="kds:op")
    order.refresh_from_db()
    second = order.data["auto_ready"]["token"]
    assert second != first
    directives = list(_phase_directives(order, "on_ready").order_by("pk"))
    assert [d.payload["hold_token"] for d in directives] == [first, second]

    for directive in directives:
        _run(LifecyclePhaseHandler(), directive)
    assert _notifications(order, "order_ready").count() == 1


def test_kitchen_recall_also_drops_the_hold(channel):
    order = _order("UNDO-B5")
    ticket = _ticket(order, "lanches")
    kds_core.complete_ticket(ticket, actor="kds:op")
    held = _phase_directives(order, "on_ready").get()
    ticket.refresh_from_db()

    kds_core.reopen_ticket(ticket, actor="kds:op")
    order.refresh_from_db()
    assert order.status == Order.Status.PREPARING
    assert "auto_ready" not in order.data
    _run(LifecyclePhaseHandler(), held)
    assert not _notifications(order, "order_ready").exists()


def test_leaving_ready_inside_the_window_releases_the_ready_phase_first(channel):
    """Entregou logo: o pronto sai antes da conclusão, e a directive segurada vira no-op."""
    _set_fulfillment(channel, handoff_undo_seconds=0)
    order = _order("UNDO-B6")
    ticket = _ticket(order, "lanches")
    kds_core.complete_ticket(ticket, actor="kds:op")
    held = _phase_directives(order, "on_ready").get()
    order.refresh_from_db()

    operator_orders.advance_order(order, actor="gestor:ana", target_status=Order.Status.COMPLETED, undo_window=True)

    order.refresh_from_db()
    assert order.status == Order.Status.COMPLETED
    assert order.data["lifecycle"]["on_ready"] == "done"
    assert _notifications(order, "order_ready").count() == 1
    _run(LifecyclePhaseHandler(), held)
    assert _notifications(order, "order_ready").count() == 1


def test_undo_ready_is_offered_only_inside_the_window(channel):
    order = _order("UNDO-B7")
    ticket = _ticket(order, "lanches")
    kds_core.complete_ticket(ticket, actor="kds:op")
    order.refresh_from_db()
    refs = [a.ref for a in operator_orders.operational_actions(order)]
    assert "undo-ready" in refs

    _expire_auto_ready(order)
    refs = [a.ref for a in operator_orders.operational_actions(order)]
    assert "undo-ready" not in refs


# ── iFood: o readyToPickup NÃO espera (efeito que não pode esperar) ──────


def test_ifood_ready_callback_is_not_held_and_the_card_says_so(channel):
    """O readyToPickup chama o entregador do iFood: sai na hora, e o card avisa."""
    from shopman.backstage.projections.order_queue import _undo_projection
    from shopman.shop.handlers import ifood_status

    Channel.objects.create(ref="ifood", name="iFood", config={})
    order = _order("UNDO-I1", channel_ref="ifood")
    Order.objects.filter(pk=order.pk).update(external_ref="ifood-abc")
    order.refresh_from_db()
    ticket = _ticket(order, "lanches")
    kds_core.complete_ticket(ticket, actor="kds:op")
    order.refresh_from_db()

    ifood_status._enqueue_callback(order, "kds:op")
    callback = Directive.objects.get(topic=IFOOD_STATUS_CALLBACK, payload__order_ref=order.ref)
    assert callback.available_at <= timezone.now()
    assert "hold_token" not in callback.payload
    # O aviso ao cliente (fase do pronto), esse sim, espera.
    assert _phase_directives(order, "on_ready").get().available_at > timezone.now()

    undo = _undo_projection(order)
    assert undo.kind == "auto_ready"
    assert undo.already_out == "iFood já avisado"
    assert undo.held_effect == "Aviso de pronto ao cliente"


# ── Entregar / Despachar ─────────────────────────────────────────────────


def _ready(ref: str, **kwargs) -> Order:
    return _order(ref, status=Order.Status.READY, **kwargs)


def test_handoff_tap_does_not_record_the_transition(channel):
    order = _ready("UNDO-H1")

    result = operator_orders.advance_order(order, actor="gestor:ana", target_status=Order.Status.COMPLETED, undo_window=True)

    assert result == Order.Status.COMPLETED
    order.refresh_from_db()
    assert order.status == Order.Status.READY
    pending = order.data["pending_handoff"]
    assert pending["to_status"] == Order.Status.COMPLETED
    assert pending["from_status"] == Order.Status.READY
    commit = Directive.objects.get(topic=ORDER_HANDOFF_COMMIT, payload__order_ref=order.ref)
    assert commit.payload["token"] == pending["token"]
    assert commit.available_at > timezone.now() + timedelta(seconds=3)
    # Nada que sai da casa: nem a fase de conclusão (fidelidade, nota), nem aviso.
    assert not _phase_directives(order, "on_completed").exists()


def test_handoff_without_window_records_at_once(channel):
    _set_fulfillment(channel, handoff_undo_seconds=0)
    order = _ready("UNDO-H2")
    operator_orders.advance_order(order, actor="gestor:ana", target_status=Order.Status.COMPLETED, undo_window=True)
    order.refresh_from_db()
    assert order.status == Order.Status.COMPLETED
    assert "pending_handoff" not in order.data


def test_other_callers_keep_recording_at_once(channel):
    """iFood, entregador, PDV e piloto não passam ``undo_window``: gravam na hora."""
    order = _ready("UNDO-H3")
    operator_orders.advance_order(order, actor="system:ifood", target_status=Order.Status.COMPLETED)
    order.refresh_from_db()
    assert order.status == Order.Status.COMPLETED


def test_commit_after_the_window_records_the_transition(channel):
    order = _ready("UNDO-H4")
    operator_orders.advance_order(order, actor="gestor:ana", target_status=Order.Status.COMPLETED, undo_window=True)
    commit = Directive.objects.get(topic=ORDER_HANDOFF_COMMIT, payload__order_ref=order.ref)

    # Antes do prazo: no-op.
    _run(HandoffCommitHandler(), commit)
    order.refresh_from_db()
    assert order.status == Order.Status.READY

    _expire_handoff(order)
    _run(HandoffCommitHandler(), commit)
    order.refresh_from_db()
    assert order.status == Order.Status.COMPLETED
    assert "pending_handoff" not in order.data
    assert _phase_directives(order, "on_completed").count() == 1
    # Idempotente: a mesma directive de novo não faz nada.
    _run(HandoffCommitHandler(), commit)
    order.refresh_from_db()
    assert order.status == Order.Status.COMPLETED


def test_undo_handoff_inside_the_window(channel):
    order = _ready("UNDO-H5")
    operator_orders.advance_order(order, actor="gestor:ana", target_status=Order.Status.COMPLETED, undo_window=True)
    order.refresh_from_db()
    token = order.data["pending_handoff"]["token"]
    commit = Directive.objects.get(topic=ORDER_HANDOFF_COMMIT, payload__order_ref=order.ref)

    order_undo.undo_handoff(order, token=token, actor="gestor:ana")

    order.refresh_from_db()
    assert order.status == Order.Status.READY
    assert "pending_handoff" not in order.data
    assert order.events.filter(type="handoff_undone").exists()
    # A gravação agendada vira no-op, mesmo depois do prazo.
    _run(HandoffCommitHandler(), commit)
    order.refresh_from_db()
    assert order.status == Order.Status.READY
    assert not _phase_directives(order, "on_completed").exists()


def test_undo_handoff_after_the_window_is_refused(channel):
    order = _ready("UNDO-H6")
    operator_orders.advance_order(order, actor="gestor:ana", target_status=Order.Status.COMPLETED, undo_window=True)
    order.refresh_from_db()
    token = order.data["pending_handoff"]["token"]
    _expire_handoff(order)

    with pytest.raises(order_undo.UndoRefused, match="prazo"):
        order_undo.undo_handoff(order, token=token, actor="gestor:ana")


def test_race_commit_first_then_undo_is_refused(channel):
    order = _ready("UNDO-H7")
    operator_orders.advance_order(order, actor="gestor:ana", target_status=Order.Status.COMPLETED, undo_window=True)
    order.refresh_from_db()
    token = order.data["pending_handoff"]["token"]
    _expire_handoff(order)

    assert order_undo.commit_handoff(order.ref, token) == Order.Status.COMPLETED
    with pytest.raises(order_undo.UndoRefused):
        order_undo.undo_handoff(order, token=token, actor="gestor:ana")
    order.refresh_from_db()
    assert order.status == Order.Status.COMPLETED


def test_race_undo_first_then_commit_is_noop(channel):
    order = _ready("UNDO-H8")
    operator_orders.advance_order(order, actor="gestor:ana", target_status=Order.Status.COMPLETED, undo_window=True)
    order.refresh_from_db()
    token = order.data["pending_handoff"]["token"]

    order_undo.undo_handoff(order, token=token, actor="gestor:ana")
    assert order_undo.commit_handoff(order.ref, token, now=timezone.now() + timedelta(minutes=1)) == ""
    order.refresh_from_db()
    assert order.status == Order.Status.READY


def test_repeated_tap_is_the_same_handoff_and_another_target_conflicts(channel):
    order = _ready("UNDO-H9", fulfillment="delivery")
    operator_orders.advance_order(order, actor="gestor:ana", target_status=Order.Status.DISPATCHED, undo_window=True)
    order.refresh_from_db()
    token = order.data["pending_handoff"]["token"]

    assert operator_orders.advance_order(order, actor="saida:bia", target_status=Order.Status.DISPATCHED, undo_window=True) == Order.Status.DISPATCHED
    order.refresh_from_db()
    assert order.data["pending_handoff"]["token"] == token
    assert Directive.objects.filter(topic=ORDER_HANDOFF_COMMIT, payload__order_ref=order.ref).count() == 1

    with pytest.raises(operator_orders.OrderStateConflict):
        operator_orders.advance_order(order, actor="gestor:ana", target_status=Order.Status.COMPLETED, undo_window=True)


def test_dispatch_window_then_commit_schedules_the_delivery_close(channel):
    from shopman.shop.directives import DELIVERY_AUTO_COMPLETE

    order = _ready("UNDO-H10", fulfillment="delivery")
    operator_orders.advance_order(order, actor="gestor:ana", target_status=Order.Status.DISPATCHED, undo_window=True)
    assert not Directive.objects.filter(topic=DELIVERY_AUTO_COMPLETE, payload__order_ref=order.ref).exists()
    order.refresh_from_db()
    _expire_handoff(order)

    assert order_undo.commit_handoff(order.ref, order.data["pending_handoff"]["token"]) == Order.Status.DISPATCHED
    order.refresh_from_db()
    assert order.status == Order.Status.DISPATCHED
    assert Directive.objects.filter(topic=DELIVERY_AUTO_COMPLETE, payload__order_ref=order.ref).exists()


def test_refused_commit_leaves_the_order_and_warns(channel, monkeypatch):
    from shopman.backstage.models import OperatorAlert

    order = _ready("UNDO-H11")
    operator_orders.advance_order(order, actor="gestor:ana", target_status=Order.Status.COMPLETED, undo_window=True)
    order.refresh_from_db()
    token = order.data["pending_handoff"]["token"]
    _expire_handoff(order)
    monkeypatch.setattr(operator_orders, "gestor_advance_block", lambda *a, **k: operator_orders.AdvanceBlock.PAYMENT_NOT_CAPTURED)

    assert order_undo.commit_handoff(order.ref, token) == ""
    order.refresh_from_db()
    assert order.status == Order.Status.READY
    assert "pending_handoff" not in order.data
    assert OperatorAlert.objects.filter(type="handoff_refused", order_ref=order.ref).exists()


def test_next_advance_settles_an_expired_handoff_first(channel):
    """O worker atrasou: o próximo toque grava a saída vencida antes de seguir."""
    order = _ready("UNDO-H12", fulfillment="delivery")
    operator_orders.advance_order(order, actor="gestor:ana", target_status=Order.Status.DISPATCHED, undo_window=True)
    order.refresh_from_db()
    _expire_handoff(order)

    # O próximo passo (entregue) grava primeiro a saída vencida e depois abre
    # a janela dele.
    operator_orders.advance_order(order, actor="gestor:ana", target_status=Order.Status.DELIVERED, undo_window=True)
    order.refresh_from_db()
    assert order.status == Order.Status.DISPATCHED
    assert order.data["pending_handoff"]["to_status"] == Order.Status.DELIVERED


def test_pending_handoff_offers_only_undo(channel):
    order = _ready("UNDO-H13")
    operator_orders.advance_order(order, actor="gestor:ana", target_status=Order.Status.COMPLETED, undo_window=True)
    order.refresh_from_db()
    refs = [a.ref for a in operator_orders.operational_actions(order)]
    assert "undo-handoff" in refs
    assert "advance" not in refs


def test_saida_and_gestor_share_the_same_window(channel):
    order = _ready("UNDO-H14")
    assert kds_core.expedition_action_by_order_id(order.pk, action="complete", actor="saida:bia") == Order.Status.COMPLETED
    order.refresh_from_db()
    assert order.status == Order.Status.READY
    assert order.data["pending_handoff"]["to_status"] == Order.Status.COMPLETED
    # Replay pela Saída: a mesma saída.
    assert kds_core.expedition_action_by_order_id(order.pk, action="complete", actor="saida:bia") == Order.Status.COMPLETED
    assert Directive.objects.filter(topic=ORDER_HANDOFF_COMMIT, payload__order_ref=order.ref).count() == 1
