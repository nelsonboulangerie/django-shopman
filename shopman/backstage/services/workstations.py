"""Postos de trabalho: criar, renomear, desativar, e o que a tela de provisionar lê.

O modelo e o porquê estão em ``models/workstation.py``; as palavras, em
``workstation_vocabulary.py``. Aqui ficam as regras de escrita:

* todo ``Terminal`` tem o seu posto Caixa, criado junto com ele
  (``ensure_cash_desk_workstation``, ligado a ``post_save`` em ``apps.py``);
* um ``Terminal`` novo não pode tomar o ref de um posto sem caixa
  (``guard_terminal_ref``, em ``pre_save``), senão os dispositivos daquele posto
  passariam a abrir a gaveta dele;
* desativar um posto solta TODOS os dispositivos dele: um posto fora do ar não pode
  continuar abrindo a antessala.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify

from shopman.backstage.workstation_vocabulary import (
    CASH_DESK,
    COPY,
    KIND_LABELS,
    devices_label,
    kind_label,
    kinds_for_surface,
)


class WorkstationError(ValueError):
    """Pedido recusado; a mensagem vai ao operador."""

    def __init__(self, message: str, *, field: str = "", code: str = "workstation_invalid"):
        super().__init__(message)
        self.field = field
        self.code = code


# ── Signals de Terminal ─────────────────────────────────────────────────


def guard_terminal_ref(sender, instance, **kwargs) -> None:
    """Recusa um ``Terminal`` cujo ref já é de um posto SEM caixa."""
    from shopman.backstage.models import Workstation

    if not instance.ref:
        return
    clash = Workstation.objects.filter(ref=instance.ref, terminal__isnull=True).exists()
    if clash:
        raise ValidationError(
            {"ref": f"Já existe um posto sem caixa com o ref {instance.ref}. Escolha outro ref para o caixa."}
        )


def ensure_cash_desk_workstation(sender, instance, created: bool = False, raw: bool = False, **kwargs) -> None:
    """Todo caixa é um posto: o ``Terminal`` novo ganha o seu posto Caixa."""
    if raw:
        return
    from shopman.backstage.models import Workstation

    if Workstation.objects.filter(terminal=instance).exists():
        return
    Workstation.objects.create(
        ref=instance.ref,
        label=instance.label or instance.ref,
        kind=CASH_DESK,
        terminal=instance,
        is_active=instance.is_active,
    )


# ── Leitura ─────────────────────────────────────────────────────────────


def get_active(ref: str):
    from shopman.backstage.models import Workstation

    ref = str(ref or "").strip()
    if not ref:
        return None
    return Workstation.objects.select_related("terminal").filter(ref=ref, is_active=True).first()


def card(workstation) -> dict | None:
    """O posto como a tela o mostra (contexto no rail, cabeçalho)."""
    if workstation is None:
        return None
    return {
        "ref": workstation.ref,
        "label": workstation.label,
        "kind": workstation.kind,
        "kind_label": kind_label(workstation.kind),
        "has_cash_desk": workstation.has_cash_desk,
        "context_label": f"{COPY['context_prefix']} {workstation.label}",
    }


def device_count(ref: str) -> int:
    from shopman.backstage.station_trust import active_station_devices

    return len(active_station_devices(ref))


def _has_open_shift(workstation) -> bool:
    if workstation.terminal_id is None:
        return False
    from shopman.cashman import services as cash

    return cash.open_shift_for_terminal(workstation.terminal) is not None


def option(workstation) -> dict:
    """Uma linha da lista de provisionar: o posto e o que já está nele."""
    devices = device_count(workstation.ref)
    open_shift = _has_open_shift(workstation)
    hints = []
    if workstation.has_cash_desk:
        hints.append(COPY["cash_desk_hint"])
    if devices:
        hints.append(devices_label(devices))
    if open_shift:
        hints.append(COPY["open_shift_hint"])
    return {
        **card(workstation),
        "active_devices": devices,
        "has_open_shift": open_shift,
        "hint": " · ".join(hints),
    }


def provision_state(*, surface: str, current_ref: str) -> dict:
    """O que a tela de provisionar precisa, para AQUELE app."""
    from shopman.backstage.models import Workstation

    kinds = kinds_for_surface(surface)
    workstations = (
        Workstation.objects.select_related("terminal")
        .filter(is_active=True, kind__in=kinds)
        .exclude(terminal__is_active=False)
        .order_by("label", "ref")
    )
    order = {kind: index for index, kind in enumerate(kinds)}
    options = sorted((option(w) for w in workstations), key=lambda o: (order.get(o["kind"], 99), o["label"]))
    return {
        "station": current_ref,
        "workstation": card(get_active(current_ref)),
        "kinds": [{"kind": kind, "label": KIND_LABELS[kind]} for kind in kinds],
        "workstations": options,
        "copy": dict(COPY),
    }


# ── Escrita (cadastro) ──────────────────────────────────────────────────


def _clean_label(label) -> str:
    label = " ".join(str(label or "").split())
    if not label:
        raise WorkstationError("Dê um nome ao posto.", field="label")
    if len(label) > 80:
        raise WorkstationError("Nome longo demais (até 80 letras).", field="label")
    return label


def _free_ref(label: str) -> str:
    from shopman.cashman.models import Terminal

    from shopman.backstage.models import Workstation

    base = (slugify(label) or "posto")[:70]
    candidate = base
    n = 2
    while Workstation.objects.filter(ref=candidate).exists() or Terminal.objects.filter(ref=candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


@transaction.atomic
def create(*, label, kind) -> object:
    """Cria um posto SEM caixa. O posto Caixa nasce com o caixa (Admin do terminal)."""
    from shopman.backstage.models import Workstation

    label = _clean_label(label)
    kind = str(kind or "").strip()
    if kind not in KIND_LABELS:
        raise WorkstationError("Escolha o tipo do posto.", field="kind")
    if kind == CASH_DESK:
        raise WorkstationError(
            "O posto Caixa nasce com o caixa, no cadastro de terminais.", field="kind", code="cash_desk_needs_terminal"
        )
    workstation = Workstation(ref=_free_ref(label), label=label, kind=kind)
    workstation.full_clean()
    workstation.save()
    return workstation


@transaction.atomic
def update(ref: str, *, label=None, kind=None, is_active=None):
    """Renomeia, muda o tipo ou liga/desliga. Desligar solta todos os dispositivos."""
    from shopman.backstage.models import Workstation

    workstation = Workstation.objects.select_for_update().filter(ref=ref).first()
    if workstation is None:
        raise WorkstationError(COPY["unknown"], code="workstation_unknown")
    fields = []
    if label is not None:
        workstation.label = _clean_label(label)
        fields.append("label")
    if kind is not None:
        kind = str(kind).strip()
        if kind not in KIND_LABELS:
            raise WorkstationError("Escolha o tipo do posto.", field="kind")
        if kind == CASH_DESK and workstation.terminal_id is None:
            raise WorkstationError(
                "Só um posto com caixa pode ser do tipo Caixa.", field="kind", code="cash_desk_needs_terminal"
            )
        workstation.kind = kind
        fields.append("kind")
    if is_active is not None:
        workstation.is_active = bool(is_active)
        fields.append("is_active")
    if fields:
        try:
            workstation.full_clean()
        except ValidationError as exc:
            field, messages = next(iter(exc.message_dict.items()))
            raise WorkstationError(messages[0], field=field) from exc
        workstation.save(update_fields=[*fields, "updated_at"])
    if is_active is False:
        release_all(workstation.ref)
    return workstation


def devices(ref: str) -> list[dict]:
    """Os dispositivos fixados no posto, do mais recente ao mais antigo."""
    from shopman.backstage.station_trust import active_station_devices

    return [
        {
            "id": str(device.pk),
            "label": device.label or "",
            "ip_address": device.ip_address or "",
            "created_at": device.created_at.isoformat() if device.created_at else None,
            "last_used_at": device.last_used_at.isoformat() if device.last_used_at else None,
        }
        for device in active_station_devices(ref)
    ]


def release_device(ref: str, device_id: str) -> bool:
    """Solta UM dispositivo do posto (o tablet perdido, o que saiu da loja)."""
    import uuid

    from shopman.doorman.models import SubjectType, TrustedDevice

    try:
        uuid.UUID(str(device_id))
    except ValueError:
        return False
    device = TrustedDevice.objects.filter(
        pk=device_id, subject_type=SubjectType.STATION, subject_id=ref, is_active=True
    ).first()
    if device is None:
        return False
    device.revoke()
    return True


def release_all(ref: str) -> int:
    from shopman.doorman.models import SubjectType, TrustedDevice

    return TrustedDevice.revoke_all_for(SubjectType.STATION, ref)


def management_list() -> list[dict]:
    """O cadastro inteiro, ativos e desativados, para a tela de Postos."""
    from shopman.backstage.models import Workstation

    rows = []
    for workstation in Workstation.objects.select_related("terminal").order_by("-is_active", "label", "ref"):
        rows.append(
            {
                **card(workstation),
                "is_active": workstation.is_active,
                "devices": devices(workstation.ref),
            }
        )
    return rows
