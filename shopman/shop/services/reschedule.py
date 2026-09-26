"""Reagendar uma encomenda: trocar a data (e a janela) combinada com o cliente.

Mudar a data não é reescrever duas chaves. A data está costurada em cinco lugares,
e cada um precisa ir junto — senão a encomenda de sábado vira sábado no papel e
terça na cozinha:

1. ``Order.data.delivery_date``/``delivery_time_slot`` (+ ``is_preorder``) e a
   trilha ``reschedule_history`` (``docs/reference/data-schemas.md``);
2. o despertador ``preorder.activate:{ref}`` — a directive viva é MOVIDA, nunca
   duplicada; data nova = hoje ⇒ ativa agora pelo caminho de sempre
   (``lifecycle.activate_preorder``);
3. o lembrete de véspera (``preorder_reminder``), que congela data e janela no
   ``context`` — o pendente é fechado sem envio e outro nasce para a data nova;
4. as reservas de estoque (``hold.target_date``) — soltas e refeitas na data nova
   pelo gate de commit (``stock.hold(require_all=True)``): sem saldo, recusa e
   NADA muda;
5. o vínculo com a produção (``production_order_sync``), recalculado depois do
   commit pelo reconciliador canônico (mesma ordem de locks dele).

Tudo numa transação, sob o lock do pedido. Idempotente: a mesma data e a mesma
janela não mexem em nada.

⚠️ **Pedido que já foi para a cozinha não muda de dia.** Com ticket de KDS, baixa
de estoque feita ou status "em preparo", trocar a data exigiria desfazer a baixa
e cancelar tickets — uma devolução disfarçada. Recusa com o motivo; o caminho é
cancelar e registrar de novo. A JANELA do mesmo dia continua trocável: ela não
toca estoque, cozinha nem produção.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, timedelta
from datetime import time as time_type

from django.db import transaction
from django.utils import timezone
from shopman.orderman.models import Directive, Order

logger = logging.getLogger(__name__)

HISTORY_KEY = "reschedule_history"
EVENT_TYPE = "order_rescheduled"
REMINDER_TEMPLATE = "preorder_reminder"
# Aviso ao cliente: o gancho fica pronto e só dispara quando existir o texto
# (``notification_copy.CUSTOMER_COPY``) — e, para o WhatsApp fora da janela de
# 24h, o template aprovado na Meta. Inventar a mensagem aqui mandaria texto que
# ninguém revisou.
CUSTOMER_NOTICE_TEMPLATE = "order_rescheduled"

_REFUSED_STATUSES = {
    Order.Status.READY.value: "já está pronto",
    Order.Status.DISPATCHED.value: "já saiu para entrega",
    Order.Status.DELIVERED.value: "já foi entregue",
    Order.Status.COMPLETED.value: "já foi concluído",
    Order.Status.CANCELLED.value: "foi cancelado",
    Order.Status.RETURNED.value: "foi devolvido",
}


class RescheduleRefused(ValueError):
    """A troca de data não pode ser feita. Nada foi alterado.

    ``field`` diz qual entrada a tela deve apontar (``date``/``slot``) quando a
    recusa é sobre ela; vazio quando é sobre o pedido.
    """

    def __init__(self, message: str, *, code: str, field: str = ""):
        super().__init__(message)
        self.message = message
        self.code = code
        self.field = field


@dataclass(frozen=True)
class RescheduleResult:
    changed: bool
    from_date: str
    from_slot: str
    to_date: str
    to_slot: str
    activated_now: bool = False


def reschedule(order, *, date, slot, actor: str, reason: str = "") -> RescheduleResult:
    """Troca a data/janela combinada do pedido, levando junto tudo que depende dela."""
    new_day = _parse_day(date)
    new_slot = str(slot or "").strip()
    reason = str(reason or "").strip()

    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        _refuse_by_state(locked)

        data = dict(locked.data or {})
        from_date = str(data.get("delivery_date") or "")
        from_slot = str(data.get("delivery_time_slot") or "")
        from_day = _commitment_day(locked)
        to_date = new_day.isoformat()

        if from_date == to_date and from_slot == new_slot:
            return RescheduleResult(False, from_date, from_slot, to_date, new_slot)

        _validate(locked, new_day, new_slot)

        today = timezone.localdate()
        date_changes = from_day != new_day
        if date_changes and _physical_work_started(locked):
            raise RescheduleRefused(
                "Este pedido já está em preparo: a data não muda mais. "
                "Para outro dia, cancele e registre uma nova encomenda.",
                code="already_in_preparation",
            )

        history = list(data.get(HISTORY_KEY) or [])
        history.append({
            "from_date": from_date,
            "from_slot": from_slot,
            "to_date": to_date,
            "to_slot": new_slot,
            "actor": actor,
            "at": timezone.now().isoformat(),
            "reason": reason,
        })
        data.update({
            "delivery_date": to_date,
            "delivery_time_slot": new_slot,
            "is_preorder": new_day > today,
            HISTORY_KEY: history,
        })
        locked.data = data
        locked.save(update_fields=["data", "updated_at"])

        activated_now = False
        if date_changes:
            _move_holds(locked, new_day)
            activated_now = _move_activation(locked, new_day, today=today)
            _replace_reminder(locked, new_day, today=today)
            _relink_production(locked)
        else:
            # Só a janela mudou: o lembrete congela a janela no texto.
            _replace_reminder(locked, new_day, today=today)

        event_payload = {
            "from_date": from_date,
            "from_slot": from_slot,
            "to_date": to_date,
            "to_slot": new_slot,
        }
        if reason:
            event_payload["reason"] = reason
        locked.emit_event(event_type=EVENT_TYPE, actor=actor, payload=event_payload)
        _notify_customer(locked)

    order.refresh_from_db()
    logger.info(
        "reschedule: order=%s %s/%s -> %s/%s actor=%s activated_now=%s",
        order.ref, from_date, from_slot, to_date, new_slot, actor, activated_now,
    )
    return RescheduleResult(True, from_date, from_slot, to_date, new_slot, activated_now)


# ── Validação ────────────────────────────────────────────────────────────────


def _parse_day(value) -> date_type:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date_type):
        return value
    try:
        return date_type.fromisoformat(str(value or "").strip())
    except ValueError:
        raise RescheduleRefused("Data inválida. Escolha uma data da lista.", code="invalid_date", field="date") from None


def state_refusal(order) -> str:
    """Por que a data deste pedido não muda mais — ou ``""``.

    A mesma régua de :func:`reschedule` (estado e marketplace), para a tela
    decidir se oferece o gesto. Validação da data escolhida e "já em preparo"
    continuam no serviço: dependem da data nova.
    """
    try:
        _refuse_by_state(order)
    except RescheduleRefused as exc:
        return exc.message
    return ""


def _refuse_by_state(order) -> None:
    from shopman.shop.services import ifood_schedule

    label = _REFUSED_STATUSES.get(str(order.status))
    if label:
        raise RescheduleRefused(
            f"Este pedido {label}: a data não muda mais.", code="order_not_reschedulable",
        )
    if order.channel_ref == "ifood" or ifood_schedule.is_scheduled(order):
        raise RescheduleRefused(
            "A data do pedido do iFood é combinada no iFood.", code="marketplace_schedule",
        )


def _validate(order, day: date_type, slot: str) -> None:
    """As réguas que já existem — nenhuma reimplementada aqui."""
    from shopman.shop.services import fulfillment_window, preorder_dates
    from shopman.shop.services.pos_intent import PosIntentError
    from shopman.shop.services.pos_sales_mode import order_sales_mode, validate_sales_mode

    data = order.data or {}
    if data.get("origin_channel") == "pos":
        # Venda de balcão é "levar agora": a régua do PDV recusa data nela.
        try:
            validate_sales_mode(
                {
                    "sales_mode": order_sales_mode(order),
                    "fulfillment_type": data.get("fulfillment_type"),
                    "delivery_date": day.isoformat(),
                    "delivery_time_slot": slot,
                },
                require_ready=False,
            )
        except PosIntentError as exc:
            raise RescheduleRefused(exc.message, code=exc.code, field="date") from None

    refusal = preorder_dates.date_refusal(day)
    if refusal:
        raise RescheduleRefused(refusal, code="invalid_date", field="date")

    error = fulfillment_window.validate(day, slot, _order_skus(order))
    if error:
        raise RescheduleRefused(error, code="invalid_slot", field="slot")


def _physical_work_started(order) -> bool:
    """O pedido já foi para a cozinha ou já baixou estoque?"""
    if order.status == Order.Status.PREPARING:
        return True
    if order.session_key:
        try:
            from shopman.shop.adapters import kds as kds_adapter

            if kds_adapter.ticket_exists_for_order(order):
                return True
        except ImportError:
            pass
    from shopman.shop.adapters import get_adapter

    adapter = get_adapter("stock")
    for entry in (order.data or {}).get("hold_ids") or []:
        hold_id = entry.get("hold_id")
        if hold_id and adapter.hold_state(hold_id) == "fulfilled":
            return True
    return False


# ── Os cinco lugares ─────────────────────────────────────────────────────────


def _move_holds(order, day: date_type) -> None:
    """Solta as reservas da data antiga e refaz na nova pelo gate de commit.

    ``require_all=True`` é a mesma régua do commit: saldo insuficiente, produto
    pausado ou antecedência (lead time) levantam, e a transação inteira volta —
    as reservas antigas inclusive.
    """
    from shopman.orderman.exceptions import ValidationError

    from shopman.shop.services import stock

    if "hold_ids" not in (order.data or {}):
        return  # pedido sem reserva (teste de marketplace, integração): nada a mover
    stock.release(order)
    data = dict(order.data or {})
    data.pop("hold_ids", None)
    data.pop("stock_ceded_holds", None)
    order.data = data
    try:
        stock.hold(order, require_all=True)
    except ValidationError as exc:
        raise RescheduleRefused(_stock_refusal(order, exc, day), code=exc.code, field="date") from None


def _stock_refusal(order, exc, day: date_type) -> str:
    context = getattr(exc, "context", None) or {}
    if exc.code == "insufficient_stock":
        sku = context.get("sku") or context.get("component_sku") or ""
        name = next(
            (item.get("name") for item in (order.snapshot or {}).get("items", []) if item.get("sku") == sku),
            None,
        ) or sku
        if context.get("error_code") == "SKU_PAUSED":
            return f"{name} está pausado no cardápio. Nada foi alterado."
        return f"{name} não tem saldo para {day.strftime('%d/%m/%Y')}. Nada foi alterado."
    return f"{exc.message} Nada foi alterado."


def _move_activation(order, day: date_type, *, today: date_type) -> bool:
    """Move o despertador vivo; data nova = hoje ⇒ ativa agora. True se ativou."""
    from shopman.shop import lifecycle
    from shopman.shop.config import ChannelConfig
    from shopman.shop.directives import PREORDER_ACTIVATE

    live = (
        Directive.objects.select_for_update()
        .filter(topic=PREORDER_ACTIVATE, dedupe_key=f"preorder.activate:{order.ref}", status__in=("queued", "running"))
        .order_by("pk")
        .first()
    )
    if live is not None and live.status == "running":
        raise RescheduleRefused(
            "A encomenda está sendo enviada para a cozinha neste instante. Atualize o pedido e tente de novo.",
            code="activation_running",
        )

    if day > today:
        available_at, target = lifecycle.preorder_activation_at(order)
        if live is not None:
            live.available_at = available_at
            live.payload = {**(live.payload or {}), "delivery_date": target.isoformat()}
            live.save(update_fields=["available_at", "payload", "updated_at"])
            return False
        # Sem despertador: o pedido era de hoje e ainda não tinha ido para a
        # cozinha. Arma o despertador nas mesmas condições em que o aceite o
        # armaria — aceito e com o pagamento que libera o trabalho físico. O
        # pedido novo ou à espera do Pix arma sozinho quando avançar.
        if order.status == Order.Status.ACCEPTED:
            config = ChannelConfig.for_channel(order.channel_ref)
            if not lifecycle._requires_payment_before_physical_work(order, config) or lifecycle._payment_is_captured(order):
                lifecycle._schedule_preorder_activation(order)
        return False

    # Data nova é hoje. Só há o que ativar quando o despertador existia: é ele
    # que prova que o pedido estava aceito, pago e esperando o dia.
    if live is None:
        return False
    live.status = "done"
    live.last_error = ""
    live.save(update_fields=["status", "last_error", "updated_at"])
    lifecycle.activate_preorder(order)
    return True


def _replace_reminder(order, day: date_type, *, today: date_type) -> None:
    """Fecha o lembrete de véspera pendente e agenda outro para a data nova."""
    for pending in (
        Directive.objects.select_for_update()
        .filter(topic="notification.send", status="queued", payload__order_ref=order.ref, payload__template=REMINDER_TEMPLATE)
        .order_by("pk")
    ):
        payload = dict(pending.payload or {})
        if (payload.get("notification_delivery") or {}).get("status"):
            continue  # o envio já começou: não se desfaz um aviso em trânsito
        payload["notification_delivery"] = {
            "status": "skipped",
            "reason": "rescheduled",
            "recorded_at": timezone.now().isoformat(),
        }
        pending.payload = payload
        pending.status = "done"
        pending.save(update_fields=["payload", "status", "updated_at"])
    if day > today:
        schedule_preorder_reminder(order)


def schedule_preorder_reminder(order) -> Directive | None:
    """O mesmo lembrete de véspera que o ``CommitService`` agenda no commit.

    Espelho deliberado de ``orderman.services.commit`` (o Core não importa o
    orquestrador, e o commit continua sendo o dono do lembrete original): 09:00 do
    dia anterior, com data, janela, nome e resumo dos itens congelados no
    ``context``. Mudou lá, muda aqui.
    """
    data = order.data or {}
    try:
        delivery_day = date_type.fromisoformat(str(data.get("delivery_date") or ""))
    except ValueError:
        return None
    reminder_at = datetime.combine(delivery_day - timedelta(days=1), time_type(9, 0))
    if timezone.is_naive(reminder_at):
        reminder_at = timezone.make_aware(reminder_at)
    items = (order.snapshot or {}).get("items") or []
    items_summary = ", ".join(
        f"{item.get('qty', '')}x {item.get('name', item.get('sku', ''))}" for item in items[:5]
    )
    return Directive.objects.create(
        topic="notification.send",
        available_at=reminder_at,
        payload={
            "order_ref": order.ref,
            "template": REMINDER_TEMPLATE,
            "context": {
                "customer_name": (data.get("customer") or {}).get("name", ""),
                "delivery_date": data["delivery_date"],
                "delivery_time_slot": data.get("delivery_time_slot", ""),
                "items_summary": items_summary,
                "fulfillment_type": data.get("fulfillment_type", "pickup"),
            },
        },
    )


def _relink_production(order) -> None:
    """Recalcula o vínculo com as ordens de produção depois do commit.

    O reconciliador trava WorkOrder → Order; aqui já seguramos o Order. Rodar
    dentro da transação inverteria a ordem dos locks, então vai pelo mesmo
    ``on_commit`` que o signal do pedido usa.
    """
    from shopman.shop.handlers.production_order_sync import queue_order_to_work_order_sync

    queue_order_to_work_order_sync(order=order, event_type="")


def _notify_customer(order) -> None:
    from shopman.shop.notification_copy import CUSTOMER_COPY

    if CUSTOMER_NOTICE_TEMPLATE not in CUSTOMER_COPY:
        logger.info(
            "reschedule: sem texto de aviso '%s' — cliente não avisado automaticamente order=%s",
            CUSTOMER_NOTICE_TEMPLATE, order.ref,
        )
        return
    from shopman.shop.services import notification

    notification.send(order, CUSTOMER_NOTICE_TEMPLATE)


# ── Leituras ─────────────────────────────────────────────────────────────────


def _commitment_day(order) -> date_type:
    from shopman.shop.services.order_helpers import get_commitment_date

    return get_commitment_date(order) or timezone.localdate(order.created_at or timezone.now())


def _order_skus(order) -> list[str]:
    return [
        sku
        for item in (order.snapshot or {}).get("items", [])
        if isinstance(item, dict) and (sku := str(item.get("sku") or "").strip())
    ]
