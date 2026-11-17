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
from datetime import datetime, time, timedelta

from django.utils import timezone
from shopman.utils.formatting import format_clock, format_local

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
#: Valores do iFood que chegam como código e viram palavra de gente. O código vai
#: junto, em texto secundário, para quem for conferir com o iFood.
_VALUE_WORDS = {
    "type": {"STORE": "Loja", "RESTAURANT": "Restaurante", "MARKET": "Mercado"},
    "status": {
        "AVAILABLE": "Ativa no cadastro do iFood",
        "UNAVAILABLE": "Indisponível no cadastro do iFood",
        "DISABLED": "Desativada no cadastro do iFood",
    },
    "test": {"TEST": "Sim"},
}
#: Explicação curta da linha que confundiria sem ela.
_DETAIL_HINTS = {
    "status": "É o cadastro da loja no iFood. Se ela recebe pedido agora, quem diz é a Disponibilidade.",
}
_OPERATION_WORDS = {"delivery": "Entrega", "takeout": "Retirada", "indoor": "No salão"}
_CHANNEL_WORDS = {"ifood-app": "App do iFood", "IFOOD": "App do iFood"}
_CHECK_LABELS = {
    "unavailabilities": "Pausas",
    "is-connected": "Conexão com a casa",
    "opening-hours": "Horário de funcionamento",
    "catalog": "Cardápio",
    "delivery-area": "Área de entrega",
}
_CHECK_STATE_LABELS = {
    "OK": "Ok",
    "WARNING": "Alerta",
    "CLOSED": "Fechada",
    "UNAVAILABLE": "Indisponível",
    "ERROR": "Erro",
}
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


def _moment(value: datetime | None, tz, now: datetime | None = None) -> str:
    """ "às 14h05" hoje; "em 16/11 às 14h05" em outro dia. Lê depois de "Consultado"."""
    if value is None:
        return ""
    local = timezone.localtime(value, timezone=tz)
    today = timezone.localtime(now or timezone.now(), timezone=tz).date()
    clock = format_clock(local.time())
    return f"às {clock}" if local.date() == today else f"em {local:%d/%m} às {clock}"  # hora-ok: dia/mês da frase


def _period(starts_at: datetime | None, ends_at: datetime | None, tz, now: datetime) -> str:
    if starts_at is None or ends_at is None:
        return f"Desde {_when(starts_at, tz)}" if starts_at else ""
    start = timezone.localtime(starts_at, timezone=tz)
    end = timezone.localtime(ends_at, timezone=tz)
    today = timezone.localtime(now, timezone=tz).date()
    if start.date() == end.date():
        days = (start.date() - today).days
        day = {0: "Hoje", 1: "Amanhã"}.get(days, f"{start:%d/%m}")  # hora-ok: dia/mês da frase
        return f"{day}, das {format_clock(start.time())} às {format_clock(end.time())}"
    return f"De {_when(starts_at, tz)} até {_when(ends_at, tz)}"


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
    #: O código do iFood por trás da palavra (``DISABLED``), em texto secundário.
    code: str = ""
    hint: str = ""


@dataclass(frozen=True)
class StatusCheck:
    code: str
    label: str
    state: str
    state_label: str
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


def _date(value) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return _display(value)
    return format_local(timezone.localtime(parsed, timezone=business_calendar.shop_timezone()), "%d/%m/%Y")


def _row(key: str, value) -> DetailRow:
    words = _VALUE_WORDS.get(key, {})
    raw = str(value) if value not in (None, "") else ""
    if key == "createdAt":
        shown, code = _date(value), ""
    elif raw in words:
        shown, code = words[raw], raw
    else:
        shown, code = _display(value), ""
    return DetailRow(label=_DETAIL_LABELS[key], value=shown, code=code, hint=_DETAIL_HINTS.get(key, ""))


def _operation_rows(operations) -> list[DetailRow]:
    """Operação e canal de venda em rótulos de gente; o número só quando há mais de um."""
    rows: list[DetailRow] = []
    operations = [op for op in operations or [] if isinstance(op, dict)]
    for index, op in enumerate(operations, start=1):
        suffix = f" {index}" if len(operations) > 1 else ""
        name = str(op.get("name") or "")
        rows.append(
            DetailRow(label=f"Operação{suffix}", value=_OPERATION_WORDS.get(name, name or "(vazio)"), code=name)
        )
        channels = op.get("salesChannels") or ([op["salesChannel"]] if isinstance(op.get("salesChannel"), dict) else [])
        for channel in channels:
            if not isinstance(channel, dict):
                continue
            cname = str(channel.get("name") or "")
            rows.append(
                DetailRow(
                    label=f"Canal de venda{suffix}", value=_CHANNEL_WORDS.get(cname, cname or "(vazio)"), code=cname
                )
            )
            if "enabled" in channel:
                rows.append(DetailRow(label=f"Ativo no iFood{suffix}", value=_display(channel.get("enabled"))))
    return rows


def _detail_rows(body: dict) -> tuple[DetailRow, ...]:
    body = dict(body or {})
    operations = body.pop("operations", None)
    pairs = _flatten(body)
    known = [(key, value) for key, value in pairs if key in _DETAIL_LABELS]
    known.sort(key=lambda pair: list(_DETAIL_LABELS).index(pair[0]))
    # Campo que o iFood mandar e não tiver rótulo aparece com o nome dele: "detalhes
    # completos" é tudo, e esconder seria pior que mostrar o nome técnico.
    rest = [DetailRow(label=key, value=_display(value)) for key, value in pairs if key not in _DETAIL_LABELS]
    return (*(_row(key, value) for key, value in known), *_operation_rows(operations), *rest)


def _message(block) -> tuple[str, str]:
    block = block if isinstance(block, dict) else {}
    return str(block.get("title") or ""), str(block.get("subtitle") or block.get("description") or "")


def _operation(op: dict) -> OperationStatus:
    state = str(op.get("state") or "").upper()
    title, description = _message(op.get("message"))
    sales = op.get("salesChannel")
    channel = str(sales.get("name") if isinstance(sales, dict) else sales or "")
    checks = []
    for validation in op.get("validations") or []:
        if not isinstance(validation, dict):
            continue
        vtitle, vdescription = _message(validation.get("message"))
        code = str(validation.get("id") or validation.get("code") or "")
        vstate = str(validation.get("state") or "").upper()
        checks.append(
            StatusCheck(
                code=code,
                label=_CHECK_LABELS.get(code, vtitle or code),
                state=vstate,
                state_label=_CHECK_STATE_LABELS.get(vstate, vstate or "Sem estado"),
                title=vtitle,
                description=vdescription,
            )
        )
    return OperationStatus(
        operation=_OPERATION_WORDS.get(str(op.get("operation") or ""), str(op.get("operation") or "")),
        sales_channel=_CHANNEL_WORDS.get(channel, channel),
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
        checked_at_display=_moment(now, tz, now),
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
    #: "Hoje, das 14h04 às 14h34"; em dias diferentes, "De 20/11 às 18h até 21/11 às 8h".
    period_display: str
    #: Quando a loja volta: "às 14h34" hoje, "em 18/11 às 8h" em outro dia.
    resume_display: str
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
        return InterruptionsProjection(
            refused=refused, error=api_error_copy(exc), checked_at_display=_moment(now, tz, now)
        )
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
                    period_display=_period(starts_at, ends_at, tz, now),
                    resume_display=_moment(ends_at, tz, now),
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
                    period_display=_period(record.starts_at, record.ends_at, tz, now),
                    resume_display=_moment(record.ends_at, tz, now),
                    removable=False,
                    listed_by_ifood=False,
                ),
            )
        )
    rows.sort(key=lambda pair: pair[0])
    return InterruptionsProjection(
        items=tuple(row for _, row in rows), refused=refused, checked_at_display=_moment(now, tz, now)
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
    #: A última gravação do horário no iFood (``IFoodStoreStatus.synced_at``). O iFood
    #: confirma o PUT na hora e o GET mostra o novo minutos depois (medido em
    #: 17/11/2026): gravado há pouco + diferente = esperando o iFood, não defeito.
    written_at_display: str = ""
    written_recently: bool = False


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


#: Quanto tempo depois de gravar a diferença ainda é "o iFood ainda não mostra".
WRITE_SETTLE = timedelta(minutes=90)


def _last_write(now: datetime, tz) -> tuple[str, bool]:
    from shopman.shop.models import IFoodStoreStatus

    row = IFoodStoreStatus.objects.filter(merchant_id=ifood_merchant.merchant_id()).first()
    written = getattr(row, "synced_at", None)
    if written is None:
        return "", False
    return _moment(written, tz, now), now - written < WRITE_SETTLE


def build_opening_hours(*, now: datetime | None = None) -> OpeningHoursProjection:
    now = now or timezone.now()
    tz = business_calendar.shop_timezone()
    house = business_calendar.weekly_shifts()
    written_at_display, written_recently = _last_write(now, tz)
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
            checked_at_display=_moment(now, tz, now),
            written_at_display=written_at_display,
            written_recently=written_recently,
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
        checked_at_display=_moment(now, tz, now),
        written_at_display=written_at_display,
        written_recently=written_recently,
    )


def write_opening_hours(*, now: datetime | None = None) -> OpeningHoursProjection:
    """Grava agora no iFood o horário da casa (o mesmo ``sync_store`` da fila) e relê.

    Levanta ``MerchantAPIError`` com a recusa do iFood (400 de turno sobreposto, 403).
    """
    ifood_merchant.sync_store(now=now)
    return build_opening_hours(now=now)


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
    "write_opening_hours",
]
