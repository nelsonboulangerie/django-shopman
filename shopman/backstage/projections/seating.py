"""PDV › Ajustes › Salão: a planta de hoje e o registro do que mudou.

A leitura que a tela Salão do PDV desenha (prévia ``salao-mesas4.html``): as
mesas que existem HOJE (``SeatingSpot`` com ``active_from``/``active_until``),
com forma, posição e lugares; o total que o B.I. usa ("N lugares na capacidade
oficial · M extras de dia cheio"); e o histórico do salão, lido do ``LogEntry``
que ``services/seating.py`` escreve a cada gravação (quem, quando, o quê).

Puro de leitura: quem grava é o serviço.
"""

from __future__ import annotations

import json

from django.utils import formats, timezone

from shopman.backstage.models import SeatingSpot, SpotShape
from shopman.backstage.services import seating as seating_service

HISTORY_LIMIT = 30

_FIELD_LABELS = {
    "label": "nome",
    "short_label": "sigla",
    "area": "área",
    "shape": "forma",
    "seats": "lugares",
    "counts_in_capacity": "capacidade oficial",
    "plan_x": "posição",
    "plan_y": "posição",
    "rotation": "giro",
    "active_until": "saída",
}
_SHAPE_LABELS = dict(SpotShape.choices)


def _date(value) -> str:
    return formats.date_format(value, "d/m/Y") if value else ""


def spot_card(spot: SeatingSpot) -> dict:
    since = seating_service.first_day(spot)
    return {
        "ref": spot.ref,
        "label": spot.label,
        "short_label": spot.short_label,
        "area": spot.area,
        "kind": spot.kind,
        "shape": spot.shape,
        "seats": spot.seats,
        "counts_in_capacity": spot.counts_in_capacity,
        "plan_x": spot.plan_x,
        "plan_y": spot.plan_y,
        "rotation": spot.rotation,
        "since": since.isoformat() if since else None,
        "since_label": _date(since),
        "born_today": spot.active_from == seating_service.today(),
    }


def totals(spots) -> dict:
    counted = [spot for spot in spots if spot.counts_in_capacity]
    return {
        "capacity_seats": sum(spot.seats for spot in counted),
        "capacity_spots": len(counted),
        "extra_seats": sum(spot.seats for spot in spots if not spot.counts_in_capacity),
    }


def _value(field: str, value) -> str:
    if field == "shape":
        return _SHAPE_LABELS.get(value, value or "")
    if field == "counts_in_capacity":
        return "conta" if value else "extra de dia cheio"
    if value in (None, ""):
        return "vazio"
    return str(value)


def _summary(payload: dict, label: str) -> str:
    """Uma frase do que mudou, para o operador ler sem abrir o antes/depois."""
    action = str(payload.get("action", "")).rsplit(".", 1)[-1]
    before = payload.get("before") or {}
    after = payload.get("after") or {}
    if action == "add":
        seats = after.get("seats")
        return f"{label} entrou no salão ({seats} {'lugar' if seats == 1 else 'lugares'})."
    if action == "remove":
        return f"{label} saiu do salão a partir de hoje."
    parts: list[str] = []
    moved = False
    for field in after:
        if field in ("plan_x", "plan_y"):
            moved = True
            continue
        if field in ("active_from", "active_until", "ref"):
            continue
        name = _FIELD_LABELS.get(field, field)
        parts.append(f"{name} de {_value(field, before.get(field))} para {_value(field, after.get(field))}")
    if moved:
        parts.append("mudou de lugar na planta")
    text = f"{label}: {', '.join(parts) or 'sem mudança visível'}."
    if action == "version":
        text += " Vale a partir de hoje; os dias de antes seguem com a versão anterior."
    return text


def history(limit: int = HISTORY_LIMIT) -> list[dict]:
    from django.contrib.admin.models import LogEntry
    from django.contrib.contenttypes.models import ContentType

    content_type = ContentType.objects.get_for_model(SeatingSpot)
    entries = (
        LogEntry.objects.filter(content_type=content_type)
        .select_related("user")
        .order_by("-action_time", "-pk")[:limit]
    )
    rows = []
    for entry in entries:
        try:
            payload = json.loads(entry.change_message or "{}")
        except ValueError:
            payload = {}
        if not isinstance(payload, dict) or not str(payload.get("action", "")).startswith(seating_service.AUDIT_ACTION):
            # Gravação do Admin (mensagem padrão do Django): entra com o texto dele.
            payload = {}
        label = entry.object_repr or (payload.get("ref") or "")
        user = entry.user
        local = timezone.localtime(entry.action_time)
        rows.append({
            "id": entry.pk,
            "at": entry.action_time.isoformat(),
            "at_label": formats.date_format(local, "d/m/Y H:i"),
            "who": (user.get_full_name().strip() or user.get_username()) if user else "",
            "ref": payload.get("ref") or entry.object_id,
            "action": str(payload.get("action", "admin")).rsplit(".", 1)[-1],
            "summary": _summary(payload, label) if payload else f"{label}: alterado pelo Admin.",
            "before": payload.get("before"),
            "after": payload.get("after"),
        })
    return rows


def build_seating() -> dict:
    spots = seating_service.active_spots()
    return {
        "today": seating_service.today().isoformat(),
        "today_label": _date(seating_service.today()),
        "revision": seating_service.revision(spots),
        "spots": [spot_card(spot) for spot in spots],
        "totals": totals(spots),
        "shapes": [{"value": value, "label": label} for value, label in SpotShape.choices],
        "max_seats": seating_service.MAX_SEATS,
        "history": history(),
    }
