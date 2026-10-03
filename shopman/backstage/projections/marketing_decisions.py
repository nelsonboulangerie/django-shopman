"""A fila de decisões do Marketing: a casa do app, ordenada por prazo.

Decisão do dono (03/10/2026, SUITE-UX §9 "Decisões do Marketing"): o trabalho
central do app é *o que espera o meu sim*, e antes ele morava em cinco portas
(Hoje cortado em 4, sino, push, a volta do disparo e a linha do histórico) e em
nenhuma tela. Esta leitura junta, numa lista só, as decisões que de fato existem
hoje no sistema, cada uma com o lugar exato onde ela já é tomada:

- **revisar um anúncio** (`pending_review` dentro do prazo): o "sim / não /
  quando" da tela do anúncio;
- **repetir falhas seguras** (`failed_retryable`): só volta à fila por gesto do
  operador, nunca sozinha (o worker não repete);
- **consultar de novo um resultado incerto** (`unknown` cuja tentativa já teve
  a consulta automática e continuou sem resposta).

O resultado incerto que o sistema ainda vai consultar, ou já consultou sozinho,
NÃO é decisão: vai em ``automatic_checks``, que a tela mostra como "o sistema
consultou sem reenviar · automático".

O alcance sai na grandeza certa, separado: **postagens** (1 por plataforma de
publicação) e **pessoas** (mensagem direta). Somar as duas é o erro que o
contrato do Marketing proíbe.

Como o resto das leituras do Marketing, esta não carrega rótulo final nem copy:
códigos, contagens, datas e nomes de cadastro (campanha, produto). A frase em
pt-BR mora no Nuxt (`surfaces/marketing-nuxt/app/presentation/decisions.ts`).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone

from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    Campaign,
    DeliveryAttempt,
    DeliveryReconciliation,
    DeliveryTarget,
)
from shopman.shop.services.marketing_capabilities import platform_kind
from shopman.shop.services.marketing_delivery_recovery import (
    SYSTEM_RECONCILIATION_ACTOR,
)
from shopman.shop.services.marketing_time import configured_timezone_name

# A janela do que já assentou e ainda vale mostrar (a mesma do painel v2).
RECENT_WINDOW = timedelta(hours=24)

DIRECT_MESSAGE_KIND = "direct_message"
PUBLICATION_KIND = "publication"

DecisionKind = Literal["review", "retry_failed", "reconcile_unknown"]
# `checking`: na fila da consulta (pedida pelo sistema ou a pedir na próxima
# passada). Os outros quatro são o que a consulta automática encontrou.
AutomaticCheckState = Literal[
    "checking",
    "confirmed",
    "accepted",
    "failed",
    "still_unknown",
]

_SAFE_CODE = re.compile(r"^[a-z0-9_]{1,64}$")
_DOMAIN_CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")


@dataclass(frozen=True, slots=True)
class DecisionReachProjection:
    posts: int
    people: int


@dataclass(frozen=True, slots=True)
class DecisionFailureProjection:
    platform_ref: str
    delivery_kind: str
    count: int
    reason_code: str


@dataclass(frozen=True, slots=True)
class DecisionItemProjection:
    ref: str
    kind: DecisionKind
    announcement_id: int
    announcement_version: int
    campaign_name: str
    trigger: str
    product_name: str
    platform_refs: tuple[str, ...]
    reach: DecisionReachProjection
    deadline_at: datetime | None
    scheduled_for: datetime | None
    created_at: datetime
    failures: tuple[DecisionFailureProjection, ...]
    href: str


@dataclass(frozen=True, slots=True)
class AutomaticCheckProjection:
    ref: str
    announcement_id: int
    campaign_name: str
    platform_ref: str
    delivery_kind: str
    state: AutomaticCheckState
    target_count: int
    checked_at: datetime | None
    href: str


@dataclass(frozen=True, slots=True)
class ScheduledItemProjection:
    ref: str
    announcement_id: int
    campaign_name: str
    trigger: str
    product_name: str
    platform_refs: tuple[str, ...]
    reach: DecisionReachProjection
    scheduled_for: datetime
    href: str


@dataclass(frozen=True, slots=True)
class MarketingDecisionQueueProjection:
    generated_at: datetime
    shop_timezone: str
    items: tuple[DecisionItemProjection, ...]
    automatic_checks: tuple[AutomaticCheckProjection, ...]
    scheduled: tuple[ScheduledItemProjection, ...]
    scheduled_today_count: int
    active_campaign_count: int


def build_decision_queue(*, now: datetime | None = None) -> MarketingDecisionQueueProjection:
    """Montar a fila inteira, sem corte: a casa nunca esconde uma decisão."""

    clock = now or timezone.now()
    if timezone.is_naive(clock):
        raise ValueError("A fila de decisões exige um relógio com fuso.")
    zone = ZoneInfo(configured_timezone_name())

    pending = [
        announcement
        for announcement in Announcement.objects.filter(
            status=AnnouncementStatus.PENDING_REVIEW,
        ).select_related("rule")
        if not announcement.is_expired(now=clock)
    ]
    scheduled = list(
        Announcement.objects.filter(
            status=AnnouncementStatus.APPROVED,
            publish_at__gt=clock,
        )
        .select_related("rule")
        .order_by("publish_at", "pk")
    )
    open_targets = list(
        DeliveryTarget.objects.filter(
            state__in=(
                DeliveryTarget.State.FAILED_RETRYABLE,
                DeliveryTarget.State.UNKNOWN,
            ),
        )
        .select_related("announcement", "announcement__rule")
        .order_by("announcement_id", "platform", "pk")
    )
    recent_automatic = list(
        DeliveryReconciliation.objects.filter(
            command__actor__isnull=True,
            command__actor_ref=SYSTEM_RECONCILIATION_ACTOR,
        )
        .filter(
            Q(
                state__in=(
                    DeliveryReconciliation.State.PENDING,
                    DeliveryReconciliation.State.CLAIMED,
                )
            )
            | Q(completed_at__gte=clock - RECENT_WINDOW)
        )
        .select_related("target", "target__announcement", "target__announcement__rule")
        .order_by("target__announcement_id", "target__platform", "pk")
    )
    product_names = _product_names(
        (*pending, *scheduled, *(target.announcement for target in open_targets))
    )

    items: list[DecisionItemProjection] = [
        _review_item(announcement, product_names=product_names, zone=zone)
        for announcement in pending
    ]
    unknown_needs_operator, unknown_waiting_lookup = _split_unknown(
        [target for target in open_targets if target.state == DeliveryTarget.State.UNKNOWN]
    )
    items.extend(
        _failure_items(
            [
                target
                for target in open_targets
                if target.state == DeliveryTarget.State.FAILED_RETRYABLE
            ],
            kind="retry_failed",
            product_names=product_names,
            zone=zone,
        )
    )
    items.extend(
        _failure_items(
            unknown_needs_operator,
            kind="reconcile_unknown",
            product_names=product_names,
            zone=zone,
        )
    )
    items.sort(key=_urgency_key)

    local_now = timezone.localtime(clock, zone)
    end_of_day = datetime.combine(local_now.date() + timedelta(days=1), time.min, tzinfo=zone)
    return MarketingDecisionQueueProjection(
        generated_at=local_now,
        shop_timezone=str(zone),
        items=tuple(items),
        automatic_checks=_automatic_checks(
            recent_automatic,
            waiting=unknown_waiting_lookup,
            zone=zone,
        ),
        scheduled=tuple(
            _scheduled_item(announcement, product_names=product_names, zone=zone)
            for announcement in scheduled
        ),
        scheduled_today_count=sum(
            1 for announcement in scheduled if announcement.publish_at < end_of_day
        ),
        active_campaign_count=Campaign.objects.filter(is_active=True).count(),
    )


def _review_item(
    announcement: Announcement,
    *,
    product_names: dict[str, str],
    zone: ZoneInfo,
) -> DecisionItemProjection:
    platform_refs = _platform_refs(announcement)
    return DecisionItemProjection(
        ref=f"review:announcement:{announcement.pk}",
        kind="review",
        announcement_id=announcement.pk,
        announcement_version=announcement.version,
        campaign_name=_campaign_name(announcement),
        trigger=_trigger(announcement),
        product_name=product_names.get(_sku(announcement), ""),
        platform_refs=platform_refs,
        reach=_planned_reach(announcement, platform_refs),
        deadline_at=_local(announcement.expires_at, zone),
        scheduled_for=_local(announcement.publish_at, zone),
        created_at=_local(announcement.created_at, zone),
        failures=(),
        href=f"/announcements/{announcement.pk}#review",
    )


def _scheduled_item(
    announcement: Announcement,
    *,
    product_names: dict[str, str],
    zone: ZoneInfo,
) -> ScheduledItemProjection:
    platform_refs = _platform_refs(announcement)
    return ScheduledItemProjection(
        ref=f"scheduled:announcement:{announcement.pk}",
        announcement_id=announcement.pk,
        campaign_name=_campaign_name(announcement),
        trigger=_trigger(announcement),
        product_name=product_names.get(_sku(announcement), ""),
        platform_refs=platform_refs,
        reach=_planned_reach(announcement, platform_refs),
        scheduled_for=timezone.localtime(announcement.publish_at, zone),
        href=f"/announcements/{announcement.pk}",
    )


def _failure_items(
    targets: list[DeliveryTarget],
    *,
    kind: DecisionKind,
    product_names: dict[str, str],
    zone: ZoneInfo,
) -> list[DecisionItemProjection]:
    by_announcement: dict[int, list[DeliveryTarget]] = defaultdict(list)
    for target in targets:
        by_announcement[target.announcement_id].append(target)
    items: list[DecisionItemProjection] = []
    for announcement_id, rows in by_announcement.items():
        announcement = rows[0].announcement
        failures = _failures(rows)
        items.append(
            DecisionItemProjection(
                ref=f"{kind}:announcement:{announcement_id}",
                kind=kind,
                announcement_id=announcement_id,
                announcement_version=announcement.version,
                campaign_name=_campaign_name(announcement),
                trigger=_trigger(announcement),
                product_name=product_names.get(_sku(announcement), ""),
                platform_refs=tuple(failure.platform_ref for failure in failures),
                reach=DecisionReachProjection(
                    posts=sum(
                        failure.count
                        for failure in failures
                        if failure.delivery_kind == PUBLICATION_KIND
                    ),
                    people=sum(
                        failure.count
                        for failure in failures
                        if failure.delivery_kind == DIRECT_MESSAGE_KIND
                    ),
                ),
                # Repetir só vale enquanto o anúncio vale: depois do prazo, o
                # worker encerra o destino como vencido em vez de enviar.
                deadline_at=(
                    _local(announcement.expires_at, zone) if kind == "retry_failed" else None
                ),
                scheduled_for=None,
                created_at=_local(announcement.created_at, zone),
                failures=failures,
                href=f"/announcements/{announcement_id}#result",
            )
        )
    return items


def _failures(rows: list[DeliveryTarget]) -> tuple[DecisionFailureProjection, ...]:
    by_platform: dict[tuple[str, str], list[DeliveryTarget]] = defaultdict(list)
    for target in rows:
        platform_ref = _domain_code(target.platform) or "unknown"
        by_platform[(platform_ref, _delivery_kind(target))].append(target)
    failures = []
    for (platform_ref, delivery_kind), targets in by_platform.items():
        codes = Counter(
            code
            for code in (str(target.last_error_code or "") for target in targets)
            if _SAFE_CODE.fullmatch(code)
        )
        failures.append(
            DecisionFailureProjection(
                platform_ref=platform_ref,
                delivery_kind=delivery_kind,
                count=len(targets),
                reason_code=codes.most_common(1)[0][0] if codes else "",
            )
        )
    return tuple(failures)


def _split_unknown(
    targets: list[DeliveryTarget],
) -> tuple[list[DeliveryTarget], list[DeliveryTarget]]:
    """Separar o incerto que é decisão do operador do que o sistema vai consultar.

    Decisão: a última tentativa incerta já teve uma consulta (qualquer, do sistema
    ou de uma pessoa) e nenhuma está em andamento. O resto espera a consulta
    automática da próxima passada, ou já está nela.
    """

    if not targets:
        return [], []
    target_ids = [target.pk for target in targets]
    latest_attempt: dict[int, int] = {}
    for target_id, attempt_id in (
        DeliveryAttempt.objects.filter(
            target_id__in=target_ids,
            state=DeliveryAttempt.State.COMPLETED,
            outcome_kind="unknown",
        )
        .order_by("target_id", "-ordinal")
        .values_list("target_id", "pk")
    ):
        latest_attempt.setdefault(target_id, attempt_id)
    active = set(
        DeliveryReconciliation.objects.filter(
            target_id__in=target_ids,
            state__in=(
                DeliveryReconciliation.State.PENDING,
                DeliveryReconciliation.State.CLAIMED,
            ),
        ).values_list("target_id", flat=True)
    )
    looked_up = set(
        DeliveryReconciliation.objects.filter(
            attempt_id__in=list(latest_attempt.values()),
        ).values_list("attempt_id", flat=True)
    )
    needs_operator: list[DeliveryTarget] = []
    waiting: list[DeliveryTarget] = []
    for target in targets:
        if target.pk in active:
            continue  # já aparece pela própria reconciliação, como "consultando"
        attempt_id = latest_attempt.get(target.pk)
        if attempt_id is not None and attempt_id in looked_up:
            needs_operator.append(target)
        else:
            waiting.append(target)
    return needs_operator, waiting


def _automatic_checks(
    reconciliations: list[DeliveryReconciliation],
    *,
    waiting: list[DeliveryTarget],
    zone: ZoneInfo,
) -> tuple[AutomaticCheckProjection, ...]:
    groups: dict[tuple[int, str], dict] = {}

    def group_for(target: DeliveryTarget) -> dict:
        platform_ref = _domain_code(target.platform) or "unknown"
        key = (target.announcement_id, platform_ref)
        if key not in groups:
            groups[key] = {
                "announcement": target.announcement,
                "platform_ref": platform_ref,
                "delivery_kind": _delivery_kind(target),
                "states": Counter(),
                "targets": set(),
                "checked_at": None,
            }
        return groups[key]

    for reconciliation in reconciliations:
        group = group_for(reconciliation.target)
        if reconciliation.target_id in group["targets"]:
            continue
        group["targets"].add(reconciliation.target_id)
        if reconciliation.state != DeliveryReconciliation.State.COMPLETED:
            group["states"]["checking"] += 1
            continue
        group["states"][_check_state(reconciliation.target.state)] += 1
        if reconciliation.completed_at and (
            group["checked_at"] is None or reconciliation.completed_at > group["checked_at"]
        ):
            group["checked_at"] = reconciliation.completed_at
    for target in waiting:
        group = group_for(target)
        if target.pk not in group["targets"]:
            group["targets"].add(target.pk)
            group["states"]["checking"] += 1

    checks = []
    for (announcement_id, platform_ref), group in groups.items():
        states: Counter = group["states"]
        # Enquanto um destino ainda está na consulta, o grupo inteiro está
        # "consultando": a frase não pode prometer um resultado pela metade.
        state = (
            "checking"
            if states["checking"]
            else states.most_common(1)[0][0]
        )
        announcement = group["announcement"]
        checks.append(
            AutomaticCheckProjection(
                ref=f"check:announcement:{announcement_id}:{platform_ref}",
                announcement_id=announcement_id,
                campaign_name=_campaign_name(announcement),
                platform_ref=platform_ref,
                delivery_kind=group["delivery_kind"],
                state=state,
                target_count=len(group["targets"]),
                checked_at=_local(group["checked_at"], zone) if state != "checking" else None,
                href=f"/announcements/{announcement_id}#result",
            )
        )
    checks.sort(key=lambda check: (check.state != "checking", check.ref))
    return tuple(checks)


def _check_state(target_state: str) -> AutomaticCheckState:
    if target_state == DeliveryTarget.State.CONFIRMED:
        return "confirmed"
    if target_state == DeliveryTarget.State.ACCEPTED:
        return "accepted"
    if target_state == DeliveryTarget.State.UNKNOWN:
        return "still_unknown"
    return "failed"


def _planned_reach(
    announcement: Announcement,
    platform_refs: tuple[str, ...],
) -> DecisionReachProjection:
    posts = sum(1 for ref in platform_refs if platform_kind(ref) == PUBLICATION_KIND)
    has_message = any(platform_kind(ref) == DIRECT_MESSAGE_KIND for ref in platform_refs)
    audience = announcement.audience if isinstance(announcement.audience, dict) else {}
    people = _safe_count(audience.get("eligible_count", audience.get("total", 0)))
    return DecisionReachProjection(posts=posts, people=people if has_message else 0)


def _urgency_key(item: DecisionItemProjection) -> tuple:
    # Prazo mais curto primeiro; sem prazo vai para o fim, do mais antigo ao mais novo.
    return (
        item.deadline_at is None,
        item.deadline_at or item.created_at,
        item.created_at,
        item.ref,
    )


def _product_names(announcements) -> dict[str, str]:
    skus = {sku for sku in (_sku(item) for item in announcements) if sku}
    if not skus:
        return {}
    from shopman.offerman.models import Product

    return dict(Product.objects.filter(sku__in=skus).values_list("sku", "name"))


def _sku(announcement: Announcement) -> str:
    context = announcement.trigger_context if isinstance(announcement.trigger_context, dict) else {}
    return str(context.get("sku") or "")


def _campaign_name(announcement: Announcement) -> str:
    return announcement.rule.name if announcement.rule_id else ""


def _trigger(announcement: Announcement) -> str:
    return _domain_code(announcement.rule.trigger) if announcement.rule_id else ""


def _platform_refs(announcement: Announcement) -> tuple[str, ...]:
    return tuple(
        ref
        for ref in (_domain_code(value) for value in (announcement.platforms or ()))
        if ref
    )


def _delivery_kind(target: DeliveryTarget) -> str:
    kind = str(target.delivery_kind or "") or str(platform_kind(target.platform) or "")
    return kind if kind in {DIRECT_MESSAGE_KIND, PUBLICATION_KIND} else ""


def _domain_code(value: object) -> str:
    text = str(value or "").strip()
    return text if _DOMAIN_CODE.fullmatch(text) else ""


def _safe_count(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _local(value: datetime | None, zone: ZoneInfo) -> datetime | None:
    return timezone.localtime(value, zone) if value is not None else None
