"""Desfazer do que o sistema fez e do que o operador entregou (SUITE-UX §5.1, L1).

Duas janelas, cada uma com a sua guarda, ambas decididas pelo dono:

**"Pronto" automático** (``order.data["auto_ready"]``). A Cozinha concluiu todas
as estações do pedido e ``kds.on_all_tickets_done`` levou o pedido a READY. A
transição é imediata (é fato da casa: a Saída e o Gestor precisam ver), mas o
que sai da casa espera a janela: a fase ``on_ready`` do lifecycle (aviso de
"pronto" ao cliente, nota da sacola, corrida do entregador) nasce com
``available_at`` no fim da janela e com o token do registro. Desfazer dentro da
janela reabre o ticket que fechou o pedido e o devolve a PREPARING; o token
some, e a directive segurada vira no-op. Se o pedido sai de READY para frente
antes de a janela vencer (alguém entregou logo), a fase do pronto roda ali
mesmo, antes da saída (``release_ready_hold``): o cliente lê os avisos em ordem.

⚠️ O ``readyToPickup`` do iFood NÃO espera. É o sinal para o entregador do
iFood vir buscar (segurá-lo atrasa a coleta e o tempo de preparo medido pelo
marketplace), o iFood exige o pronto antes do despacho e não tem "desfazer
pronto", e o despacho do entregador dele pode chegar dentro da janela. O
desfazer continua valendo para a casa (o pedido volta ao preparo), e o card
diz que o iFood já foi avisado.

**Entregar/Despachar** (``order.data["pending_handoff"]``). O toque do Gestor
ou da Saída da Cozinha NÃO grava a transição: valida tudo o que a transição
validaria, registra o pedido de saída com um token e agenda
``order.handoff_commit`` para o fim da janela (5 s). Até lá o pedido continua
no status de antes para o resto do sistema; nada sai da casa (aviso ao cliente,
iFood, nota, fidelidade, troco no livro, maquininha) porque nada disso
aconteceu ainda. Desfazer apaga o registro. Quando a janela vence, a directive
roda a MESMA ``operator_orders.advance_order`` com os argumentos do toque.

As chaves estão em ``docs/reference/data-schemas.md``.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone
from shopman.orderman.models import Order

logger = logging.getLogger(__name__)

AUTO_READY_KEY = "auto_ready"
PENDING_HANDOFF_KEY = "pending_handoff"

#: Destinos do toque do Gestor/Saída que ganham a janela de desfazer.
HANDOFF_TARGETS = frozenset({Order.Status.DISPATCHED, Order.Status.DELIVERED, Order.Status.COMPLETED})

_HANDOFF_VERBS = {
    Order.Status.DISPATCHED: "Saiu",
    Order.Status.DELIVERED: "Entregue",
    Order.Status.COMPLETED: "Entregue",
}


class UndoRefused(ValueError):
    """O desfazer não cabe mais: a janela venceu ou o pedido mudou."""


# ── Configuração ─────────────────────────────────────────────────────────


def _fulfillment_config(order):
    from shopman.shop.config import ChannelConfig

    try:
        return ChannelConfig.for_channel(order.channel_ref).fulfillment
    except Exception:
        logger.debug("order_undo: config indisponível channel=%s", order.channel_ref, exc_info=True)
        return ChannelConfig.Fulfillment()


def auto_ready_enabled(order) -> bool:
    return bool(_fulfillment_config(order).auto_ready)


def ready_undo_seconds(order) -> int:
    return max(0, int(_fulfillment_config(order).ready_undo_seconds or 0))


def handoff_undo_seconds(order) -> int:
    return max(0, int(_fulfillment_config(order).handoff_undo_seconds or 0))


# ── Tempo ────────────────────────────────────────────────────────────────


def _parse(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def _clock(value) -> str:
    moment = _parse(value)
    return timezone.localtime(moment).strftime("%H:%M") if moment else ""


# ── "Pronto" automático ──────────────────────────────────────────────────


def auto_ready_record(order) -> dict:
    record = (order.data or {}).get(AUTO_READY_KEY)
    return dict(record) if isinstance(record, dict) else {}


def ready_hold(order, *, now=None) -> dict:
    """O registro do pronto automático cuja janela ainda segura o que sai da casa.

    Vazio quando não há janela aberta: o pedido não está em READY, a janela
    venceu, ou a fase do pronto já rodou (alguém entregou antes do prazo).
    """
    from shopman.shop import lifecycle

    record = auto_ready_record(order)
    if not record.get("token") or order.status != Order.Status.READY:
        return {}
    until = _parse(record.get("undo_until"))
    if until is None or until <= (now or timezone.now()):
        return {}
    if lifecycle.phase_complete(order, "on_ready"):
        return {}
    return record


def record_auto_ready(order, *, ticket_ids, actor: str) -> dict:
    """Grava o registro ANTES da transição (o signal lê ``order.data``).

    Chamado com o pedido travado, por ``kds.on_all_tickets_done``. Sem janela
    configurada, não grava nada: o pronto avisa na hora, como antes.
    """
    seconds = ready_undo_seconds(order)
    if seconds <= 0:
        return {}
    now = timezone.now()
    record = {
        "token": secrets.token_hex(8),
        "at": now.isoformat(),
        "undo_until": (now + timedelta(seconds=seconds)).isoformat(),
        "ticket_ids": [int(pk) for pk in ticket_ids if pk],
        "actor": str(actor or "")[:150],
    }
    data = dict(order.data or {})
    data[AUTO_READY_KEY] = record
    order.data = data
    order.save(update_fields=["data", "updated_at"])
    return record


def clear_auto_ready(order) -> None:
    """Tira o registro (o pedido saiu do pronto para trás). Salva só ``data``."""
    data = dict(order.data or {})
    if AUTO_READY_KEY not in data:
        return
    data.pop(AUTO_READY_KEY, None)
    order.data = data
    order.save(update_fields=["data", "updated_at"])


def undo_auto_ready(order, *, token: str, actor: str, expected_revision: str | None = None) -> None:
    """Desfaz o pronto automático: reabre o ticket que fechou o pedido e volta ao preparo.

    Só dentro da janela, só com o token que a tela leu e só se nada mudou
    (pedido ainda em READY, sem saída pedida). Depois da janela o aviso ao
    cliente já saiu e o pronto não volta mais por aqui; o caminho é a
    estação reabrir o ticket (K06), que segue com as regras dela.
    """
    from shopman.shop.services import kds as kds_service
    from shopman.shop.services import operator_orders

    with transaction.atomic():
        # Ordem de lock de sempre (origem → ticket): o pedido antes dos tickets.
        kds_service._lock_source_for_session(order.session_key)
        Order.objects.select_for_update().get(pk=order.pk)
        order.refresh_from_db()
        if expected_revision is not None and expected_revision != operator_orders.operational_revision(order):
            raise operator_orders.OrderStateConflict("O pedido mudou. Confira o estado atualizado antes de continuar.")
        record = auto_ready_record(order)
        if not token or record.get("token") != token:
            raise UndoRefused("Este pronto já não pode ser desfeito daqui. Atualize o pedido.")
        if order.status != Order.Status.READY or pending_handoff(order):
            raise UndoRefused("O pedido já saiu do pronto. Atualize o pedido.")
        if not ready_hold(order):
            raise UndoRefused("O prazo para desfazer acabou: o cliente já foi avisado.")

        from shopman.shop.adapters import kds as kds_adapter

        reopened = kds_adapter.reopen_done_tickets(order.session_key, record.get("ticket_ids") or [])
        clear_auto_ready(order)
        order.transition_status(Order.Status.PREPARING, actor=actor)
        order.emit_event("auto_ready_undone", actor=actor, payload={"ticket_ids": reopened})
    logger.info("order_undo.auto_ready_undone order=%s tickets=%s actor=%s", order.ref, reopened, actor)


def release_ready_hold(order) -> bool:
    """O pedido sai de READY para frente com a janela do pronto ainda aberta.

    Quem entregou já não pode desfazer o pronto; segurar o aviso não protege
    mais nada e inverteria a ordem dos avisos ao cliente. A fase do pronto roda
    aqui, com o pedido travado, como a directive rodaria. Idempotente: sem
    janela aberta, nada a fazer.
    """
    from shopman.shop import lifecycle

    record = ready_hold(order)
    if not record:
        return False
    lifecycle.dispatch(order, "on_ready")
    order.refresh_from_db()
    return True


def held_until(order, phase: str) -> tuple[datetime | None, str]:
    """Quando o efeito do pronto pode sair, e o token que o segura.

    Usado por ``lifecycle.enqueue_phase`` (fase ``on_ready``). ``(None, "")``
    quando nada segura.
    """
    if phase != "on_ready":
        return None, ""
    record = ready_hold(order)
    if not record:
        return None, ""
    return _parse(record["undo_until"]), record["token"]


def hold_superseded(order, token: str) -> bool:
    """A directive segurada por ``token`` perdeu a razão de existir (desfeita)."""
    if not token:
        return False
    return auto_ready_record(order).get("token") != token


# ── Entregar / Despachar ─────────────────────────────────────────────────


def pending_handoff(order) -> dict:
    record = (order.data or {}).get(PENDING_HANDOFF_KEY)
    return dict(record) if isinstance(record, dict) and record.get("token") else {}


def handoff_window_open(order, *, now=None) -> bool:
    record = pending_handoff(order)
    until = _parse(record.get("commit_at")) if record else None
    return bool(until and until > (now or timezone.now()))


def handoff_label(record: dict) -> str:
    """'Entregue às 14:02' / 'Saiu às 14:02', na voz do card."""
    verb = _HANDOFF_VERBS.get(record.get("to_status"), "Entregue")
    clock = _clock(record.get("requested_at"))
    return f"{verb} às {clock}" if clock else verb


def request_handoff(
    order,
    *,
    to_status: str,
    actor: str,
    seconds: int,
    change_out_q: int | None = None,
    cash_shift=None,
    equipment: list[str] | None = None,
    trip_ref: str | None = None,
) -> dict:
    """Registra o toque de saída e agenda a gravação para o fim da janela.

    Chamado por ``operator_orders.advance_order`` com o pedido travado e tudo
    já validado. Grava só o registro (``order.data``) e a directive; a
    transição, o troco no livro, a maquininha e os tickets ficam para
    ``commit_handoff``.
    """
    from shopman.shop.directives import ORDER_HANDOFF_COMMIT, create_deduped

    now = timezone.now()
    record = {
        "token": secrets.token_hex(8),
        "from_status": order.status,
        "to_status": to_status,
        "requested_at": now.isoformat(),
        "commit_at": (now + timedelta(seconds=seconds)).isoformat(),
        "actor": str(actor or "")[:150],
        "change_out_q": None if change_out_q is None else int(change_out_q),
        "cash_shift_id": getattr(cash_shift, "pk", None),
        "equipment": list(equipment or []),
        "trip_ref": trip_ref or "",
    }
    data = dict(order.data or {})
    data[PENDING_HANDOFF_KEY] = record
    order.data = data
    order.save(update_fields=["data", "updated_at"])
    order.emit_event(
        "handoff_requested", actor=actor,
        payload={"to_status": to_status, "commit_at": record["commit_at"]},
    )
    create_deduped(
        ORDER_HANDOFF_COMMIT,
        payload={"order_ref": order.ref, "token": record["token"]},
        dedupe_key=f"{ORDER_HANDOFF_COMMIT}:{order.ref}:{record['token']}",
        available_at=now + timedelta(seconds=seconds),
    )
    return record


def _drop_pending(order) -> None:
    data = dict(order.data or {})
    data.pop(PENDING_HANDOFF_KEY, None)
    order.data = data
    order.save(update_fields=["data", "updated_at"])


def undo_handoff(order, *, token: str, actor: str) -> None:
    """Desfaz o toque de Entregar/Despachar dentro da janela. Nada saiu da casa."""
    with transaction.atomic():
        Order.objects.select_for_update().get(pk=order.pk)
        order.refresh_from_db()
        record = pending_handoff(order)
        if not token or record.get("token") != token:
            raise UndoRefused("Esta saída já não pode ser desfeita daqui. Atualize o pedido.")
        if order.status != record.get("from_status"):
            raise UndoRefused("O pedido mudou. Atualize o pedido.")
        if not handoff_window_open(order):
            raise UndoRefused("O prazo para desfazer acabou.")
        _drop_pending(order)
        order.emit_event("handoff_undone", actor=actor, payload={"to_status": record.get("to_status")})
    logger.info("order_undo.handoff_undone order=%s to=%s actor=%s", order.ref, record.get("to_status"), actor)


def commit_handoff(order_ref: str, token: str, *, now=None) -> str:
    """Grava a saída pedida quando a janela vence. Devolve o status final, ou ''.

    Idempotente e seguro contra a corrida com o desfazer: decide sob o lock do
    pedido. Token que não bate (desfeito, ou já gravado) é no-op; janela ainda
    aberta é no-op (quem chama antes do prazo não grava). Se a gravação for
    recusada (o turno de caixa fechou, a maquininha foi para outra saída), o
    registro sai, o pedido fica onde estava e o Gestor recebe um aviso.
    """
    from shopman.shop.services import operator_orders
    from shopman.shop.services.observability import create_operator_alert

    refusal = ""
    with transaction.atomic():
        order = Order.objects.select_for_update().filter(ref=order_ref).first()
        if order is None:
            return ""
        record = pending_handoff(order)
        if not token or record.get("token") != token:
            return ""
        if handoff_window_open(order, now=now):
            return ""
        if order.status != record.get("from_status"):
            _drop_pending(order)
            return ""
        cash_shift = None
        if record.get("cash_shift_id"):
            from shopman.cashman.models import Shift

            cash_shift = Shift.objects.filter(pk=record["cash_shift_id"]).first()
        try:
            with transaction.atomic():
                return operator_orders.advance_order(
                    order,
                    actor=record.get("actor") or "system:handoff",
                    change_out_q=record.get("change_out_q"),
                    cash_shift=cash_shift,
                    equipment=record.get("equipment") or [],
                    target_status=record.get("to_status"),
                    trip_ref=record.get("trip_ref") or None,
                    handoff_token=token,
                )
        except (ValueError, operator_orders.ChangeOutRequired) as exc:
            refusal = str(exc) or "A saída foi recusada."
            order.refresh_from_db()
            _drop_pending(order)
            order.emit_event("handoff_refused", actor="system:handoff", payload={"reason": refusal[:300]})
    logger.warning("order_undo.handoff_refused order=%s reason=%s", order_ref, refusal)
    create_operator_alert(
        type="handoff_refused",
        severity="warning",
        order_ref=order_ref,
        message=(
            f"A saída do pedido {order_ref} não foi gravada: {refusal} "
            "O pedido continua onde estava. Confira e toque de novo."
        ),
        dedupe_key=f"handoff_refused:{order_ref}:{token}",
    )
    return ""


def settle_pending_handoff(order, *, force: bool = False) -> str:
    """Grava agora a saída pendente: a vencida (o worker ainda não passou) ou,
    com ``force``, a que ainda está na janela, porque um fato de fora (iFood,
    entregador) chegou e não espera o desfazer de uma tela."""
    record = pending_handoff(order)
    if not record or (handoff_window_open(order) and not force):
        return ""
    now = None
    if force:
        now = (_parse(record.get("commit_at")) or timezone.now()) + timedelta(seconds=1)
    return commit_handoff(order.ref, record["token"], now=now)
