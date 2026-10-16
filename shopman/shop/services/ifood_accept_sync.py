"""O aceite do pedido chegou ao iFood? (P1-3)

Aceitar no Gestor muda o pedido aqui na hora; o ``confirm`` ao iFood sai depois,
numa Directive ``ifood.status_callback`` com retry (``handlers/ifood_status``).
Quando essa chamada falha, a cozinha já está trabalhando e o iFood continua
achando que ninguém aceitou: no fim do prazo dele (8 min desde o ``createdAt``,
``data.ifood.confirm_by``) ele cancela sozinho. Até aqui isso só aparecia no
alerta genérico de tarefas, e o card perdia o prazo assim que saía de ``new``.

O estado NÃO é gravado no pedido: ele é derivado das duas evidências que já
existem, e por isso não fica fora de sincronia com elas.

- ``data.ifood.remote_confirmed`` (ou ``remote_dispatched``/``remote_concluded``):
  o iFood disse que confirmou. Estado ``confirmed``.
- A Directive do aceite (``dedupe_key`` ``ifood.status_callback:<ref>:accepted``),
  a mais recente: ``done`` é ``sent`` (o iFood recebeu o ``confirm``); com erro
  gravado, em fila de nova tentativa ou ``failed``, é ``failed``; em fila sem
  erro ainda, ``pending``.

``failed`` é o único estado que pede gente: o card mostra "O iFood ainda não
recebeu o aceite" com o prazo dele contando e o **Tentar de novo**
(:func:`retry`), e o Gestor recebe o alerta ``ifood_accept_not_delivered`` na
primeira falha. O alerta fecha quando o ``confirm`` passa, quando o iFood
confirma, ou quando o pedido acaba.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from shopman.shop.directives import IFOOD_STATUS_CALLBACK

logger = logging.getLogger(__name__)

ALERT_TYPE = "ifood_accept_not_delivered"
ACCEPT_STATUS = "accepted"

#: Eventos do pedido que mudam o que o card mostra (o Gestor relê pelo SSE).
EVENT_FAILED = "ifood_accept_failed"
EVENT_SENT = "ifood_accept_sent"
EVENT_RETRIED = "ifood_accept_retried"
EVENT_CONFIRMED = "ifood_accept_confirmed"
EVENTS = (EVENT_FAILED, EVENT_SENT, EVENT_RETRIED, EVENT_CONFIRMED)

_REMOTE_MARKERS = ("remote_confirmed", "remote_dispatched", "remote_concluded")


@dataclass(frozen=True)
class AcceptSync:
    """O estado do aceite no iFood. ``state`` vazio: não se aplica a este pedido."""

    state: str = ""
    directive_id: int | None = None
    directive_status: str = ""
    attempts: int = 0

    @property
    def failed(self) -> bool:
        return self.state == "failed"

    @property
    def revision(self) -> str:
        """Base do Tentar de novo: muda a cada tentativa, para o gesto não repetir uma velha."""
        return f"{self.state}:{self.directive_id or 0}:{self.directive_status}:{self.attempts}"


def dedupe_key(order_ref: str) -> str:
    return f"{IFOOD_STATUS_CALLBACK}:{order_ref}:{ACCEPT_STATUS}"


def _facts(order) -> dict:
    return (order.data or {}).get("ifood") or {}


def applies(order) -> bool:
    """Pedido do iFood já aceito aqui, vivo, real (não simulado) e não cancelado lá."""
    from shopman.orderman.models import Order

    from shopman.shop.services import ifood_ingest

    if getattr(order, "channel_ref", "") != ifood_ingest.IFOOD_CHANNEL_REF:
        return False
    if order.status == Order.Status.NEW or order.status in Order.TERMINAL_STATUSES:
        return False
    if (order.data or {}).get("ifood_cancelled"):
        return False
    external = str(order.external_ref or (order.data or {}).get("external_order_code") or "")
    return bool(external) and not external.upper().startswith("IFOOD-SIM-")


def remote_confirmed(order) -> bool:
    facts = _facts(order)
    return any(facts.get(marker) for marker in _REMOTE_MARKERS)


def latest_directives(refs) -> dict:
    """{order_ref: Directive mais recente do aceite}, numa consulta só."""
    from shopman.orderman.models import Directive

    refs = [ref for ref in refs if ref]
    if not refs:
        return {}
    keys = {dedupe_key(ref): ref for ref in refs}
    out: dict = {}
    for directive in Directive.objects.filter(topic=IFOOD_STATUS_CALLBACK, dedupe_key__in=list(keys)).order_by("pk"):
        out[keys[directive.dedupe_key]] = directive
    return out


def _state_from(directive) -> str:
    if directive is None:
        return ""
    if directive.status == "done":
        return "sent"
    if directive.status == "failed":
        return "failed"
    # Em fila ou rodando: com erro gravado é nova tentativa de quem já falhou.
    return "failed" if directive.attempts and directive.last_error else "pending"


def state_for(order, *, batch: dict | None = None) -> AcceptSync:
    """O estado do aceite deste pedido.

    ``batch``: o lote de :func:`latest_directives` da tela inteira (sem N+1); sem
    ele, consulta só este pedido, e só quando o pedido é do iFood e já aceito.
    """
    if not applies(order):
        return AcceptSync()
    if remote_confirmed(order):
        return AcceptSync(state="confirmed")
    directive = (batch if batch is not None else latest_directives([order.ref])).get(order.ref)
    state = _state_from(directive)
    if not state:
        return AcceptSync()
    return AcceptSync(
        state=state,
        directive_id=directive.pk,
        directive_status=directive.status,
        attempts=int(directive.attempts or 0),
    )


def deadline(order):
    """Quando o iFood cancela sozinho (``data.ifood.confirm_by``), ou ``None``."""
    raw = str(_facts(order).get("confirm_by") or "").strip()
    if not raw:
        return None
    try:
        value = parse_datetime(raw)
    except (TypeError, ValueError):
        return None
    return value if value is not None and timezone.is_aware(value) else None


def notice_title() -> str:
    return "O iFood ainda não recebeu o aceite"


def notice_text(order) -> str:
    """A frase inteira, para o alerta e para o detalhe: o fato, o prazo e o gesto."""
    when = deadline(order)
    if when is not None and when > timezone.now():
        clock = timezone.localtime(when).strftime("%H:%M")
        deadline_line = f" Se não receber até {clock}, o iFood cancela o pedido sozinho."
    elif when is not None:
        deadline_line = " O prazo do iFood para o aceite já passou: confira no iFood se o pedido segue ativo."
    else:
        deadline_line = " Sem o aceite, o iFood cancela o pedido sozinho."
    return (
        f"O iFood ainda não recebeu o aceite do pedido {order.ref}, e a cozinha já pode estar trabalhando nele."
        f"{deadline_line} Toque em Tentar de novo no pedido."
    )


# ── Os três fatos que mexem no estado ─────────────────────────────────────────


def on_attempt_failed(order, directive) -> None:
    """Uma tentativa de ``confirm`` falhou. Avisa na primeira, uma vez por Directive.

    A Directive ainda está ``running`` aqui (o worker grava a falha depois que o
    handler levanta): ``attempts`` já conta esta tentativa.
    """
    from shopman.shop.services.observability import create_operator_alert

    if not applies(order) or remote_confirmed(order):
        return
    if int(getattr(directive, "attempts", 1) or 1) > 1:
        return  # o aviso já saiu na primeira; as novas tentativas são do worker
    create_operator_alert(
        type=ALERT_TYPE,
        severity="error",
        message=notice_text(order),
        order_ref=order.ref,
        dedupe_key=f"{ALERT_TYPE}:{order.ref}",
        respond_by=deadline(order),
    )
    _emit(order, EVENT_FAILED, directive)


def _emit(order, event_type: str, directive=None) -> None:
    """Rastro no histórico do pedido; o SSE do Gestor relê o card por ele. Nunca levanta."""
    try:
        order.emit_event(event_type=event_type, actor="system:ifood", payload={"directive_id": getattr(directive, "pk", None)})
    except Exception:
        logger.exception("ifood_accept_sync: could not record %s for order %s", event_type, getattr(order, "ref", "?"))


def _had_trouble(order) -> bool:
    """Só vale contar que deu certo quando antes deu errado (sem ruído no histórico)."""
    return order.events.filter(type__in=(EVENT_FAILED, EVENT_RETRIED)).exists()


def on_sent(order, directive) -> None:
    """O iFood recebeu o ``confirm``. Fecha o aviso, se havia um."""
    from shopman.shop.handlers.alert_resolution import resolve_on_commit

    resolve_on_commit(order.ref, (ALERT_TYPE,), actor="ifood_accept_sent")
    if _had_trouble(order) and not order.events.filter(type=EVENT_SENT, payload__directive_id=getattr(directive, "pk", None)).exists():
        _emit(order, EVENT_SENT, directive)


def on_remote_confirmed(order) -> None:
    """O iFood disse que o pedido está confirmado (CFM): nada mais a avisar."""
    from shopman.shop.handlers.alert_resolution import resolve_on_commit

    resolve_on_commit(order.ref, (ALERT_TYPE,), actor="ifood_remote_confirmed")
    if _had_trouble(order) and not order.events.filter(type=EVENT_CONFIRMED).exists():
        _emit(order, EVENT_CONFIRMED)


class AcceptRetryRefused(Exception):
    """O Tentar de novo não cabe agora; a mensagem é para o operador."""


class AcceptRetryStale(AcceptRetryRefused):
    """A leitura que pediu o Tentar de novo ficou velha (outra tentativa já correu)."""


def retry(order, *, actor: str, expected_revision: str | None = None):
    """Tentar de novo: põe o ``confirm`` deste pedido para sair agora.

    Reabre a Directive do aceite em vez de criar outra: a mesma linha guarda o
    histórico, e a constraint de uma tarefa viva por ``dedupe_key`` continua
    valendo. Volta com ``attempts`` zerado para ter a janela de retry inteira e
    disponível já; o worker (``process_directives --watch``, 1 s) a pega.

    Idempotente pela revisão: dois toques na mesma leitura reabrem uma vez só,
    e um toque sobre um estado que mudou é recusado com o motivo.
    """
    from django.db import transaction
    from shopman.orderman.models import Directive, Order

    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        directives = list(
            Directive.objects.select_for_update()
            .filter(topic=IFOOD_STATUS_CALLBACK, dedupe_key=dedupe_key(locked.ref))
            .order_by("pk")
        )
        directive = directives[-1] if directives else None
        sync = state_for(locked, batch={locked.ref: directive} if directive else {})
        if expected_revision is not None and sync.revision != expected_revision:
            raise AcceptRetryStale("O envio do aceite mudou desde a leitura. Confira o pedido antes de tentar de novo.")
        if sync.state == "confirmed" or sync.state == "sent":
            raise AcceptRetryRefused("O iFood já recebeu o aceite deste pedido.")
        if not sync.failed or directive is None:
            raise AcceptRetryRefused("Não há envio de aceite pendente neste pedido.")
        if directive.status == "running":
            raise AcceptRetryRefused("O aceite está sendo enviado agora. Confira em alguns segundos.")
        previous_error = directive.last_error
        directive.status = "queued"
        directive.attempts = 0
        directive.error_code = ""
        directive.last_error = ""
        directive.available_at = timezone.now()
        directive.save(update_fields=["status", "attempts", "error_code", "last_error", "available_at", "updated_at"])
        locked.emit_event(
            event_type=EVENT_RETRIED,
            actor=actor,
            payload={"directive_id": directive.pk, "previous_error": previous_error[:200]},
        )
    logger.info("ifood_accept_sync: retry queued for order %s (directive %s) by %s", locked.ref, directive.pk, actor)
    return directive


__all__ = [
    "ALERT_TYPE",
    "AcceptRetryRefused",
    "AcceptRetryStale",
    "AcceptSync",
    "applies",
    "deadline",
    "latest_directives",
    "notice_text",
    "notice_title",
    "on_attempt_failed",
    "on_remote_confirmed",
    "on_sent",
    "retry",
    "state_for",
]
