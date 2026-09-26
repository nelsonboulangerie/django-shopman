"""Reagendar encomenda — a data combinada muda e leva junto tudo que depende dela.

O que se prova aqui (``shop.services.reschedule``):

- futura → outra futura: o despertador é MOVIDO (continua um só), o lembrete de
  véspera é trocado por outro com a data nova, as reservas passam para a data nova,
  o vínculo de produção troca de ordem e a trilha grava a mudança;
- futura → hoje: ativa agora (baixa feita, despertador encerrado);
- sem saldo na data nova: recusa e NADA muda;
- pedido cancelado/concluído, pedido já em preparo, data passada/além do
  máximo/dia fechado: recusa com motivo;
- mesma data e janela: nada acontece (idempotente);
- o despertador que toca antes da data volta para a fila (não se perde).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.orderman.models import Directive, Order, OrderItem
from shopman.stockman.models import Hold, Position, PositionKind
from shopman.stockman.models.enums import HoldStatus
from shopman.stockman.services.movements import StockMovements
from shopman.stockman.services.planning import StockPlanning

from shopman.shop import lifecycle
from shopman.shop.directives import PREORDER_ACTIVATE
from shopman.shop.models import Channel, Shop
from shopman.shop.services import stock
from shopman.shop.services.reschedule import (
    HISTORY_KEY,
    RescheduleRefused,
    reschedule,
    schedule_preorder_reminder,
)

pytestmark = pytest.mark.django_db

SKU = "BAGUETE"
ABERTO_TODO_DIA = {
    day: {"open": "07:00", "close": "19:00"}
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
}


@pytest.fixture(autouse=True)
def _noop_sku_validator(settings):
    from shopman.stockman.adapters.sku_validation import reset_sku_validator

    settings.STOCKMAN = {
        **getattr(settings, "STOCKMAN", {}),
        "SKU_VALIDATOR": "shopman.stockman.adapters.noop.NoopSkuValidator",
    }
    reset_sku_validator()
    yield
    reset_sku_validator()


@pytest.fixture(autouse=True)
def casa(db):
    from shopman.offerman.models import Product

    Shop.objects.create(name="Nelson", brand_name="Nelson", opening_hours=ABERTO_TODO_DIA)
    # Pagamento no balcão: a baixa sai na ativação, sem passo digital.
    Channel.objects.create(ref="web", name="Loja", config={"payment": {"timing": "external", "method": "cash"}})
    # Canal que NÃO registra demanda: sem plano na data, não há reserva.
    Channel.objects.create(
        ref="strict", name="Sem demanda",
        config={"payment": {"timing": "external", "method": "cash"}, "stock": {"preorder": False}},
    )
    Product.objects.create(sku=SKU, name="Baguete", base_price_q=1200, is_published=True, is_sellable=True)


@pytest.fixture
def vitrine(db):
    return Position.objects.create(ref="vitrine", name="Vitrine", kind=PositionKind.PHYSICAL, is_saleable=True)


class _Product:
    sku = SKU
    name = "Baguete"
    shelf_life_days = None


def _day(offset: int):
    return timezone.localdate() + timedelta(days=offset)


def _plan(offset: int, qty: int, position) -> None:
    StockPlanning.plan(Decimal(qty), _Product(), _day(offset), position=position)


def _encomenda(ref: str, offset: int, *, channel: str = "web", status: str = Order.Status.ACCEPTED, slot: str = "slot-09") -> Order:
    day = _day(offset)
    order = Order.objects.create(
        ref=ref,
        channel_ref=channel,
        session_key=f"SESS-{ref}",
        status=status,
        snapshot={"items": [{"line_id": "L1", "sku": SKU, "name": "Baguete", "qty": 2, "unit_price_q": 1200}]},
        data={
            "customer": {"name": "Ana"},
            "fulfillment_type": "pickup",
            "payment": {"method": "cash"},
            "delivery_date": day.isoformat(),
            "delivery_time_slot": slot,
            "is_preorder": day > timezone.localdate(),
        },
        total_q=2400,
    )
    OrderItem.objects.create(order=order, line_id="L1", sku=SKU, name="Baguete", qty=2, unit_price_q=1200, line_total_q=2400)
    stock.hold(order)
    order.refresh_from_db()
    return order


def _holds(order) -> list[Hold]:
    ids = [int(e["hold_id"].split(":")[1]) for e in order.data.get("hold_ids", []) if e.get("hold_id")]
    return list(Hold.objects.filter(pk__in=ids))


def _live_alarms(order):
    return Directive.objects.filter(topic=PREORDER_ACTIVATE, payload__order_ref=order.ref, status__in=("queued", "running"))


def _pending_reminders(order):
    return Directive.objects.filter(
        topic="notification.send", status="queued", payload__order_ref=order.ref, payload__template="preorder_reminder",
    )


# ── futura → outra futura ────────────────────────────────────────────────────


def test_futura_para_futura_move_despertador_lembrete_estoque_e_historico(vitrine):
    _plan(3, 5, vitrine)
    _plan(6, 5, vitrine)
    order = _encomenda("RS-1", 3)
    lifecycle._schedule_preorder_activation(order)
    schedule_preorder_reminder(order)
    alarm = _live_alarms(order).get()
    old_holds = _holds(order)
    assert {h.target_date for h in old_holds} == {_day(3)}

    result = reschedule(order, date=_day(6).isoformat(), slot="slot-12", actor="pos:marina", reason="cliente viaja")

    assert result.changed and not result.activated_now
    order.refresh_from_db()
    assert order.data["delivery_date"] == _day(6).isoformat()
    assert order.data["delivery_time_slot"] == "slot-12"
    assert order.data["is_preorder"] is True

    # Despertador: o MESMO, movido.
    live = _live_alarms(order).get()
    assert live.pk == alarm.pk
    assert timezone.localtime(live.available_at).date() == _day(6)
    assert live.payload["delivery_date"] == _day(6).isoformat()

    # Lembrete: o antigo fecha sem envio, o novo leva a data nova.
    reminders = _pending_reminders(order)
    assert reminders.count() == 1
    novo = reminders.get()
    assert novo.payload["context"]["delivery_date"] == _day(6).isoformat()
    assert novo.payload["context"]["delivery_time_slot"] == "slot-12"
    assert timezone.localtime(novo.available_at).date() == _day(5)
    antigo = Directive.objects.get(topic="notification.send", payload__order_ref=order.ref, status="done")
    assert antigo.payload["notification_delivery"]["status"] == "skipped"
    assert antigo.payload["notification_delivery"]["reason"] == "rescheduled"

    # Estoque: reservas antigas soltas, novas na data nova.
    for hold in old_holds:
        hold.refresh_from_db()
        assert hold.status == HoldStatus.RELEASED
    new_holds = _holds(order)
    assert new_holds and {h.target_date for h in new_holds} == {_day(6)}
    assert sum(h.quantity for h in new_holds) == Decimal("2")

    # Trilha.
    (entry,) = order.data[HISTORY_KEY]
    assert entry["from_date"] == _day(3).isoformat() and entry["to_date"] == _day(6).isoformat()
    assert entry["from_slot"] == "slot-09" and entry["to_slot"] == "slot-12"
    assert entry["actor"] == "pos:marina" and entry["reason"] == "cliente viaja"
    event = order.events.get(type="order_rescheduled")
    assert event.payload["to_date"] == _day(6).isoformat()


def test_reagendar_troca_o_vinculo_de_producao(vitrine, django_capture_on_commit_callbacks):
    from shopman.craftsman import craft
    from shopman.craftsman.models import Recipe

    from shopman.shop.handlers.production_order_sync import (
        ORDER_AWAITING_WO_REFS_KEY,
        link_order_to_work_orders,
    )

    recipe = Recipe.objects.create(ref="rs-baguete", name="Baguete", output_sku=SKU, batch_size=Decimal("10"))
    with django_capture_on_commit_callbacks(execute=True):
        wo_late = craft.plan(recipe, 10, date=_day(6), position_ref="")
        wo_early = craft.plan(recipe, 10, date=_day(3), position_ref="")
    _plan(3, 5, vitrine)
    _plan(6, 5, vitrine)
    order = _encomenda("RS-PROD", 6)
    link_order_to_work_orders(order=order, event_type="status_changed")
    order.refresh_from_db()
    # A ordem mais antiga elegível para o dia 6 é a do próprio dia 6.
    assert order.data[ORDER_AWAITING_WO_REFS_KEY] == [wo_late.ref]

    with django_capture_on_commit_callbacks(execute=True):
        reschedule(order, date=_day(3).isoformat(), slot="slot-09", actor="pos:marina")

    order.refresh_from_db()
    wo_late.refresh_from_db()
    wo_early.refresh_from_db()
    assert order.data[ORDER_AWAITING_WO_REFS_KEY] == [wo_early.ref]
    assert order.ref not in (wo_late.meta or {}).get("committed_order_refs", [])
    assert order.ref in wo_early.meta["committed_order_refs"]


# ── futura → hoje ────────────────────────────────────────────────────────────


def test_futura_para_hoje_ativa_agora(vitrine):
    StockMovements.receive(quantity=Decimal("10"), sku=SKU, position=vitrine, reason="prateleira")
    _plan(3, 5, vitrine)
    order = _encomenda("RS-HOJE", 3)
    lifecycle._schedule_preorder_activation(order)
    schedule_preorder_reminder(order)

    result = reschedule(order, date=timezone.localdate().isoformat(), slot="", actor="pos:marina")

    assert result.activated_now
    order.refresh_from_db()
    assert order.data["is_preorder"] is False
    assert not _live_alarms(order).exists(), "o despertador cumpriu o papel: nada fica na fila"
    assert Directive.objects.filter(topic=PREORDER_ACTIVATE, payload__order_ref=order.ref, status="done").count() == 1
    assert not _pending_reminders(order).exists(), "lembrete de 'amanhã' para pedido de hoje seria mentira"
    holds = _holds(order)
    assert holds and all(h.status == HoldStatus.FULFILLED for h in holds), "a baixa saiu na ativação"


# ── sem saldo: nada muda ─────────────────────────────────────────────────────


def test_sem_saldo_na_data_nova_recusa_e_nada_muda(vitrine):
    # Só há plano para o dia 6: a fornada do dia 6 não existe no dia 3.
    _plan(6, 5, vitrine)
    order = _encomenda("RS-SEM", 6, channel="strict")
    lifecycle._schedule_preorder_activation(order)
    schedule_preorder_reminder(order)
    before_data = dict(order.data)
    alarm = _live_alarms(order).get()
    reminder = _pending_reminders(order).get()
    holds = _holds(order)
    assert holds

    with pytest.raises(RescheduleRefused) as exc:
        reschedule(order, date=_day(3).isoformat(), slot="slot-09", actor="pos:marina")

    assert exc.value.field == "date"
    assert "não tem saldo" in exc.value.message and "Nada foi alterado" in exc.value.message
    order.refresh_from_db()
    assert order.data == before_data
    assert HISTORY_KEY not in order.data
    for hold in holds:
        hold.refresh_from_db()
        assert hold.status == HoldStatus.PENDING and hold.target_date == _day(6)
    alarm.refresh_from_db()
    assert alarm.status == "queued" and timezone.localtime(alarm.available_at).date() == _day(6)
    reminder.refresh_from_db()
    assert reminder.status == "queued" and "notification_delivery" not in reminder.payload
    assert not order.events.filter(type="order_rescheduled").exists()


# ── recusas ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", [Order.Status.CANCELLED, Order.Status.COMPLETED, Order.Status.DELIVERED, Order.Status.DISPATCHED])
def test_pedido_encerrado_nao_reagenda(vitrine, status):
    _plan(3, 5, vitrine)
    order = _encomenda(f"RS-{status}", 3, status=status)

    with pytest.raises(RescheduleRefused) as exc:
        reschedule(order, date=_day(5).isoformat(), slot="slot-09", actor="pos:marina")

    assert exc.value.code == "order_not_reschedulable"
    assert "a data não muda mais" in exc.value.message


def test_pedido_ja_baixado_nao_muda_de_dia(vitrine):
    StockMovements.receive(quantity=Decimal("10"), sku=SKU, position=vitrine, reason="prateleira")
    order = _encomenda("RS-FEITO", 0, slot="")
    stock.fulfill(order)

    with pytest.raises(RescheduleRefused) as exc:
        reschedule(order, date=_day(2).isoformat(), slot="slot-09", actor="pos:marina")

    assert exc.value.code == "already_in_preparation"


def test_data_passada_recusa(vitrine):
    _plan(3, 5, vitrine)
    order = _encomenda("RS-PASS", 3)
    with pytest.raises(RescheduleRefused) as exc:
        reschedule(order, date=_day(-1).isoformat(), slot="", actor="pos:marina")
    assert exc.value.field == "date"
    assert exc.value.message == "Não é possível encomendar para uma data passada."


def test_alem_do_maximo_recusa(vitrine):
    _plan(3, 5, vitrine)
    order = _encomenda("RS-MAX", 3)
    with pytest.raises(RescheduleRefused) as exc:
        reschedule(order, date=_day(31).isoformat(), slot="", actor="pos:marina")
    assert exc.value.message.startswith("Data máxima permitida:")


def test_dia_fechado_recusa(vitrine):
    shop = Shop.load()
    shop.defaults = {**(shop.defaults or {}), "closed_dates": [{"date": _day(5).isoformat(), "label": "Feriado"}]}
    shop.save()
    _plan(3, 5, vitrine)
    order = _encomenda("RS-FECH", 3)
    with pytest.raises(RescheduleRefused) as exc:
        reschedule(order, date=_day(5).isoformat(), slot="", actor="pos:marina")
    assert exc.value.message == "Fechado: Feriado — escolha outra data."


def test_data_invalida_recusa(vitrine):
    _plan(3, 5, vitrine)
    order = _encomenda("RS-INV", 3)
    with pytest.raises(RescheduleRefused) as exc:
        reschedule(order, date="31/12", slot="", actor="pos:marina")
    assert exc.value.code == "invalid_date"


# ── idempotência ─────────────────────────────────────────────────────────────


def test_mesma_data_e_janela_nao_mexe_em_nada(vitrine):
    _plan(3, 5, vitrine)
    order = _encomenda("RS-IDEM", 3)
    lifecycle._schedule_preorder_activation(order)
    schedule_preorder_reminder(order)
    reschedule(order, date=_day(4).isoformat(), slot="slot-09", actor="pos:marina")
    order.refresh_from_db()
    holds_before = order.data["hold_ids"]

    again = reschedule(order, date=_day(4).isoformat(), slot="slot-09", actor="pos:marina")

    assert again.changed is False
    order.refresh_from_db()
    assert len(order.data[HISTORY_KEY]) == 1
    assert order.data["hold_ids"] == holds_before
    assert _live_alarms(order).count() == 1
    assert _pending_reminders(order).count() == 1
    assert order.events.filter(type="order_rescheduled").count() == 1


def test_so_a_janela_muda_nao_toca_estoque(vitrine):
    _plan(3, 5, vitrine)
    order = _encomenda("RS-JAN", 3)
    schedule_preorder_reminder(order)
    holds_before = order.data["hold_ids"]

    reschedule(order, date=_day(3).isoformat(), slot="slot-15", actor="pos:marina")

    order.refresh_from_db()
    assert order.data["hold_ids"] == holds_before
    assert _pending_reminders(order).get().payload["context"]["delivery_time_slot"] == "slot-15"


# ── o despertador que toca cedo não se perde ────────────────────────────────


def test_despertador_que_toca_cedo_volta_para_a_fila(vitrine):
    from shopman.shop.handlers.preorder import PreorderActivateHandler

    _plan(3, 5, vitrine)
    order = _encomenda("RS-CEDO", 3)
    lifecycle._schedule_preorder_activation(order)
    alarm = _live_alarms(order).get()
    alarm.status = "running"
    alarm.attempts = 1
    alarm.available_at = timezone.now()
    alarm.save()

    PreorderActivateHandler().handle(message=alarm, ctx={})

    alarm.refresh_from_db()
    assert alarm.status == "queued"
    assert timezone.localtime(alarm.available_at).date() == _day(3)
    assert alarm.attempts == 0
