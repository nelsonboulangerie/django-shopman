"""O acionador: do alerta ao remédio do domínio, com teto, registro e conferência.

Um alerta de tipo com remédio (``remedies.BY_ALERT_TYPE``) ganha, depois do commit,
uma Directive ``incident.act`` (uma viva por alerta). Ela roda no worker de
diretivas, em segundos, e é uma pequena máquina de estados no próprio payload:

- **planejar**: o remédio olha o alerta e diz ``act``, ``wait``, ``no`` ou ``judge``;
- **esperar**: o domínio ainda está tentando; a directive volta na hora certa,
  sem gastar tentativa;
- **acionar**: o gesto do domínio, com o ator ``watchman:incidentes``;
- **conferir**: volta depois de ``verify_after`` e pergunta ao domínio, por fato,
  se resolveu; desiste em ``verify_within`` ("não resolveu").

Toda decisão vira uma linha de ``IncidentAction``: o placar. O modo da loja
(``Shop.incident_remedies_mode``) decide entre acionar, só registrar (sombra) e
nada. A repescagem (``act_on_incidents``, no ``maintenance_worker``) cobre o alerta
cuja directive se perdeu.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from shopman.backstage.incidents import remedies
from shopman.shop.directives import INCIDENT_ACT

logger = logging.getLogger(__name__)

#: Gestos acionados que contam no teto de tentativas.
_ACTED = ("ran", "resolved", "not_resolved")
#: Alerta mais velho que isto não é mais "agora": fica com gente.
MAX_WAIT = timedelta(hours=24)


def current_mode() -> str:
    from shopman.shop.models import Shop

    shop = Shop.load()
    return str(getattr(shop, "incident_remedies_mode", "") or "off") if shop is not None else "off"


def dedupe_key(alert_id: int) -> str:
    return f"incident.act:{alert_id}"


def enqueue(alert_id: int, *, action_id: int | None = None):
    from shopman.shop.directives import create_deduped

    payload = {"alert_id": int(alert_id)}
    if action_id:
        payload["action_id"] = int(action_id)
    return create_deduped(INCIDENT_ACT, payload=payload, dedupe_key=dedupe_key(alert_id))


def on_alert_saved(sender, instance, created, **kwargs) -> None:
    """Alerta novo com remédio: a directive sai depois do commit."""

    if not created or instance.type not in remedies.BY_ALERT_TYPE:
        return
    alert_id = instance.pk
    transaction.on_commit(lambda: _enqueue_quietly(alert_id))


def _enqueue_quietly(alert_id: int) -> None:
    try:
        enqueue(alert_id)
    except Exception:  # noqa: BLE001 - o alerta já existe; a repescagem cobre
        logger.exception("incident.act_enqueue_failed alert=%s", alert_id)


def record(alert, remedy, outcome: str, detail: str = "", *, once: bool = False, mode: str = "on", **extra):
    from shopman.backstage.models import IncidentAction

    detail = str(detail or "")[:300]
    if once and IncidentAction.objects.filter(alert_id=alert.pk, outcome=outcome, detail=detail).exists():
        return None
    return IncidentAction.objects.create(
        alert_id=alert.pk,
        alert_type=alert.type,
        target=(alert.order_ref or alert.type)[:80],
        remedy=remedy.key if remedy else "",
        outcome=outcome,
        detail=detail,
        mode=mode,
        **extra,
    )


def acted_recently(remedy, target: str, *, now) -> int:
    from shopman.backstage.models import IncidentAction

    return IncidentAction.objects.filter(
        remedy=remedy.key, target=target, outcome__in=_ACTED, created_at__gte=now - timedelta(hours=24)
    ).count()


class Deferred(Exception):
    def __init__(self, until, payload=None):
        super().__init__("deferred")
        self.until = until
        self.payload = payload


def step(alert_id: int, *, action_id: int | None = None, judge=None):
    """Um passo da máquina. Devolve ``Deferred`` (para reagendar) ou ``None`` (fim).

    ``judge(alert, remedy, verdict)`` é o classificador da W3; sem ele, o caso que a
    regra não decide fica com gente.
    """

    from shopman.backstage.models import IncidentAction, OperatorAlert

    now = timezone.now()
    alert = OperatorAlert.objects.filter(pk=alert_id).first()
    remedy = remedies.BY_ALERT_TYPE.get(alert.type) if alert is not None else None
    if alert is None or remedy is None:
        return None

    if action_id:
        action = IncidentAction.objects.filter(pk=action_id).first()
        if action is None or action.verified_at is not None:
            return None
        result = remedy.confirm(action)
        if result is None and now < action.created_at + remedy.verify_within:
            return Deferred(now + remedy.verify_after, {"action_id": action.pk})
        action.outcome = action.RESOLVED if result else action.NOT_RESOLVED
        action.verified_at = now
        action.save(update_fields=["outcome", "verified_at"])
        logger.info("incident.verified alert=%s remedy=%s outcome=%s", alert.pk, remedy.key, action.outcome)
        return None

    mode = current_mode()
    if mode == "off":
        return None
    target = alert.order_ref or alert.type
    if alert.resolved_at is not None:
        return None
    if acted_recently(remedy, target, now=now) >= remedy.max_attempts:
        record(alert, remedy, IncidentAction.CEILING, f"{remedy.max_attempts} tentativas em 24 h", once=True, mode=mode)
        return None

    verdict = remedy.check(alert)
    decided_by, confidence, cost = "regra", None, 0
    if verdict.kind == "judge" and judge is not None:
        verdict, decided_by, confidence, cost = judge(alert, remedy, verdict)

    if verdict.kind == "wait":
        if now - alert.created_at > MAX_WAIT:
            record(alert, remedy, IncidentAction.SKIPPED, "esperou mais de 24 h", once=True, mode=mode)
            return None
        return Deferred(verdict.until or now + remedy.verify_after)
    if verdict.kind in {"no", "judge"}:
        reason = verdict.reason if verdict.kind == "no" else f"{verdict.reason} (pede leitura)"
        record(alert, remedy, IncidentAction.SKIPPED, reason, once=True, mode=mode,
               decided_by=decided_by, confidence=confidence, cost_usd_micros=cost)
        return None

    if mode == "shadow":
        record(alert, remedy, IncidentAction.WOULD_RUN, verdict.reason, once=True, mode=mode,
               decided_by=decided_by, confidence=confidence, cost_usd_micros=cost)
        return None
    try:
        detail = remedy.apply(alert)
    except remedies.RemedyRefused as exc:
        record(alert, remedy, IncidentAction.REFUSED, str(exc), mode=mode,
               decided_by=decided_by, confidence=confidence, cost_usd_micros=cost)
        return None
    action = record(alert, remedy, IncidentAction.RAN, f"{verdict.reason}: {detail}", mode=mode,
                    decided_by=decided_by, confidence=confidence, cost_usd_micros=cost)
    logger.info("incident.acted alert=%s remedy=%s target=%s", alert.pk, remedy.key, target)
    return Deferred(now + remedy.verify_after, {"action_id": action.pk})


class IncidentActHandler:
    """Directive ``incident.act``: um passo por execução, reagendando-se sem gastar tentativa."""

    topic = INCIDENT_ACT

    def handle(self, *, message, ctx: dict) -> None:
        del ctx
        payload = dict(message.payload or {})
        alert_id = payload.get("alert_id")
        if not alert_id:
            from shopman.orderman.exceptions import DirectiveTerminalError

            raise DirectiveTerminalError("missing alert_id")
        outcome = step(int(alert_id), action_id=payload.get("action_id"), judge=_judge())
        if isinstance(outcome, Deferred):
            message.payload = {**payload, **(outcome.payload or {})}
            message.status = "queued"
            message.attempts = max(0, int(message.attempts or 0) - 1)
            message.available_at = outcome.until
            message.save(update_fields=["payload", "status", "attempts", "available_at", "updated_at"])


def _judge():
    """O classificador (W3), quando houver. Sem ele, ``judge`` fica com gente."""

    return None


def sweep(*, now=None) -> dict:
    """Repescagem: alerta com remédio sem directive viva, e conferência vencida."""

    from shopman.orderman.models import Directive

    from shopman.backstage.models import IncidentAction, OperatorAlert

    now = now or timezone.now()
    counts = {"enqueued": 0, "expired": 0}
    if current_mode() == "off":
        return counts
    live = set(
        Directive.objects.filter(topic=INCIDENT_ACT, status__in=("queued", "running")).values_list(
            "dedupe_key", flat=True
        )
    )
    alerts = OperatorAlert.objects.filter(
        type__in=list(remedies.BY_ALERT_TYPE), resolved_at__isnull=True, created_at__gte=now - MAX_WAIT
    ).values_list("pk", flat=True)
    for alert_id in alerts:
        if dedupe_key(alert_id) in live:
            continue
        if IncidentAction.objects.filter(alert_id=alert_id).exclude(outcome=IncidentAction.RAN).exists():
            continue
        if enqueue(alert_id) is not None:
            counts["enqueued"] += 1
    pending = IncidentAction.objects.filter(outcome=IncidentAction.RAN, verified_at__isnull=True)
    for action in pending:
        remedy = remedies.BY_KEY.get(action.remedy)
        if remedy is None or now < action.created_at + remedy.verify_within:
            continue
        if action.alert_id and dedupe_key(action.alert_id) in live:
            continue
        result = remedy.confirm(action)
        action.outcome = IncidentAction.RESOLVED if result else IncidentAction.NOT_RESOLVED
        action.verified_at = now
        action.save(update_fields=["outcome", "verified_at"])
        counts["expired"] += 1
    return counts
