"""A loja no iFood, consultada ao vivo: lojas, detalhe, disponibilidade, pausas e horário.

O card do canal iFood (aba Canais) mostra a ÚLTIMA conferência do maintenance-worker.
Esta tela pergunta ao iFood agora (módulo Merchant) e mostra a resposta dele, com o
que a casa pediu ao lado: é onde o gestor confere que a pausa e o horário do Gestor
chegaram ao iFood, e onde o iFood homologa o módulo.

Cada seção é uma chamada própria e falha sozinha: um 403 no horário não apaga a lista
de lojas. A falha vira frase de balcão (``error``), nunca a mensagem crua do iFood.

Desligar e ligar o iFood é o toggle "Ativo" do canal (``channel_switch``), o mesmo
gesto de todo canal. Aqui só se REMOVE a pausa que nasceu fora do Gestor (Portal do
Parceiro): é o que destrava o 409 de "já existe outra pausa no mesmo horário".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

from django.utils import timezone
from shopman.utils.formatting import format_local

from shopman.shop.services import business_calendar, ifood_merchant

#: Rótulos dos campos do detalhe da loja (``GET /merchants/{id}``). Campo que o iFood
#: devolver e não estiver aqui aparece com o nome dele: "detalhes completos" é tudo.
_DETAIL_LABELS = {
    "id": "ID da loja",
    "name": "Nome",
    "corporateName": "Razão social",
    "description": "Descrição",
    "averageTicket": "Ticket médio",
    "exclusive": "Exclusiva do iFood",
    "type": "Tipo",
    "status": "Situação",
    "createdAt": "Cadastrada em",
    "address.street": "Rua",
    "address.number": "Número",
    "address.district": "Bairro",
    "address.city": "Cidade",
    "address.state": "Estado",
    "address.postalCode": "CEP",
    "address.country": "País",
    "address.latitude": "Latitude",
    "address.longitude": "Longitude",
    "test": "Loja de teste",
}
#: Pedaços do caminho de campo aninhado, para o que não tem rótulo próprio:
#: ``operations 1.salesChannels 1.enabled`` → ``Operação 1 · canal de venda 1 · ativo``.
_PATH_WORDS = (
    ("operations ", "Operação "),
    (".salesChannels ", " · canal de venda "),
    (".salesChannel", " · canal de venda"),
    (".name", ""),
    (".enabled", " · ativo"),
)
_STATE_LABELS = {
    "OK": "Aberta",
    "WARNING": "Aberta, com alerta",
    "CLOSED": "Fechada",
    "UNAVAILABLE": "Indisponível",
    "ERROR": "Fechada por erro",
}
_DAY_LABELS = {
    "monday": "Segunda",
    "tuesday": "Terça",
    "wednesday": "Quarta",
    "thursday": "Quinta",
    "friday": "Sexta",
    "saturday": "Sábado",
    "sunday": "Domingo",
}
_IFOOD_TO_DAY = {value: key for key, value in ifood_merchant._IFOOD_DAYS.items()}

ORIGIN_SWITCH = "switch"
ORIGIN_CALENDAR = "calendar"
ORIGIN_MANAGER = "manager"
ORIGIN_PORTAL = "portal"
_ORIGIN_LABELS = {
    ORIGIN_SWITCH: "iFood desligado no Gestor",
    ORIGIN_CALENDAR: "Calendário da loja",
    ORIGIN_MANAGER: "Pausa do gestor",
    ORIGIN_PORTAL: "Portal do Parceiro",
}


def api_error_copy(exc: ifood_merchant.MerchantAPIError) -> str:
    """A recusa do iFood numa frase de balcão (com o código, para quem for conferir)."""
    if exc.status == 0:
        return "O iFood não respondeu. Tente de novo em instantes."
    if exc.status == 401:
        return "O iFood recusou a credencial do app (HTTP 401)."
    if exc.status == 403:
        return "O iFood recusou (HTTP 403): o módulo Merchant não está liberado para este app."
    if exc.status == 404:
        return "O iFood não encontrou esta loja (HTTP 404)."
    if exc.status == 409:
        return "O iFood recusou: já existe outra pausa no mesmo horário (HTTP 409)."
    if exc.status == 400:
        return "O iFood recusou o pedido por estar fora do formato dele (HTTP 400)."
    return f"O iFood recusou o pedido (HTTP {exc.status})."


def _when(value: datetime | None, tz) -> str:
    return format_local(timezone.localtime(value, timezone=tz), "%d/%m {clock}") if value else ""


# ── Lojas vinculadas ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MerchantRow:
    id: str
    name: str
    corporate_name: str
    is_current: bool


@dataclass(frozen=True)
class MerchantsProjection:
    merchants: tuple[MerchantRow, ...] = ()
    error: str = ""


def build_merchants() -> MerchantsProjection:
    try:
        merchants = ifood_merchant.list_merchants()
    except ifood_merchant.MerchantAPIError as exc:
        return MerchantsProjection(error=api_error_copy(exc))
    current = ifood_merchant.merchant_id()
    return MerchantsProjection(
        merchants=tuple(
            MerchantRow(
                id=str(item.get("id") or ""),
                name=str(item.get("name") or ""),
                corporate_name=str(item.get("corporateName") or ""),
                is_current=str(item.get("id") or "") == current,
            )
            for item in merchants
            if isinstance(item, dict)
        )
    )


# ── Detalhe e disponibilidade ─────────────────────────────────────────────────


@dataclass(frozen=True)
class DetailRow:
    label: str
    value: str


@dataclass(frozen=True)
class StatusCheck:
    code: str
    state: str
    title: str
    description: str


@dataclass(frozen=True)
class OperationStatus:
    operation: str
    sales_channel: str
    available: bool
    state: str
    state_label: str
    title: str
    description: str
    checks: tuple[StatusCheck, ...] = ()


@dataclass(frozen=True)
class MerchantProjection:
    merchant_id: str
    detail: tuple[DetailRow, ...] = ()
    detail_error: str = ""
    available: bool | None = None
    operations: tuple[OperationStatus, ...] = ()
    status_error: str = ""
    checked_at_display: str = ""


def _flatten(value, prefix: str = "") -> list[tuple[str, object]]:
    if isinstance(value, dict):
        out: list[tuple[str, object]] = []
        for key, item in value.items():
            out.extend(_flatten(item, f"{prefix}.{key}" if prefix else str(key)))
        return out
    if isinstance(value, list):
        if all(not isinstance(item, (dict, list)) for item in value):
            return [(prefix, ", ".join(str(item) for item in value))]
        out = []
        for index, item in enumerate(value, start=1):
            out.extend(_flatten(item, f"{prefix} {index}"))
        return out
    return [(prefix, value)]


def _display(value) -> str:
    if value is True:
        return "Sim"
    if value is False:
        return "Não"
    if value is None or value == "":
        return "(vazio)"
    return str(value)


def _detail_rows(body: dict) -> tuple[DetailRow, ...]:
    pairs = _flatten(body)
    known = [(key, value) for key, value in pairs if key in _DETAIL_LABELS]
    known.sort(key=lambda pair: list(_DETAIL_LABELS).index(pair[0]))
    rest = [(key, value) for key, value in pairs if key not in _DETAIL_LABELS]
    return tuple(
        DetailRow(label=_DETAIL_LABELS.get(key) or _path_label(key), value=_display(value))
        for key, value in [*known, *rest]
    )


def _path_label(key: str) -> str:
    for raw, word in _PATH_WORDS:
        key = key.replace(raw, word)
    return key


def _message(block) -> tuple[str, str]:
    block = block if isinstance(block, dict) else {}
    return str(block.get("title") or ""), str(block.get("subtitle") or block.get("description") or "")


def _operation(op: dict) -> OperationStatus:
    state = str(op.get("state") or "").upper()
    title, description = _message(op.get("message"))
    sales = op.get("salesChannel")
    checks = []
    for validation in op.get("validations") or []:
        if not isinstance(validation, dict):
            continue
        vtitle, vdescription = _message(validation.get("message"))
        checks.append(
            StatusCheck(
                code=str(validation.get("id") or validation.get("code") or ""),
                state=str(validation.get("state") or "").upper(),
                title=vtitle,
                description=vdescription,
            )
        )
    return OperationStatus(
        operation=str(op.get("operation") or ""),
        sales_channel=str(sales.get("name") if isinstance(sales, dict) else sales or ""),
        available=op.get("available") is True,
        state=state,
        state_label=_STATE_LABELS.get(state, state or "Sem estado"),
        title=title,
        description=description,
        checks=tuple(checks),
    )


def build_merchant(*, now: datetime | None = None) -> MerchantProjection:
    now = now or timezone.now()
    tz = business_calendar.shop_timezone()
    mid = ifood_merchant.merchant_id()
    detail: tuple[DetailRow, ...] = ()
    detail_error = ""
    try:
        detail = _detail_rows(ifood_merchant.get_merchant())
    except ifood_merchant.MerchantAPIError as exc:
        detail_error = api_error_copy(exc)
    operations: tuple[OperationStatus, ...] = ()
    status_error = ""
    available = None
    try:
        raw = ifood_merchant.get_status()
        operations = tuple(_operation(op) for op in raw)
        available = any(op.available for op in operations)
    except ifood_merchant.MerchantAPIError as exc:
        status_error = api_error_copy(exc)
    return MerchantProjection(
        merchant_id=mid,
        detail=detail,
        detail_error=detail_error,
        available=available,
        operations=operations,
        status_error=status_error,
        checked_at_display=_when(now, tz),
    )


# ── Pausas ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class InterruptionRow:
    id: str
    description: str
    starts_at_display: str
    ends_at_display: str
    origin: str
    origin_label: str
    in_effect: bool
    #: Só a pausa feita fora do Gestor se remove aqui; a do Gestor sai ligando o iFood de novo.
    removable: bool
    #: ``False``: o iFood aceitou a pausa (devolveu o id), mas a lista dele ainda não a traz.
    listed_by_ifood: bool = True


@dataclass(frozen=True)
class RefusedPause:
    origin_label: str
    starts_at_display: str
    ends_at_display: str
    error: str


@dataclass(frozen=True)
class InterruptionsProjection:
    items: tuple[InterruptionRow, ...] = ()
    refused: tuple[RefusedPause, ...] = ()
    error: str = ""
    checked_at_display: str = ""


def _origin(record) -> str:
    from shopman.shop.models import IFoodInterruptionKind

    if record is None:
        return ORIGIN_PORTAL
    if record.kind == IFoodInterruptionKind.MANUAL:
        return ORIGIN_MANAGER
    return ORIGIN_SWITCH if str(record.calendar_key or "").startswith("off:") else ORIGIN_CALENDAR


def _ours_by_ifood_id(ids: list[str]) -> dict:
    from shopman.shop.models import IFoodInterruption

    if not ids:
        return {}
    return {
        record.ifood_id: record
        for record in IFoodInterruption.objects.filter(merchant_id=ifood_merchant.merchant_id(), ifood_id__in=ids)
    }


def build_interruptions(*, now: datetime | None = None) -> InterruptionsProjection:
    from shopman.shop.models import IFoodInterruption
    from shopman.shop.models import IFoodInterruptionState as S

    now = now or timezone.now()
    tz = business_calendar.shop_timezone()
    refused = tuple(
        RefusedPause(
            origin_label=_ORIGIN_LABELS[_origin(record)],
            starts_at_display=_when(record.starts_at, tz),
            ends_at_display=_when(record.ends_at, tz),
            error=record.last_error or "O iFood recusou esta pausa.",
        )
        for record in IFoodInterruption.objects.filter(
            merchant_id=ifood_merchant.merchant_id(), state=S.FAILED, ends_at__gt=now
        ).order_by("starts_at")
    )
    try:
        remote = ifood_merchant.list_interruptions()
    except ifood_merchant.MerchantAPIError as exc:
        return InterruptionsProjection(refused=refused, error=api_error_copy(exc), checked_at_display=_when(now, tz))
    ours = _ours_by_ifood_id([str(item.get("id")) for item in remote if item.get("id")])
    rows = []
    for item in remote:
        remote_id = str(item.get("id") or "")
        starts_at = ifood_merchant._parse_remote_datetime(item.get("start"), tz)
        ends_at = ifood_merchant._parse_remote_datetime(item.get("end"), tz)
        if ends_at is not None and ends_at <= now:
            continue
        origin = _origin(ours.get(remote_id))
        rows.append(
            (
                starts_at or now,
                InterruptionRow(
                    id=remote_id,
                    description=str(item.get("description") or ""),
                    starts_at_display=_when(starts_at, tz),
                    ends_at_display=_when(ends_at, tz),
                    origin=origin,
                    origin_label=_ORIGIN_LABELS[origin],
                    in_effect=bool(starts_at and starts_at <= now),
                    removable=origin == ORIGIN_PORTAL and bool(remote_id),
                ),
            )
        )
    # A pausa que o iFood aceitou e a lista dele não traz. Medido na loja de teste em
    # 17/11/2026: o POST devolve 201 com id, a validação ``unavailabilities`` fecha a
    # loja, e o ``GET /interruptions`` segue ``[]``. Esconder a pausa seria mentir que
    # a loja está aberta; a linha diz de onde veio a certeza.
    listed = {row.id for _, row in rows}
    for record in IFoodInterruption.objects.filter(
        merchant_id=ifood_merchant.merchant_id(), state=S.ACTIVE, ends_at__gt=now
    ).exclude(ifood_id=""):
        if record.ifood_id in listed:
            continue
        origin = _origin(record)
        rows.append(
            (
                record.starts_at,
                InterruptionRow(
                    id=record.ifood_id,
                    description=record.description,
                    starts_at_display=_when(record.starts_at, tz),
                    ends_at_display=_when(record.ends_at, tz),
                    origin=origin,
                    origin_label=_ORIGIN_LABELS[origin],
                    in_effect=record.starts_at <= now,
                    removable=False,
                    listed_by_ifood=False,
                ),
            )
        )
    rows.sort(key=lambda pair: pair[0])
    return InterruptionsProjection(
        items=tuple(row for _, row in rows), refused=refused, checked_at_display=_when(now, tz)
    )


class PauseNotRemovable(Exception):
    """A pausa é do Gestor ou do calendário: removê-la direto voltaria na próxima gravação."""


def remove_portal_interruption(interruption_id: str) -> None:
    """Remove no iFood uma pausa feita fora do Gestor (Portal do Parceiro).

    A pausa do Gestor sai ligando o iFood de novo (toggle do canal) e a do calendário sai
    pelo calendário: apagar qualquer uma delas aqui seria desfeito pela próxima
    gravação, e o gestor veria a pausa "voltar sozinha".
    """
    if interruption_id in _ours_by_ifood_id([interruption_id]):
        raise PauseNotRemovable(interruption_id)
    ifood_merchant.delete_interruption(interruption_id)


# ── Horário ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DayHours:
    day: str
    label: str
    house: str
    ifood: str
    matches: bool


@dataclass(frozen=True)
class OpeningHoursProjection:
    days: tuple[DayHours, ...] = ()
    matches: bool | None = None
    governs: bool = False
    error: str = ""
    checked_at_display: str = ""


def _shift_phrase(shifts: list[tuple[time, time]]) -> str:
    return business_calendar.format_shifts(shifts) if shifts else "Fechado"


def _remote_by_day(remote: list[dict]) -> dict[str, list[tuple[time, time]]]:
    out: dict[str, list[tuple[time, time]]] = {}
    for shift in remote:
        day = _IFOOD_TO_DAY.get(str(shift.get("dayOfWeek") or "").upper())
        try:
            start = time.fromisoformat(str(shift.get("start") or ""))
            duration = int(shift.get("duration") or 0)
        except (TypeError, ValueError):
            continue
        if day is None or duration <= 0:
            continue
        minutes = start.hour * 60 + start.minute + duration
        end = time(23, 59) if minutes >= 24 * 60 else time(minutes // 60, minutes % 60)
        out.setdefault(day, []).append((start, end))
    for shifts in out.values():
        shifts.sort()
    return out


def build_opening_hours(*, now: datetime | None = None) -> OpeningHoursProjection:
    now = now or timezone.now()
    tz = business_calendar.shop_timezone()
    house = business_calendar.weekly_shifts()
    try:
        remote = ifood_merchant.get_opening_hours()
    except ifood_merchant.MerchantAPIError as exc:
        return OpeningHoursProjection(
            days=tuple(
                DayHours(day=d, label=_DAY_LABELS[d], house=_shift_phrase(house.get(d, [])), ifood="", matches=False)
                for d in business_calendar.DAY_ORDER
            ),
            governs=ifood_merchant.governs(),
            error=api_error_copy(exc),
            checked_at_display=_when(now, tz),
        )
    by_day = _remote_by_day(remote)
    days = tuple(
        DayHours(
            day=d,
            label=_DAY_LABELS[d],
            house=_shift_phrase(house.get(d, [])),
            ifood=_shift_phrase(by_day.get(d, [])),
            matches=house.get(d, []) == by_day.get(d, []),
        )
        for d in business_calendar.DAY_ORDER
    )
    return OpeningHoursProjection(
        days=days,
        matches=ifood_merchant.shifts_match(ifood_merchant.desired_shifts(), remote),
        governs=ifood_merchant.governs(),
        checked_at_display=_when(now, tz),
    )


__all__ = [
    "InterruptionsProjection",
    "MerchantProjection",
    "MerchantsProjection",
    "OpeningHoursProjection",
    "PauseNotRemovable",
    "api_error_copy",
    "build_interruptions",
    "build_merchant",
    "build_merchants",
    "build_opening_hours",
    "remove_portal_interruption",
]
