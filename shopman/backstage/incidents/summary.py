"""Resumo dos alertas por tipo: o que a ponte do GitHub lê, sem dado de cliente.

Um *episódio* é um trecho contínuo em que havia ao menos um alerta aberto do
tipo. Três episódios na janela de sete dias marcam o tipo como recorrente: o
alerta que volta sempre é defeito, e a causa se corrige no código, não com
remédio automático para sempre.

A mensagem do alerta nunca sai daqui: ela pode citar cliente. Saem o tipo, a
contagem, os horários e as refs de pedido (código, não pessoa).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.utils import timezone

WINDOW_DAYS = 7
RECURRING_EPISODES = 3
MAX_ORDER_REFS = 10
_SEVERITY_RANK = {"warning": 0, "error": 1, "critical": 2}


@dataclass(frozen=True)
class IncidentGroup:
    type: str
    label: str
    owner: str
    audience: str
    severity: str
    open_count: int
    open_since: datetime | None
    last_seen: datetime
    green_since: datetime | None
    episodes: int
    recurring: bool
    home: str
    order_refs: tuple[str, ...] = field(default_factory=tuple)

    @property
    def fingerprint(self) -> str:
        return f"shop:{self.type}"

    def to_dict(self) -> dict:
        def iso(value):
            return value.isoformat() if value else None

        return {
            "fingerprint": self.fingerprint,
            "type": self.type,
            "label": self.label,
            "owner": self.owner,
            "audience": self.audience,
            "severity": self.severity,
            "open_count": self.open_count,
            "open_since": iso(self.open_since),
            "last_seen": iso(self.last_seen),
            "green_since": iso(self.green_since),
            "episodes": self.episodes,
            "recurring": self.recurring,
            "home": self.home,
            "order_refs": list(self.order_refs),
        }


def count_episodes(intervals, *, now: datetime) -> int:
    """Quantos trechos contínuos com alerta aberto. ``intervals`` = (início, fim|None)."""

    episodes = 0
    frontier: datetime | None = None
    for start, end in sorted(intervals, key=lambda pair: pair[0]):
        end = end or now
        if frontier is None or start > frontier:
            episodes += 1
            frontier = end
        elif end > frontier:
            frontier = end
    return episodes


def summarize(*, now: datetime | None = None, window_days: int = WINDOW_DAYS) -> list[IncidentGroup]:
    from django.db.models import Q

    from shopman.backstage.incidents.owners import home_for, owner_for
    from shopman.backstage.models import OperatorAlert

    now = now or timezone.now()
    since = now - timedelta(days=window_days)
    labels = dict(OperatorAlert.TYPE_CHOICES)
    rows = (
        OperatorAlert.objects.filter(Q(created_at__gte=since) | Q(resolved_at__isnull=True))
        .order_by("created_at")
        .values("type", "severity", "audience", "order_ref", "created_at", "resolved_at")
    )
    by_type: dict[str, list[dict]] = {}
    for row in rows:
        by_type.setdefault(row["type"], []).append(row)

    groups = []
    for alert_type, alerts in by_type.items():
        open_alerts = [a for a in alerts if a["resolved_at"] is None]
        pool = open_alerts or alerts
        severity = max((a["severity"] for a in pool), key=lambda s: _SEVERITY_RANK.get(s, 0))
        episodes = count_episodes(
            [(a["created_at"], a["resolved_at"]) for a in alerts if a["created_at"] >= since or a["resolved_at"] is None],
            now=now,
        )
        refs = []
        for a in reversed(open_alerts or alerts):
            ref = (a["order_ref"] or "").strip()
            if ref and ref not in refs:
                refs.append(ref)
        groups.append(
            IncidentGroup(
                type=alert_type,
                label=str(labels.get(alert_type, alert_type)),
                owner=owner_for(alert_type, audience=alerts[-1]["audience"]),
                audience=alerts[-1]["audience"],
                severity=severity,
                open_count=len(open_alerts),
                open_since=min((a["created_at"] for a in open_alerts), default=None),
                last_seen=alerts[-1]["created_at"],
                green_since=None if open_alerts else max(a["resolved_at"] for a in alerts),
                episodes=episodes,
                recurring=episodes >= RECURRING_EPISODES,
                home=home_for(alert_type),
                order_refs=tuple(refs[:MAX_ORDER_REFS]),
            )
        )
    groups.sort(key=lambda g: (-g.open_count, -_SEVERITY_RANK.get(g.severity, 0), g.type))
    return groups
