"""Alerta de pedido que a própria operação resolveu some sozinho.

O sino do Gestor só fecha o que o sistema resolve (``resolved_at``); "Visto"
registra ciência e não tira nada da lista. Até aqui quase nenhum alerta de
pedido era resolvido, então o contador só crescia: o pedido era aceito e
"pagamento esperando aceite" continuava lá; a nota autorizava e "NFC-e sem
emissão" continuava lá, e ainda mantinha o pedido em "NFC-e falhou".

Aqui mora a regra de "qual fato encerra qual alerta" que cabe no ciclo do
pedido. Os que dependem de um gesto específico ficam no serviço do gesto:
maquininha que volta (``operator_orders._stamp_equipment_back``), corrida
aceita (``courier``), nota reprocessada (``backstage.services.orders``) e
DANFE impressa (``backstage.services.order_danfe``).
"""

from __future__ import annotations

import logging

from django.db import transaction

logger = logging.getLogger(__name__)

#: A nota foi autorizada: a emissão que falhou, a saída sem nota, o pagamento
#: que barrava a nota e a nota prometida deixam de ser verdade.
RESOLVED_BY_AUTHORIZATION = (
    "fiscal_emit_failed",
    "fiscal_handoff_without_nfce",
    "fiscal_payment_mismatch",
    "fiscal_receipt_promised",
)

#: O pedido saiu de "novo" (aceito, recusado, cancelado): ninguém mais espera a
#: decisão da casa.
RESOLVED_BY_LEAVING_NEW = (
    "stale_new_order",
    "payment_awaiting_confirmation",
)

#: A corrida da central: a entrega terminou ou o pedido acabou.
COURIER_TYPES = (
    "courier_dispatch_failed",
    "courier_not_attended",
    "courier_ride_cancelled",
)

#: Chegou ao cliente: o que era "antes de a sacola sair" perde o sentido.
RESOLVED_BY_DELIVERY = (*COURIER_TYPES, "danfe_print_failed", "preorder_activation_blocked_unpaid")

#: Desfeito: nada mais vai sair, nem sacola, nem corrida, nem cozinha.
RESOLVED_BY_UNDO = (*RESOLVED_BY_LEAVING_NEW, *RESOLVED_BY_DELIVERY)


def resolve(order_ref: str, types, *, actor: str) -> None:
    """Resolve os alertas abertos destes tipos para o pedido. Nunca levanta."""
    from shopman.shop.adapters import alert as alert_adapter

    if not order_ref:
        return
    for alert_type in types:
        try:
            alert_adapter.resolve(alert_type, order_ref=order_ref, actor=actor)
        except Exception:
            logger.exception(
                "alert_resolution.failed",
                extra={"order_ref": order_ref, "alert_type": alert_type},
            )


def resolve_on_commit(order_ref: str, types, *, actor: str) -> None:
    transaction.on_commit(lambda: resolve(order_ref, types, actor=actor))


def on_order_changed(sender, order, event_type, actor=None, **kwargs) -> None:
    if event_type != "status_changed":
        return
    status = str(order.status)
    who = f"order-status:{actor or 'system'}"
    if status in {"cancelled", "returned"}:
        resolve_on_commit(order.ref, RESOLVED_BY_UNDO, actor=who)
    elif status in {"delivered", "completed"}:
        resolve_on_commit(order.ref, (*RESOLVED_BY_LEAVING_NEW, *RESOLVED_BY_DELIVERY), actor=who)
    elif status != "new":
        resolve_on_commit(order.ref, RESOLVED_BY_LEAVING_NEW, actor=who)


def on_nfce_authorized(sender, order=None, **kwargs) -> None:
    ref = getattr(order, "ref", "")
    if ref:
        resolve_on_commit(ref, RESOLVED_BY_AUTHORIZATION, actor="nfce-authorized")


def connect() -> None:
    from shopman.orderman.signals import order_changed

    from shopman.shop.signals import nfce_authorized

    order_changed.connect(
        on_order_changed,
        dispatch_uid="shopman.shop.alert_resolution.on_order_changed",
        weak=False,
    )
    nfce_authorized.connect(
        on_nfce_authorized,
        dispatch_uid="shopman.shop.alert_resolution.on_nfce_authorized",
        weak=False,
    )
