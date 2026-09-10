"""Piloto automático de staging — o operador de mentira que aperta botões de verdade.

Um testador sozinho no staging não tem cozinha nem gestor do outro lado. Sem
ninguém no backstage o pedido dele para em "Aceito" (a loja online tem
``fulfillment.prep_start="operator"`` de propósito) e a cascata de estados nunca
é vista até o fim. Este módulo fecha esse buraco SEM inventar um lifecycle
paralelo:

  order_changed → agenda Directive ``staging.autopilot`` (available_at = now + delay)
  handler       → chama o MESMO service do gestor (confirm_order / advance_order)
  a transição   → dispara order_changed de novo → agenda o próximo passo

Cada salto passa pelos guardas reais (pagamento capturado, encomenda na data,
transição válida na máquina de estados). Se um guarda bloqueia, o passo é
reagendado; se um operador de verdade mexeu no pedido no meio do caminho, o
passo vira no-op (o status gravado no payload não bate mais).

⚠️ NUNCA em produção. O check ``SHOPMAN_E012`` recusa o boot com
``SHOPMAN_ENVIRONMENT=production`` e :func:`is_enabled` se cala por garantia.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.directives import STAGING_AUTOPILOT, create_deduped
from shopman.shop.environment import environment_name, is_production

logger = logging.getLogger(__name__)

# Status de onde o piloto tem um próximo passo a dar. NEW sai por
# ``confirm_order``; o resto sai por ``advance_order`` (o mesmo botão "avançar"
# do gestor). Terminais (concluído/cancelado/devolvido) não estão aqui.
AUTOPILOT_STATUSES = (
    Order.Status.NEW,
    Order.Status.ACCEPTED,
    Order.Status.PREPARING,
    Order.Status.READY,
    Order.Status.DISPATCHED,
    Order.Status.DELIVERED,
)

# Teto de reagendamentos por passo. Um pedido que fica preso num guarda (PIX
# nunca pago, encomenda para daqui a duas semanas) para de gerar directive em
# vez de bater no banco a cada 30s pelo resto da vida do staging.
MAX_DEFERRALS = 20


def is_enabled() -> bool:
    """True quando o piloto pode agir NESTE deployment.

    Dupla trava: a flag precisa estar ligada E o ambiente não pode ser
    produção. O check de sistema já recusaria o boot nessa combinação, mas um
    settings sobrescrito em runtime não pode abrir a porta.
    """
    if not getattr(settings, "SHOPMAN_STAGING_AUTOPILOT", False):
        return False
    if is_production():
        environment = environment_name()
        logger.error(
            "staging_autopilot: recusado em ambiente %s — pedidos de cliente real não "
            "avançam sozinhos.",
            environment,
        )
        return False
    return True


def covers_channel(channel_ref: str) -> bool:
    """True quando o canal está no escopo do piloto.

    Lista vazia (default) = todos os canais. Preencher deixa um canal na mão do
    operador de verdade — útil quando alguém está testando o PDV/KDS no staging
    e não quer o pedido fugindo por baixo.
    """
    allowed = getattr(settings, "SHOPMAN_STAGING_AUTOPILOT_CHANNELS", []) or []
    if not allowed:
        return True
    return (channel_ref or "") in allowed


def delay_seconds() -> int:
    """Espera entre um passo e o outro (piso de 1s: o zero viraria loop cego)."""
    return max(1, int(getattr(settings, "SHOPMAN_STAGING_AUTOPILOT_DELAY_SECONDS", 30)))


def schedule(order, *, deferrals: int = 0):
    """Agenda o próximo passo do piloto para este pedido.

    Idempotente por (pedido, status): o ``dedupe_key`` carrega o status atual,
    então dois eventos para o mesmo estado geram uma directive só, e o próximo
    status ganha a sua.

    Retorna a Directive criada, ou None quando não havia o que agendar.
    """
    if not is_enabled():
        return None
    if not covers_channel(getattr(order, "channel_ref", "")):
        return None
    status = getattr(order, "status", "")
    if status not in AUTOPILOT_STATUSES:
        return None
    if deferrals >= MAX_DEFERRALS:
        logger.warning(
            "staging_autopilot: desistindo do pedido %s em %s após %d tentativas",
            order.ref, status, deferrals,
        )
        return None

    return create_deduped(
        STAGING_AUTOPILOT,
        payload={
            "order_ref": order.ref,
            "status": status,
            "deferrals": deferrals,
        },
        dedupe_key=f"staging.autopilot:{order.ref}:{status}",
        available_at=timezone.now() + timedelta(seconds=delay_seconds()),
    )


def step(order, *, recorded_status: str) -> str:
    """Dá UM passo de operador no pedido. Retorna o novo status, ou "".

    "" significa "não avancei": ou o pedido saiu de ``recorded_status`` por
    conta própria (operador de verdade agiu — o piloto sai de fininho), ou um
    guarda bloqueou (o caller reagenda).

    Levanta ValueError com a frase do bloqueio quando o guarda do gestor
    recusa — é o mesmo erro que o operador humano leria na tela.
    """
    from shopman.shop.services import operator_orders

    if order.status != recorded_status:
        # Alguém encostou no pedido entre o agendamento e agora. O evento dessa
        # mudança já agendou o passo do novo status; este morre em silêncio.
        return ""

    if order.status == Order.Status.NEW:
        operator_orders.confirm_order(order, actor="staging.autopilot")
        return Order.Status.ACCEPTED

    if order.status == Order.Status.PREPARING:
        # Em preparo quem avança é a COZINHA, não o botão do gestor. Bumpar os
        # tickets deixa o KDS do staging limpo (o "avançar" do gestor leva o
        # pedido a pronto e abandona os tickets abertos no board para sempre).
        bumped = _bump_open_tickets(order)
        if bumped:
            order.refresh_from_db()
            return order.status if order.status != recorded_status else ""

    return operator_orders.advance_order(order, actor="staging.autopilot")


def _bump_open_tickets(order) -> int:
    """Finaliza os tickets de KDS abertos do pedido, como a cozinha faria.

    ``kds.complete_ticket`` leva o pedido a "pronto" sozinho quando o último
    ticket cai (``on_all_tickets_done``). Retorna quantos tickets foram
    bumpados — 0 quando o pedido não tem KDS (canal sem roteamento), e aí o
    caller volta para o caminho do gestor.
    """
    from shopman.shop.adapters import kds as kds_adapter
    from shopman.shop.services import kds

    open_tickets = list(
        kds_adapter.get_tickets(order).filter(status__in=sorted(kds.OPEN_TICKET_STATUSES))
    )
    bumped = 0
    for ticket in open_tickets:
        if kds.complete_ticket(ticket, actor="staging.autopilot"):
            bumped += 1
    return bumped


def on_order_changed(sender, order, event_type, actor, **kwargs) -> None:
    """Receiver de ``order_changed``: agenda o próximo passo depois do COMMIT.

    Ligado em ``ShopmanConfig.ready()`` só quando o piloto está habilitado. O
    ``on_commit`` importa: agendar dentro da transação criaria directive para um
    pedido que pode não existir se o commit falhar.
    """
    if event_type not in ("created", "status_changed"):
        return
    if not is_enabled():
        return

    from django.db import transaction

    transaction.on_commit(lambda: _schedule_quietly(order))


def _schedule_quietly(order) -> None:
    """Agenda sem nunca derrubar quem transicionou o pedido.

    O piloto é conveniência de staging: uma falha aqui não pode abortar a
    transição de status que acabou de acontecer.
    """
    try:
        schedule(order)
    except Exception:
        logger.warning("staging_autopilot: agendamento falhou order=%s", order.ref, exc_info=True)


__all__ = [
    "AUTOPILOT_STATUSES",
    "MAX_DEFERRALS",
    "covers_channel",
    "delay_seconds",
    "is_enabled",
    "on_order_changed",
    "schedule",
    "step",
]
