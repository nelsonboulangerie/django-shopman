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
import re

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
    "card_authorization_expiring",
)

#: A corrida da central: a entrega terminou ou o pedido acabou.
COURIER_TYPES = (
    "courier_dispatch_failed",
    "courier_not_attended",
    "courier_ride_cancelled",
)

#: Chegou ao cliente: o que era "antes de a sacola sair" perde o sentido. O
#: ``stock_hold_gap`` avisa que o item "pode faltar na separação": separado e
#: entregue, o aviso acabou (a venda acima do estoque já está no ledger).
RESOLVED_BY_DELIVERY = (
    *COURIER_TYPES, "danfe_print_failed", "preorder_activation_blocked_unpaid", "stock_hold_gap",
)

#: Cancelado ou devolvido, o ``on_cancelled``/``on_returned`` estorna TODO intent
#: capturado do pedido, inclusive o Pix registrado à parte por ter caído numa
#: cobrança encerrada. "Confira e devolva pelo gateway" deixa de ser verdade, e
#: seguir a instrução devolveria duas vezes (beta 06/11, PIXEXP-01). Estorno que
#: falhar tem alerta próprio (``payment_refund_failed``).
RESOLVED_BY_REFUND = ("pix_on_closed_charge",)

#: Desfeito: nada mais vai sair, nem sacola, nem corrida, nem cozinha.
RESOLVED_BY_UNDO = (*RESOLVED_BY_LEAVING_NEW, *RESOLVED_BY_DELIVERY, *RESOLVED_BY_REFUND)


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
        transaction.on_commit(lambda: _resolve_emit_integration_failure(ref))


def _resolve_emit_integration_failure(ref: str) -> None:
    """A nota deste pedido saiu: a falha de integração na emissão dele acabou (#3097).

    O aviso é por pedido no texto (``fiscal:emit_nfce:pedido <ref>: ...``), sem
    ``order_ref``; o marcador nas duas grafias que o código grava.
    """
    from shopman.shop.adapters import alert as alert_adapter

    for word in ("pedido", "Pedido"):
        try:
            alert_adapter.resolve_matching(
                "integration_failed",
                message_contains=f"Dedupe: fiscal:emit_nfce:{word} {ref}:",
                actor="nfce-authorized",
            )
        except Exception:
            logger.exception("alert_resolution.emit_integration_failed", extra={"order_ref": ref})


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


#: O marcador que ``create_operator_alert`` grava no fim da mensagem da etapa travada.
_PHASE_STUCK_MARKER = re.compile(r"Dedupe: lifecycle_phase_stuck:(?P<ref>[^:\s]+):(?P<phase>on_\w+)")


def resolve_superseded_phase_alerts() -> int:
    """Fecha a "etapa travada" cuja etapa não deve mais nada. Retroativo de propósito.

    O fato é do domínio (``lifecycle``): a etapa concluiu (marcador ``done``), ou foi
    superada (``phase_superseded``: pedido de teste, ou o preparo que chegou com o
    pedido já fechado). Desde o #3039 esses casos nem abrem alerta; aqui fecham os que
    nasceram antes (os nove de 18 e 19/11/2026, #3029), e qualquer outro que a etapa
    supere depois. Quem fecha aparece como o sistema, com o motivo.

    O caso real (pedido de verdade, etapa que não pode mais rodar) fica aberto: é
    travamento, e quem decide é gente.
    """
    from shopman.orderman.models import Order

    from shopman.shop import lifecycle
    from shopman.shop.adapters import alert as alert_adapter

    closed = 0
    for pk, order_ref, message in alert_adapter.open_rows("lifecycle_phase_stuck"):
        found = _PHASE_STUCK_MARKER.search(message or "")
        if not found:
            continue
        ref = order_ref or found.group("ref")
        phase = found.group("phase")
        order = Order.objects.filter(ref=ref).first()
        if order is None:
            continue
        if lifecycle.phase_complete(order, phase):
            why = "etapa concluída depois"
        elif lifecycle.phase_superseded(order, phase):
            why = "pedido de teste" if lifecycle.is_test_order(order) else f"pedido já {order.status}, etapa superada"
        else:
            continue
        try:
            closed += alert_adapter.resolve_pk(pk, actor=f"sistema: {why}")
        except Exception:
            logger.exception("alert_resolution.superseded_failed", extra={"alert_pk": pk, "order_ref": ref})
    return closed


#: Tipos que o código não cria mais: o aviso aberto é resto de versão antiga, e
#: ninguém mais tem o gesto que o fecharia.
RETIRED_TYPES = frozenset({"customer_cancellation_requested"})

#: O fato do lote que encerra cada aviso de produção (o mesmo de
#: ``production_alerts._RESOLVED_ALERT_TYPES_BY_ACTION``, lido do estado do lote).
_WORK_ORDER_ACTION_BY_STATUS = {"started": "started", "finished": "finished", "void": "voided"}
_WORK_ORDER_STATE_WORDS = {"started": "aberto", "finished": "fechado", "void": "cancelado"}


def _is_seed_order(order) -> bool:
    """Pedido que o ``seed`` criou: marca no snapshot ou na chave de sessão."""

    return bool((order.snapshot or {}).get("seed")) or str(order.session_key or "").startswith("seed-")


def _is_seed_work_order(work_order) -> bool:
    return str(work_order.source_ref or "").startswith("seed:") or bool((work_order.meta or {}).get("seed"))


def _synthetic_reason(alert_type: str, ref: str) -> str:
    """O fato que encerra o aviso, ou ``""`` quando ele é de gente."""

    if alert_type in RETIRED_TYPES:
        return "tipo que o código não cria mais"
    if not ref:
        return ""
    if ref.startswith("WO-"):
        from shopman.craftsman.models import WorkOrder

        from shopman.shop.handlers.production_alerts import _RESOLVED_ALERT_TYPES_BY_ACTION

        work_order = WorkOrder.objects.filter(ref=ref).first()
        if work_order is None:
            return "lote que não existe mais"
        if _is_seed_work_order(work_order):
            return "lote do seed"
        action = _WORK_ORDER_ACTION_BY_STATUS.get(work_order.status, "")
        if alert_type in _RESOLVED_ALERT_TYPES_BY_ACTION.get(action, ()):
            return f"lote já {_WORK_ORDER_STATE_WORDS[work_order.status]}"
        return ""
    from shopman.orderman.models import Order

    from shopman.shop import lifecycle

    order = Order.objects.filter(ref=ref).first()
    if order is None:
        return ""
    if lifecycle.is_test_order(order):
        return "pedido de teste"
    if _is_seed_order(order):
        return "pedido do seed"
    status = str(order.status)
    if status in {"delivered", "completed"} and alert_type in (*RESOLVED_BY_LEAVING_NEW, *RESOLVED_BY_DELIVERY):
        return "pedido já entregue"
    if status in {"cancelled", "returned"} and alert_type in RESOLVED_BY_UNDO:
        return "pedido já desfeito"
    if status != "new" and alert_type in RESOLVED_BY_LEAVING_NEW:
        return "pedido já saiu de novo"
    return ""


def resolve_alerts_ended_by_fact() -> int:
    """Fecha o aviso que um fato já encerrou. Retroativo de propósito.

    - objeto de ensaio: pedido de teste ou do seed, lote do seed;
    - estado que já encerrou o aviso: pedido entregue ou desfeito, lote aberto,
      fechado ou cancelado. É a mesma regra que o ciclo aplica na hora
      (:func:`on_order_changed`, ``production_alerts``), valendo para os avisos
      que nasceram antes dela;
    - tipo que o código não cria mais.

    No padrão do
    :func:`resolve_superseded_phase_alerts`: quem fecha aparece como o sistema,
    com o motivo.

    O que não tem fato fica aberto: pedido de verdade, lote real esquecido,
    aviso sem objeto. Pedido que não existe mais também fica: a ref pode não ser
    de pedido, e na dúvida o aviso é de gente.
    """
    from shopman.shop.adapters import alert as alert_adapter

    closed = 0
    for pk, alert_type, order_ref in alert_adapter.open_rows_with_ref():
        try:
            why = _synthetic_reason(alert_type, str(order_ref or ""))
            if why:
                closed += alert_adapter.resolve_pk(pk, actor=f"sistema: {why}")
        except Exception:
            logger.exception("alert_resolution.synthetic_failed", extra={"alert_pk": pk, "order_ref": order_ref})
    return closed
