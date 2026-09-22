"""iFood Merchant: o Shopman como fonte única de "a loja está aberta" no iFood.

O que decide se a loja recebe pedido no iFood (documentação do módulo Merchant):
horário cadastrado, catálogo com item ativo, área de entrega, **nenhuma
interrupção ativa** e **polling a cada 30 s** (``is-connected``). Até aqui o
Shopman não falava com o módulo Merchant: o horário e as pausas moravam no
Portal do Parceiro, e a casa só sabia que o iFood tinha fechado quando o pedido
parava de chegar.

Este módulo faz três coisas, todas atrás de ``SHOPMAN_IFOOD["merchant_sync_enabled"]``
(env ``IFOOD_MERCHANT_SYNC=1``, desligado por padrão):

1. **Horário e calendário → iFood** (:func:`sync_store`). A grade semanal de
   ``Shop.opening_hours`` vira ``PUT /opening-hours`` — o iFood diz que esse
   verbo **substitui todos** os turnos, e dia fora da lista é dia fechado. O que
   a grade não expressa (feriado, fechamento pontual em ``closed_dates``) vira
   **interrupção** com início e fim, que é o que o iFood recomenda para
   fechamento temporário. Roda por Directive (``ifood.merchant_sync``), com
   retry, e é idempotente: lê antes de escrever, e só escreve o que difere.
2. **Pausa do gestor** (:func:`request_pause` / :func:`request_resume`). Fechar
   o iFood por estratégia com a casa aberta: uma interrupção com duração e
   motivo, e quem pediu fica registrado. Retomar apaga a interrupção.
3. **Conferência** (:func:`check_store`). O maintenance-worker lê ``GET /status``
   e, quando o iFood discorda da casa por mais de uma conferência, cria
   ``OperatorAlert``. É o vigia que o ``ifood_poll`` não tinha: polling caído
   aparece como ``is-connected`` reprovado.

⚠️ **O polling nunca é interruptor.** Parar o ``ifood_poll`` fecharia a loja
(``is-connected``), mas o polling também traz cancelamento e alteração de pedido
já aceito. Fechar é sempre interrupção ou horário.

Fuso: a documentação diz que o iFood interpreta a interrupção no fuso da LOJA e
ignora o do payload. Mandamos a hora local da loja com o deslocamento dela
(``2026-12-25T00:00:00-03:00``) — correto nas duas leituras possíveis.

Chamadas passam por ``ifood_http.request`` (retry da recusa de borda, token do
``ifood_auth``), o mesmo caminho do polling e dos callbacks de pedido.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from shopman.shop.services import business_calendar, ifood_http

logger = logging.getLogger(__name__)

_MERCHANTS_PATH = "/merchant/v1.0/merchants"

#: Quantos dias à frente o calendário é espelhado em interrupções. A varredura
#: diária empurra o horizonte; feriado mais distante entra quando se aproxima.
CALENDAR_HORIZON_DAYS = 14
#: A interrupção do iFood dura no máximo 7 dias; férias mais longas viram várias.
MAX_INTERRUPTION_DAYS = 7
#: Tolerância ao casar uma interrupção lida do iFood com a que pedimos.
_MATCH_TOLERANCE = timedelta(seconds=60)
#: Divergência só vira alerta depois de sobreviver a este intervalo — o iFood
#: aplica pausa e horário de forma assíncrona ("leva alguns segundos").
DIVERGENCE_GRACE = timedelta(minutes=4)
#: Janela do dedupe do alerta de divergência.
DIVERGENCE_ALERT_WINDOW_MINUTES = 60
#: Sem gravação há mais que isto, a conferência pede uma nova (cura o que foi
#: mexido no Portal e avança o horizonte do calendário).
RESYNC_EVERY = timedelta(hours=6)

ALERT_CLOSED_WHILE_OPEN = "ifood_store_closed_while_open"
ALERT_OPEN_WHILE_CLOSED = "ifood_store_open_while_closed"
ALERT_SYNC_FAILED = "ifood_store_sync_failed"

#: Durações oferecidas ao gestor. ``until_close`` = até o fim do expediente de hoje.
PAUSE_DURATIONS: dict[str, int] = {"30m": 30, "1h": 60, "2h": 120}
PAUSE_UNTIL_CLOSE = "until_close"

_IFOOD_DAYS = {
    "monday": "MONDAY",
    "tuesday": "TUESDAY",
    "wednesday": "WEDNESDAY",
    "thursday": "THURSDAY",
    "friday": "FRIDAY",
    "saturday": "SATURDAY",
    "sunday": "SUNDAY",
}
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
# Ordem de gravidade do estado da operação, do pior para o melhor.
_STATE_SEVERITY = ("ERROR", "CLOSED", "UNAVAILABLE", "WARNING", "OK")


# ── Configuração ──────────────────────────────────────────────────────────────


def _cfg() -> dict:
    return getattr(settings, "SHOPMAN_IFOOD", {}) or {}


def merchant_id() -> str:
    return str(_cfg().get("merchant_id") or "").strip()


def enabled() -> bool:
    """Chave ligada E integração direta configurada (client_id + merchant_id)."""
    cfg = _cfg()
    return bool(cfg.get("merchant_sync_enabled")) and bool(str(cfg.get("client_id") or "").strip()) and bool(merchant_id())


def governs(shop=None) -> bool:
    """O Shopman só governa o iFood quando a casa declarou grade semanal.

    Sem grade, o calendário da casa degrada para "sempre aberto" — espelhar isso
    no iFood seria inventar um expediente de 24 h que ninguém decidiu. Nesse
    caso nada é gravado nem conferido, e quem manda continua sendo o Portal.
    """
    return business_calendar.has_regular_hours(shop=shop)


# ── Cliente da API ────────────────────────────────────────────────────────────


class MerchantAPIError(Exception):
    """Falha numa chamada do módulo Merchant.

    ``retryable`` separa o que a Directive deve repetir (sem resposta, 429, 5xx)
    do que repetir não resolve (400, 403 da API, 409 de sobreposição).
    """

    def __init__(self, message: str, *, status: int = 0, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


class InterruptionOverlap(MerchantAPIError):
    """409: já existe interrupção no iFood cobrindo parte do mesmo intervalo."""


def _call(method: str, path: str, *, label: str, idempotent: bool, ok: tuple[int, ...], **kwargs):
    resp = ifood_http.request(method, path, label=label, idempotent=idempotent, **kwargs)
    if resp is None:
        # ``ifood_http`` já logou a causa (sem token, transporte, recusa de borda).
        raise MerchantAPIError(f"iFood merchant {label}: sem resposta utilizável", retryable=True)
    if resp.status_code in ok:
        return resp
    detail = _error_detail(resp)
    if resp.status_code == 409:
        raise InterruptionOverlap(detail or "interrupção sobreposta", status=409)
    raise MerchantAPIError(
        f"iFood merchant {label}: HTTP {resp.status_code} {detail}".strip(),
        status=resp.status_code,
        retryable=resp.status_code in _RETRYABLE_STATUS,
    )


def _error_detail(resp) -> str:
    try:
        body = resp.json()
    except Exception:
        return (getattr(resp, "text", "") or "")[:200]
    if isinstance(body, dict):
        error = body.get("error") if isinstance(body.get("error"), dict) else body
        return str(error.get("message") or error.get("detail") or error.get("code") or "")[:200]
    return ""


def _json(resp):
    try:
        return resp.json()
    except Exception:
        return None


def _merchant_path(suffix: str = "") -> str:
    return f"{_MERCHANTS_PATH}/{merchant_id()}{suffix}"


def list_merchants() -> list[dict]:
    resp = _call("GET", _MERCHANTS_PATH, label="merchant_list", idempotent=True, ok=(200,))
    body = _json(resp)
    return body if isinstance(body, list) else []


def get_merchant() -> dict:
    resp = _call("GET", _merchant_path(), label="merchant_detail", idempotent=True, ok=(200,))
    body = _json(resp)
    return body if isinstance(body, dict) else {}


def get_status() -> list[dict]:
    resp = _call("GET", _merchant_path("/status"), label="merchant_status", idempotent=True, ok=(200,))
    body = _json(resp)
    if isinstance(body, dict):
        body = [body]
    return [item for item in (body or []) if isinstance(item, dict)]


def list_interruptions() -> list[dict]:
    resp = _call("GET", _merchant_path("/interruptions"), label="merchant_interruptions", idempotent=True, ok=(200,))
    body = _json(resp)
    return [item for item in (body or []) if isinstance(item, dict)] if isinstance(body, list) else []


def create_interruption(*, starts_at: datetime, ends_at: datetime, description: str, tz) -> dict:
    """``POST /interruptions``. Não é idempotente: quem chama confere antes (``_find_remote``)."""
    resp = _call(
        "POST",
        _merchant_path("/interruptions"),
        label="merchant_interruption_create",
        idempotent=False,
        ok=(200, 201),
        json={
            "description": description[:255],
            "start": _ifood_datetime(starts_at, tz),
            "end": _ifood_datetime(ends_at, tz),
        },
    )
    body = _json(resp)
    return body if isinstance(body, dict) else {}


def delete_interruption(interruption_id: str) -> None:
    """``DELETE /interruptions/{id}``. 404 é "já não existe" — o efeito pedido."""
    _call(
        "DELETE",
        _merchant_path(f"/interruptions/{interruption_id}"),
        label="merchant_interruption_delete",
        idempotent=True,
        ok=(200, 202, 204, 404),
    )


def get_opening_hours() -> list[dict]:
    resp = _call("GET", _merchant_path("/opening-hours"), label="merchant_opening_hours", idempotent=True, ok=(200,))
    return _shifts_from_body(_json(resp))


def put_opening_hours(shifts: list[dict]) -> None:
    """``PUT /opening-hours``. Substitui TODOS os turnos — por isso é idempotente."""
    _call(
        "PUT",
        _merchant_path("/opening-hours"),
        label="merchant_opening_hours_put",
        idempotent=True,
        ok=(200, 201, 204),
        json={"storeId": merchant_id(), "shifts": shifts},
    )


def _shifts_from_body(body) -> list[dict]:
    """O GET devolve ``[{"shifts": [...]}]``; aceita também ``{"shifts": [...]}``."""
    containers = body if isinstance(body, list) else [body]
    shifts: list[dict] = []
    for container in containers:
        if isinstance(container, dict) and isinstance(container.get("shifts"), list):
            shifts.extend(item for item in container["shifts"] if isinstance(item, dict))
        elif isinstance(container, dict) and container.get("dayOfWeek"):
            shifts.append(container)
    return shifts


# ── Tradução casa → iFood ─────────────────────────────────────────────────────


def desired_shifts(shop=None) -> list[dict]:
    """A grade semanal da casa no formato do iFood: um turno por dia aberto."""
    shifts = []
    for day, (opens_at, closes_at) in business_calendar.weekly_windows(shop=shop).items():
        duration = (closes_at.hour * 60 + closes_at.minute) - (opens_at.hour * 60 + opens_at.minute)
        if duration <= 0:
            continue
        shifts.append({
            "dayOfWeek": _IFOOD_DAYS[day],
            "start": opens_at.strftime("%H:%M:%S"),
            "duration": duration,
        })
    return shifts


def _shift_key(shift: dict) -> tuple[str, str, int]:
    start = str(shift.get("start") or "")
    if len(start) == 5:
        start = f"{start}:00"
    try:
        duration = int(shift.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0
    return (str(shift.get("dayOfWeek") or "").upper(), start, duration)


def shifts_match(desired: list[dict], remote: list[dict]) -> bool:
    return sorted(map(_shift_key, desired)) == sorted(map(_shift_key, remote))


@dataclass(frozen=True)
class CalendarClosure:
    """Dias seguidos que o calendário fecha e a grade abriria, num só intervalo."""

    key: str
    starts_at: datetime
    ends_at: datetime
    label: str

    @property
    def description(self) -> str:
        return f"Fechado pelo calendário da loja: {self.label}" if self.label else "Fechado pelo calendário da loja"


def desired_calendar_closures(*, now: datetime | None = None, shop=None) -> list[CalendarClosure]:
    """Os fechamentos do calendário nos próximos ``CALENDAR_HORIZON_DAYS`` dias.

    Só entra o dia em que a grade semanal ABRIRIA: domingo sem expediente já está
    fechado pelo horário gravado, e uma interrupção ali seria ruído no Portal.
    Dias seguidos viram um intervalo só (meia-noite a meia-noite, no fuso da
    loja), partido em blocos de até ``MAX_INTERRUPTION_DAYS``.
    """
    now = now or timezone.now()
    tz = business_calendar.shop_timezone(shop=shop)
    today = timezone.localtime(now, timezone=tz).date()
    closed_days: list[tuple[date, str]] = []
    for offset in range(CALENDAR_HORIZON_DAYS + 1):
        day = today + timedelta(days=offset)
        closed, label = business_calendar.calendar_closure_on(day, shop=shop)
        if closed and business_calendar.selling_hours_for(day, shop=shop) is not None:
            closed_days.append((day, label))

    runs: list[list[tuple[date, str]]] = []
    for day, label in closed_days:
        if runs and (day - runs[-1][-1][0]).days == 1 and len(runs[-1]) < MAX_INTERRUPTION_DAYS:
            runs[-1].append((day, label))
        else:
            runs.append([(day, label)])

    closures = []
    for run in runs:
        first, last = run[0][0], run[-1][0]
        starts_at = datetime.combine(first, time.min, tzinfo=tz)
        ends_at = datetime.combine(last + timedelta(days=1), time.min, tzinfo=tz)
        if ends_at <= now:
            continue
        label = next((lbl for _, lbl in run if lbl), "")
        closures.append(CalendarClosure(key=f"{first.isoformat()}..{last.isoformat()}", starts_at=starts_at, ends_at=ends_at, label=label))
    return closures


def _ifood_datetime(value: datetime, tz) -> str:
    return timezone.localtime(value, timezone=tz).isoformat(timespec="seconds")


def _parse_remote_datetime(value, tz) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if timezone.is_naive(parsed):
        parsed = parsed.replace(tzinfo=tz)
    return parsed


def _find_remote(remote: list[dict], *, starts_at: datetime, ends_at: datetime, tz) -> dict | None:
    """A interrupção do iFood com o mesmo intervalo — é assim que um POST repetido
    (resposta perdida, retry da Directive) adota a interrupção já criada em vez de
    tomar 409 da própria pausa."""
    for item in remote:
        start = _parse_remote_datetime(item.get("start"), tz)
        end = _parse_remote_datetime(item.get("end"), tz)
        if start and end and abs(start - starts_at) <= _MATCH_TOLERANCE and abs(end - ends_at) <= _MATCH_TOLERANCE:
            return item
    return None


def _effective_start(starts_at: datetime, now: datetime) -> datetime:
    """Um intervalo que já começou é pedido a partir do próximo minuto."""
    if starts_at > now:
        return starts_at
    return (now + timedelta(minutes=1)).replace(second=0, microsecond=0)


# ── 1. Horário e calendário → iFood ───────────────────────────────────────────


@dataclass
class SyncResult:
    skipped: str = ""
    hours_written: bool = False
    created: int = 0
    removed: int = 0
    failed: int = 0


def enqueue_sync(reason: str) -> None:
    """Pede uma gravação de horário + calendário. Uma viva por vez (dedupe)."""
    if not enabled():
        return
    from shopman.shop.directives import IFOOD_MERCHANT_SYNC, create_deduped

    create_deduped(IFOOD_MERCHANT_SYNC, payload={"reason": reason}, dedupe_key=IFOOD_MERCHANT_SYNC)


def sync_store(*, now: datetime | None = None) -> SyncResult:
    """Grava no iFood a grade semanal e os fechamentos do calendário.

    Levanta :class:`MerchantAPIError` retryable para a Directive repetir. O que o
    iFood recusa de vez (409, 400) fica na interrupção como ``failed`` e vira
    alerta — repetir não resolveria.
    """
    from shopman.shop.models import Shop

    if not enabled():
        return SyncResult(skipped="desligado")
    shop = Shop.load()
    if not governs(shop):
        logger.info("ifood_merchant.sync: loja sem grade semanal — o Portal segue mandando no horário")
        return SyncResult(skipped="sem grade semanal")
    now = now or timezone.now()
    result = SyncResult()

    desired = desired_shifts(shop)
    if not shifts_match(desired, get_opening_hours()):
        put_opening_hours(desired)
        result.hours_written = True
        logger.info("ifood_merchant.sync: horário gravado no iFood (%s turnos)", len(desired))

    _reconcile_calendar(shop, now, result)
    _status_row(update={"synced_at": now})
    return result


def _reconcile_calendar(shop, now: datetime, result: SyncResult) -> None:
    from shopman.shop.models import IFoodInterruption, IFoodInterruptionKind
    from shopman.shop.models import IFoodInterruptionState as S

    tz = business_calendar.shop_timezone(shop=shop)
    mid = merchant_id()
    desired = {closure.key: closure for closure in desired_calendar_closures(now=now, shop=shop)}
    remote = list_interruptions()
    remote_ids = {str(item.get("id")) for item in remote if item.get("id")}

    live = IFoodInterruption.objects.filter(
        kind=IFoodInterruptionKind.CALENDAR,
        merchant_id=mid,
        state__in=(S.PENDING_CREATE, S.ACTIVE, S.PENDING_REMOVE),
    )
    for record in live:
        if record.ends_at <= now:
            record.state = S.REMOVED
            record.save(update_fields=["state", "updated_at"])
            continue
        closure = desired.get(record.calendar_key)
        if closure is None or closure.ends_at != record.ends_at:
            # O dia deixou de ser fechado (ou a grade mudou): a interrupção sai.
            if record.ifood_id and record.ifood_id in remote_ids:
                delete_interruption(record.ifood_id)
            record.state = S.REMOVED
            record.removed_at = now
            record.save(update_fields=["state", "removed_at", "updated_at"])
            result.removed += 1
            continue
        if record.state == S.ACTIVE and record.ifood_id in remote_ids:
            desired.pop(record.calendar_key)
            continue
        # Pendente, ou apagada no Portal: a casa continua fechada, então recria.
        desired.pop(record.calendar_key)
        _create_remote(record, remote=remote, now=now, tz=tz, result=result)

    for closure in desired.values():
        record = IFoodInterruption.objects.create(
            kind=IFoodInterruptionKind.CALENDAR,
            merchant_id=mid,
            description=closure.description,
            starts_at=closure.starts_at,
            ends_at=closure.ends_at,
            calendar_key=closure.key,
        )
        _create_remote(record, remote=remote, now=now, tz=tz, result=result)


def _create_remote(record, *, remote: list[dict], now: datetime, tz, result: SyncResult | None = None) -> None:
    """Cria no iFood a interrupção de ``record`` (adotando a que já exista igual)."""
    from shopman.shop.models import IFoodInterruptionState as S

    starts_at = _effective_start(record.starts_at, now)
    existing = _find_remote(remote, starts_at=record.starts_at, ends_at=record.ends_at, tz=tz) or _find_remote(
        remote, starts_at=starts_at, ends_at=record.ends_at, tz=tz
    )
    try:
        created = existing or create_interruption(
            starts_at=starts_at, ends_at=record.ends_at, description=record.description, tz=tz
        )
    except MerchantAPIError as exc:
        if exc.retryable:
            raise
        record.state = S.FAILED
        record.last_error = _refusal_copy(exc)
        record.save(update_fields=["state", "last_error", "updated_at"])
        if result is not None:
            result.failed += 1
        _alert_sync_failed(record, exc)
        return
    record.ifood_id = str(created.get("id") or "")
    record.state = S.ACTIVE
    record.last_error = ""
    record.save(update_fields=["ifood_id", "state", "last_error", "updated_at"])
    if result is not None:
        result.created += 1


def _refusal_copy(exc: MerchantAPIError) -> str:
    if isinstance(exc, InterruptionOverlap):
        return "O iFood recusou: já existe outra pausa no mesmo horário (criada no Portal do Parceiro?)."
    return f"O iFood recusou o pedido (HTTP {exc.status})."


def _alert_sync_failed(record, exc: MerchantAPIError) -> None:
    from shopman.shop.services.observability import create_operator_alert

    local_start = timezone.localtime(record.starts_at, timezone=business_calendar.shop_timezone())
    local_end = timezone.localtime(record.ends_at, timezone=business_calendar.shop_timezone())
    create_operator_alert(
        type=ALERT_SYNC_FAILED,
        severity="error",
        message=(
            f"{record.get_kind_display()}: a pausa de {local_start:%d/%m %H:%M} a {local_end:%d/%m %H:%M} "
            f"não foi gravada no iFood. {_refusal_copy(exc)}"
        ),
        dedupe_key=f"{ALERT_SYNC_FAILED}:{record.pk}",
        debounce_minutes=DIVERGENCE_ALERT_WINDOW_MINUTES,
        interruption_pk=record.pk,
        http_status=exc.status,
    )


# ── 2. Pausa do gestor ────────────────────────────────────────────────────────


class PauseRefused(Exception):
    """Pedido de pausa/retomada que a casa recusa, com a frase para o gestor."""


def live_manual_pause(*, now: datetime | None = None):
    """A pausa do gestor em curso (pedida, em vigor ou sendo retomada), ou None."""
    from shopman.shop.models import IFoodInterruption, IFoodInterruptionKind
    from shopman.shop.models import IFoodInterruptionState as S

    now = now or timezone.now()
    return (
        IFoodInterruption.objects.filter(
            kind=IFoodInterruptionKind.MANUAL,
            merchant_id=merchant_id(),
            state__in=(S.PENDING_CREATE, S.ACTIVE, S.PENDING_REMOVE),
            ends_at__gt=now,
        )
        .select_related("requested_by", "removed_by")
        .order_by("-requested_at")
        .first()
    )


def last_manual_pause():
    """A última pausa do gestor, viva ou não — para a tela contar o desfecho."""
    from shopman.shop.models import IFoodInterruption, IFoodInterruptionKind

    return (
        IFoodInterruption.objects.filter(kind=IFoodInterruptionKind.MANUAL, merchant_id=merchant_id())
        .select_related("requested_by", "removed_by")
        .order_by("-requested_at")
        .first()
    )


def pause_end_for(duration: str, *, now: datetime, state) -> datetime | None:
    """O fim da pausa para ``duration``; None quando a opção não serve agora."""
    if duration in PAUSE_DURATIONS:
        return now + timedelta(minutes=PAUSE_DURATIONS[duration])
    if duration == PAUSE_UNTIL_CLOSE and state.is_open and state.closes_at and state.resolved_at:
        closes = time.fromisoformat(state.closes_at)
        end = datetime.combine(state.resolved_at.date(), closes, tzinfo=state.resolved_at.tzinfo)
        return end if end > now else None
    return None


def request_pause(*, duration: str, reason: str, user, now: datetime | None = None):
    """Registra a pausa e pede ao iFood (Directive). Devolve a interrupção."""
    from shopman.shop.models import IFoodInterruption, IFoodInterruptionKind, Shop

    if not enabled():
        raise PauseRefused("A integração da loja com o iFood está desligada.")
    reason = " ".join(str(reason or "").split())
    if not reason:
        raise PauseRefused("Escreva o motivo da pausa.")
    now = now or timezone.now()
    state = business_calendar.current_business_state(now=now)
    if not state.is_open:
        raise PauseRefused("A loja já está fechada agora, e o iFood fecha junto. Não há o que pausar.")
    ends_at = pause_end_for(duration, now=now, state=state)
    if ends_at is None:
        raise PauseRefused("Escolha por quanto tempo pausar.")

    with transaction.atomic():
        # Uma pausa por vez: o iFood recusaria a segunda (409), e duas linhas vivas
        # deixariam a tela sem saber qual retomar.
        Shop.objects.select_for_update().first()
        if live_manual_pause(now=now) is not None:
            raise PauseRefused("O iFood já está pausado. Retome antes de pausar de novo.")
        record = IFoodInterruption.objects.create(
            kind=IFoodInterruptionKind.MANUAL,
            merchant_id=merchant_id(),
            description=f"Pausa pelo gestor: {reason}"[:255],
            reason=reason[:255],
            starts_at=now,
            ends_at=ends_at,
            requested_by=user if getattr(user, "pk", None) else None,
        )
        _enqueue_interruption(record)
    _log_manual("ifood_merchant.pause_requested", record, user)
    return record


def request_resume(*, user, now: datetime | None = None):
    """Pede ao iFood a retirada da pausa do gestor. Devolve a interrupção."""
    from shopman.shop.models import IFoodInterruption
    from shopman.shop.models import IFoodInterruptionState as S

    if not enabled():
        raise PauseRefused("A integração da loja com o iFood está desligada.")
    now = now or timezone.now()
    with transaction.atomic():
        current = live_manual_pause(now=now)
        if current is None:
            raise PauseRefused("O iFood não está pausado pelo gestor.")
        record = IFoodInterruption.objects.select_for_update().get(pk=current.pk)
        if record.state != S.PENDING_REMOVE:
            record.state = S.PENDING_REMOVE
            record.removed_by = user if getattr(user, "pk", None) else None
            record.removed_at = now
            record.save(update_fields=["state", "removed_by", "removed_at", "updated_at"])
            _enqueue_interruption(record)
    _log_manual("ifood_merchant.resume_requested", record, user)
    return record


def _enqueue_interruption(record) -> None:
    from shopman.shop.directives import IFOOD_MERCHANT_INTERRUPTION, create_deduped

    create_deduped(
        IFOOD_MERCHANT_INTERRUPTION,
        payload={"interruption_pk": record.pk, "state": record.state},
        dedupe_key=f"{IFOOD_MERCHANT_INTERRUPTION}:{record.pk}:{record.state}",
    )


def _log_manual(event: str, record, user) -> None:
    from shopman.shop.services.observability import operational_event

    operational_event(
        event,
        interruption_pk=record.pk,
        state=record.state,
        ends_at=record.ends_at.isoformat(),
        actor=getattr(user, "username", "") or "",
    )


def apply_interruption(interruption_pk: int, *, now: datetime | None = None) -> None:
    """Leva ao iFood o estado pedido da interrupção (criar ou retirar).

    Roda com a linha travada: uma retomada pedida no meio da criação espera a
    criação terminar e só então é vista — sem isso, o POST que terminasse depois
    marcaria "em vigor" uma pausa que o gestor já tinha retomado.
    """
    from shopman.shop.models import IFoodInterruption
    from shopman.shop.models import IFoodInterruptionState as S

    now = now or timezone.now()
    tz = business_calendar.shop_timezone()
    with transaction.atomic():
        record = IFoodInterruption.objects.select_for_update().filter(pk=interruption_pk).first()
        if record is None:
            return
        if record.state == S.PENDING_CREATE:
            if record.ends_at <= now:
                record.state = S.REMOVED
                record.save(update_fields=["state", "updated_at"])
                return
            _create_remote(record, remote=list_interruptions(), now=now, tz=tz)
        elif record.state == S.PENDING_REMOVE:
            remote_id = record.ifood_id
            if not remote_id:
                # A retomada chegou antes de a criação ter resposta: se o iFood
                # já tem a pausa, ela é achada pelo intervalo e apagada.
                found = _find_remote(list_interruptions(), starts_at=record.starts_at, ends_at=record.ends_at, tz=tz)
                remote_id = str((found or {}).get("id") or "")
            if remote_id:
                delete_interruption(remote_id)
            record.state = S.REMOVED
            record.save(update_fields=["state", "updated_at"])


# ── 3. Conferência ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StoreCheck:
    available: bool
    expected_available: bool
    state: str
    problems: list
    alerted: str = ""


def _status_row(*, update: dict):
    from shopman.shop.models import IFoodStoreStatus

    row, _ = IFoodStoreStatus.objects.get_or_create(merchant_id=merchant_id())
    for key, value in update.items():
        setattr(row, key, value)
    row.save()
    return row


def summarize_status(operations: list[dict]) -> tuple[bool, str, list[dict]]:
    """``(recebe pedido?, pior estado, validações com problema)`` do ``GET /status``."""
    available = any(op.get("available") is True for op in operations)
    states = [str(op.get("state") or "").upper() for op in operations]
    worst = next((s for s in _STATE_SEVERITY if s in states), states[0] if states else "")
    problems: list[dict] = []
    seen: set[str] = set()
    for op in operations:
        for validation in op.get("validations") or []:
            if not isinstance(validation, dict):
                continue
            code = str(validation.get("code") or "")
            vstate = str(validation.get("state") or "").upper()
            if vstate == "OK" or not code or code in seen:
                continue
            seen.add(code)
            message = validation.get("message") if isinstance(validation.get("message"), dict) else {}
            problems.append({"code": code, "state": vstate, "title": str(message.get("title") or "")})
    return available, worst, problems


def expected_available(*, now: datetime | None = None) -> tuple[bool, str]:
    """O que a casa diz: ``(deveria receber pedido no iFood?, por quê não)``."""
    now = now or timezone.now()
    state = business_calendar.current_business_state(now=now)
    if not state.is_open:
        return False, state.message or "loja fechada"
    pause = live_manual_pause(now=now)
    if pause is not None and pause.starts_at <= now:
        return False, "pausa do gestor"
    return True, ""


def check_store(*, now: datetime | None = None) -> StoreCheck | None:
    """Lê o status do iFood, grava, e alerta quando ele diverge da casa.

    ``None`` quando desligado, sem grade semanal ou sem leitura (a falha fica em
    ``IFoodStoreStatus.last_error``; o log do ``ifood_http`` tem a forense).
    """
    from shopman.shop.models import Shop

    if not enabled():
        return None
    shop = Shop.load()
    if not governs(shop):
        return None
    now = now or timezone.now()
    try:
        operations = get_status()
    except MerchantAPIError as exc:
        _status_row(update={"last_error": str(exc)[:500]})
        logger.warning("ifood_merchant.check: status ilegível — %s", exc)
        return None

    available, worst, problems = summarize_status(operations)
    expected, why_closed = expected_available(now=now)
    row = _status_row(update={
        "checked_at": now,
        "available": available,
        "state": worst,
        "problems": problems,
        "expected_available": expected,
        "last_error": "",
    })

    alerted = ""
    if available == expected:
        if row.divergent_since is not None:
            row.divergent_since = None
            row.save(update_fields=["divergent_since"])
    elif row.divergent_since is None:
        row.divergent_since = now
        row.save(update_fields=["divergent_since"])
    elif now - row.divergent_since >= DIVERGENCE_GRACE:
        alerted = _alert_divergence(row, expected=expected, why_closed=why_closed, problems=problems)

    if (row.synced_at is None or now - row.synced_at >= RESYNC_EVERY) or alerted:
        # Horário mexido no Portal, horizonte do calendário andando, ou divergência:
        # regravar é barato (lê antes, só escreve o que difere).
        enqueue_sync("check")
    return StoreCheck(available=available, expected_available=expected, state=worst, problems=problems, alerted=alerted)


def problem_copy(problems: list[dict]) -> list[str]:
    """Frases de balcão para as validações do iFood que mais explicam um fechamento."""
    codes = {p.get("code") for p in problems}
    lines = []
    if "is-connected" in codes:
        lines.append("O iFood não está recebendo o polling da casa: confira se o ifood-poll-worker está no ar.")
    if "unavailabilities" in codes:
        lines.append("Há uma pausa em vigor no iFood (se não foi o gestor, foi feita no Portal do Parceiro).")
    if "opening-hours" in codes:
        lines.append("O horário gravado no iFood não cobre este instante.")
    others = [p.get("title") or p.get("code") for p in problems if p.get("code") not in {"is-connected", "unavailabilities", "opening-hours"}]
    if others:
        lines.append("O iFood também aponta: " + "; ".join(str(o) for o in others) + ".")
    return lines


def _alert_divergence(row, *, expected: bool, why_closed: str, problems: list[dict]) -> str:
    from shopman.shop.services.observability import create_operator_alert

    since = timezone.localtime(row.divergent_since, timezone=business_calendar.shop_timezone())
    context = {
        "debounce_minutes": DIVERGENCE_ALERT_WINDOW_MINUTES,
        "ifood_state": row.state,
        "problems": [p.get("code") for p in problems],
    }
    if expected:
        head = f"O iFood está fechado desde {since:%H:%M}, com a loja aberta: nenhum pedido do iFood entra."
        create_operator_alert(
            type=ALERT_CLOSED_WHILE_OPEN,
            severity="error",
            message=" ".join([head, *problem_copy(problems)]),
            dedupe_key=ALERT_CLOSED_WHILE_OPEN,
            **context,
        )
        return ALERT_CLOSED_WHILE_OPEN
    head = f"O iFood está recebendo pedidos desde {since:%H:%M}, com a loja fechada ({why_closed})."
    create_operator_alert(
        type=ALERT_OPEN_WHILE_CLOSED,
        severity="error",
        message=(
            f"{head} O Shopman vai regravar horário e pausas no iFood; "
            "se continuar, pause pelo Gestor de pedidos ou pelo Portal do Parceiro."
        ),
        dedupe_key=ALERT_OPEN_WHILE_CLOSED,
        **context,
    )
    return ALERT_OPEN_WHILE_CLOSED


__all__ = [
    "ALERT_CLOSED_WHILE_OPEN",
    "ALERT_OPEN_WHILE_CLOSED",
    "ALERT_SYNC_FAILED",
    "CalendarClosure",
    "InterruptionOverlap",
    "MerchantAPIError",
    "PAUSE_DURATIONS",
    "PAUSE_UNTIL_CLOSE",
    "PauseRefused",
    "StoreCheck",
    "SyncResult",
    "apply_interruption",
    "check_store",
    "desired_calendar_closures",
    "desired_shifts",
    "enabled",
    "enqueue_sync",
    "expected_available",
    "governs",
    "live_manual_pause",
    "merchant_id",
    "problem_copy",
    "request_pause",
    "request_resume",
    "summarize_status",
    "sync_store",
]
