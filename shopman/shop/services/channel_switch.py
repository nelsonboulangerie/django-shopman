"""Ligar e desligar um canal — o toggle "Ativo" do card na aba Canais do Gestor.

Vale para TODO canal, de venda (``commerce_policy=order``) ou de exibição
(``display``), e usa o mecanismo que o canal já tinha: ``Channel.is_active``.

Um gesto no toggle é uma JANELA: o estado pedido (ligado ou desligado), de quando
até quando, por quê, quem operou e quem autorizou. Sem fim ("sem prazo"), o
estado fica até alguém mexer de novo; com fim, o canal volta sozinho ao estado de
antes. Janela que começa no futuro é agendamento. A janela vive em
``Channel.config["activation"]`` (JSON do canal, sem migração); o histórico de
gestos vai para o ``LogEntry`` do Admin, no mesmo padrão da pausa em massa do
Catálogo.

**O estado vale na hora, não no ciclo do worker.** Quem decide (o commit, a TV, o
feed, o iFood) lê :func:`effective_active`, que resolve a janela pelo relógio; o
``maintenance_worker`` só carimba ``is_active`` depois (:func:`apply_due`), para
quem lê a coluna direto (colunas do Catálogo, envio de catálogo).

**O calendário da loja sempre prevalece no sentido de FECHAR.** O toggle de um
canal de venda só fecha mais: loja fechada pelo horário, feriado ou fechamento
pontual é canal fechado, ligado ou não. Por isso nenhuma opção de período oferece
"ligar" num instante em que a loja está fechada (:func:`period_options`), e o card
diz quando é o horário da loja que está fechando (:func:`closed_by_shop`). Canal de
exibição (TV, feed Google/Meta) não segue o horário: o feed é buscado de
madrugada, e a loja fechada à noite zeraria o catálogo inteiro na plataforma.

O que desligado significa, por tipo de canal:

* **PDV** — sem toggle: o balcão é a loja física, e parar de vender ali é fechar
  o caixa. Nenhum estado de canal recusa venda no balcão (:func:`is_switchable`).
* **Venda com checkout próprio** (loja online, WhatsApp) — o commit recusa
  (:func:`ensure_accepting_orders`, em ``sessions.commit_session``). A loja online
  avisa na home; o concierge do WhatsApp deixa de oferecer o pedido.
* **iFood** — fechado no iFood pelo período. Sem prazo, o iFood não tem
  interrupção sem fim (7 dias no máximo cada), então a conferência do
  maintenance-worker renova (:func:`off_windows` + ``ifood_merchant``).
* **Exibição** — a saída para de exibir produto: a TV mostra a tela preta, o feed
  sai com todos os itens fora de estoque.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

ACTIVATION_KEY = "activation"
IFOOD_CHANNEL_REF = "ifood"

PERIOD_30M = "30m"
PERIOD_1H = "1h"
PERIOD_TODAY = "today"
PERIOD_OPEN = "open"
PERIOD_CUSTOM = "custom"
PERIODS = (PERIOD_30M, PERIOD_1H, PERIOD_TODAY, PERIOD_OPEN, PERIOD_CUSTOM)
_PERIOD_MINUTES = {PERIOD_30M: 30, PERIOD_1H: 60}
#: Um período escolhido no calendário cabe em três meses. Mais que isso não é
#: período, é o canal desligado — e para isso existe "sem prazo".
MAX_CUSTOM_DAYS = 90
#: Âncora das janelas sem gesto registrado (canal desligado pelo Admin ou seed):
#: uma segunda-feira à meia-noite. Fixa, para que a mesma pergunta dê sempre os
#: mesmos blocos no iFood.
_ANCHOR = (2026, 1, 5)

#: Motivos recorrentes por tipo de canal — só os que fazem sentido naquele canal.
#: "Sem entregador" só existe onde a casa entrega (no iFood quem entrega é o iFood).
_REASONS_REMOTE = ("Loja cheia", "Desfalque na equipe", "Falta de produto", "Sem entregador", "Feriado", "Férias")
_REASONS_IFOOD = ("Loja cheia", "Desfalque na equipe", "Falta de produto", "Feriado", "Férias")
_REASONS_DISPLAY = ("Falta de produto", "Feriado", "Férias")


class ChannelSwitchError(Exception):
    """Pedido de ligar/desligar que não pode ser atendido, com a frase para a tela."""


class ChannelSwitchConflict(ChannelSwitchError):
    """O canal mudou depois que a tela o leu."""


@dataclass(frozen=True)
class Activation:
    """A janela do último gesto no toggle (``config["activation"]``)."""

    is_active: bool  # o estado pedido durante a janela
    before: bool  # o estado de antes — para onde o canal volta no fim
    starts_at: datetime
    ends_at: datetime | None  # None = sem prazo
    at: datetime | None  # quando o gesto foi feito
    by: str
    approved_by: str
    reason: str
    auto: bool = False  # carimbo do fim do período, não gesto de gente


@dataclass(frozen=True)
class PeriodOption:
    key: str
    label: str
    enabled: bool
    reason: str = ""


# ── Leitura ───────────────────────────────────────────────────────────────────


def _parse(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def activation(channel) -> Activation | None:
    raw = (channel.config or {}).get(ACTIVATION_KEY)
    if not isinstance(raw, dict):
        return None
    starts_at = _parse(raw.get("starts_at")) or _parse(raw.get("at"))
    if starts_at is None:
        return None
    target = bool(raw.get("is_active", channel.is_active))
    return Activation(
        is_active=target,
        before=bool(raw.get("before", not target)),
        starts_at=starts_at,
        ends_at=_parse(raw.get("ends_at")),
        at=_parse(raw.get("at")),
        by=str(raw.get("by") or ""),
        approved_by=str(raw.get("approved_by") or ""),
        reason=str(raw.get("reason") or ""),
        auto=bool(raw.get("auto")),
    )


def effective_active(channel, *, now: datetime | None = None) -> bool:
    """O toggle AGORA, resolvendo a janela pelo relógio (não pelo carimbo do worker)."""
    record = activation(channel)
    if record is None:
        return bool(channel.is_active)
    now = now or timezone.now()
    if now < record.starts_at:
        return bool(channel.is_active)
    if record.ends_at is not None and now >= record.ends_at:
        return record.before
    return record.is_active


def governed_by_calendar(channel) -> bool:
    """Canal de venda segue o horário da loja; canal de exibição, não."""
    from shopman.shop.models import Channel

    return channel.commerce_policy == Channel.CommercePolicy.ORDER


def closed_by_shop(channel, *, state=None, now: datetime | None = None) -> str:
    """A frase de quando é a LOJA que fecha o canal (ligado, mas loja fechada)."""
    if not governed_by_calendar(channel) or not effective_active(channel, now=now):
        return ""
    from shopman.shop.services import business_calendar

    state = state or business_calendar.current_business_state(now=now)
    if state.is_open:
        return ""
    if state.closed_reason:
        return f"Fechado pelo calendário da loja: {state.closed_reason}"
    return "Fechado pelo horário da loja"


def is_switchable(channel) -> bool:
    """O canal tem o toggle? Todos, menos o PDV.

    Decisão do dono (22/09/2026): o balcão É a loja física. Parar de vender no
    balcão é fechar o caixa (o turno), não desligar um canal — então o PDV não tem
    toggle, e nenhum estado de canal recusa venda no balcão.
    """
    return channel.ref != pos_channel_ref()


def pos_channel_ref() -> str:
    return getattr(settings, "SHOPMAN_POS_CHANNEL_REF", "pdv")


def ensure_accepting_orders(channel_ref: str, *, now: datetime | None = None) -> None:
    """Recusa o commit num canal de venda desligado.

    É a trava de verdade: a home da loja online e o concierge avisam antes, mas
    um POST direto, uma aba antiga ou o PDV aberto chegam aqui.
    """
    from shopman.orderman.exceptions import ValidationError

    from shopman.shop.models import Channel

    if channel_ref == pos_channel_ref():
        return  # o balcão nunca recusa venda por estado de canal (ver is_switchable)
    channel = Channel.objects.filter(ref=channel_ref).only("ref", "name", "is_active", "config").first()
    if channel is None or effective_active(channel, now=now):
        return
    name = channel.name or channel.ref
    raise ValidationError(
        code="channel_off",
        message=f"{name} não está recebendo pedidos agora.",
        context={"channel_ref": channel.ref},
    )


def is_channel_active(channel_ref: str, *, now: datetime | None = None) -> bool:
    from shopman.shop.models import Channel

    channel = Channel.objects.filter(ref=channel_ref).only("ref", "is_active", "config").first()
    return channel is not None and effective_active(channel, now=now)


def revision(channel) -> str:
    """A revisão do toggle — muda com o estado E com a janela (agendamento incluso)."""
    from shopman.shop.services.remote_mutations import mutation_fingerprint

    return mutation_fingerprint({
        "version": 2, "ref": channel.ref, "field": "switch", "active": bool(channel.is_active),
        "activation": (channel.config or {}).get(ACTIVATION_KEY) or {},
    })


def reason_presets(channel, *, target: bool) -> tuple[str, ...]:
    """Motivos recorrentes para DESLIGAR. Ligar não tem motivo de prateleira."""
    if target:
        return ()
    from shopman.shop.models import Channel

    if channel.commerce_policy == Channel.CommercePolicy.DISPLAY:
        return _REASONS_DISPLAY
    if channel.ref == IFOOD_CHANNEL_REF:
        return _REASONS_IFOOD
    return _REASONS_REMOTE


# ── Frases ────────────────────────────────────────────────────────────────────

_WEEKDAY_ABBR_PT = ("seg.", "ter.", "qua.", "qui.", "sex.", "sáb.", "dom.")


def _hour(value: time) -> str:
    return f"{value.hour}h{value.minute:02d}" if value.minute else f"{value.hour}h"


def moment(value: datetime | None, *, now: datetime | None = None) -> str:
    """"hoje às 10h30", "amanhã às 7h", "ontem às 18h", "sáb. 20/12 às 0h"."""
    if value is None:
        return ""
    now = now or timezone.now()
    local = timezone.localtime(value)
    today = timezone.localtime(now).date()
    hour = _hour(local.time())
    if local.date() == today:
        return f"hoje às {hour}"
    if local.date() == today + timedelta(days=1):
        return f"amanhã às {hour}"
    if local.date() == today - timedelta(days=1):
        return f"ontem às {hour}"
    return f"{_WEEKDAY_ABBR_PT[local.weekday()]} {local.day}/{local.month} às {hour}"


def _signed(record: Activation) -> str:
    who = f" por {record.by}" if record.by else ""
    if record.approved_by and record.approved_by != record.by:
        who += f" (autorizado por {record.approved_by})"
    return who


def state_line(channel, *, now: datetime | None = None) -> str:
    """Uma frase: o estado do toggle agora, de quem, por quê e até quando."""
    now = now or timezone.now()
    record = activation(channel)
    active = effective_active(channel, now=now)
    if record is None:
        return "" if active else "Desligado."
    if now < record.starts_at:
        # Agendamento: o estado de agora não é o do gesto — o gesto vem depois, e
        # quem conta dele é ``scheduled_line``. Ligado é o estado normal: nada a dizer.
        return "" if active else "Desligado."
    ended = record.ends_at is not None and now >= record.ends_at
    if ended or record.auto:
        when = record.ends_at if ended else record.starts_at
        verb = "Religado" if active else "Desligado de novo"
        return f"{verb} {moment(when, now=now)}, no fim do período."
    verb = "Ligado" if record.is_active else "Desligado"
    line = f"{verb}{_signed(record)} {moment(record.at or record.starts_at, now=now)}"
    if record.reason:
        line += f": {record.reason}"
    if record.ends_at is None:
        tail = "Sem prazo: fica assim até alguém religar." if not record.is_active else ""
    else:
        back = "Volta a ligar" if not record.is_active else "Desliga de novo"
        tail = f"{back} {moment(record.ends_at, now=now)}."
    return f"{line}. {tail}".strip()


def scheduled_line(channel, *, now: datetime | None = None) -> str:
    """O agendamento ainda por vir, ou vazio."""
    now = now or timezone.now()
    record = activation(channel)
    if record is None or now >= record.starts_at:
        return ""
    verb = "Liga" if record.is_active else "Desliga"
    line = f"{verb} {moment(record.starts_at, now=now)}"
    if record.ends_at is not None:
        line += f" até {moment(record.ends_at, now=now)}"
    line += f" (agendado{_signed(record)})"
    if record.reason:
        line += f": {record.reason}"
    return f"{line}."


# ── Períodos ──────────────────────────────────────────────────────────────────


def _today_end(now: datetime, state) -> tuple[datetime, str]:
    """O fim de "por hoje": o fechamento de hoje, se ainda vem; senão a meia-noite."""
    local = timezone.localtime(now)
    if state is not None and state.closes_at and state.closure_source != "after_close":
        closes = time.fromisoformat(state.closes_at)
        end = datetime.combine(local.date(), closes, tzinfo=local.tzinfo)
        if end > now:
            return end, f"até as {_hour(closes)}"
    midnight = datetime.combine(local.date() + timedelta(days=1), time.min, tzinfo=local.tzinfo)
    return midnight, "até a meia-noite"


def period_options(channel, *, target: bool, now: datetime | None = None, state=None) -> tuple[PeriodOption, ...]:
    """As opções de período do modal para levar o toggle a ``target``.

    Ligar um canal de venda com a loja fechada não abre nada: o horário da loja
    prevalece. As opções curtas somem da escolha (desabilitadas, com o porquê), e
    "por hoje" só vale se a loja ainda abre hoje.
    """
    from shopman.shop.services import business_calendar

    now = now or timezone.now()
    governed = governed_by_calendar(channel)
    if governed and state is None:
        state = business_calendar.current_business_state(now=now)
    shop_closed = bool(governed and state is not None and state.is_closed)
    closed_reason = "A loja está fechada agora; o canal só abre junto com ela." if (target and shop_closed) else ""

    end_today, today_tail = _today_end(now, state if governed else None)
    today_ok = True
    today_label = f"Por hoje ({today_tail})"
    if target and shop_closed:
        opens_later_today = state.closure_source == "before_open" and state.opens_at and state.closes_at
        today_ok = bool(opens_later_today)
        if today_ok:
            opens = time.fromisoformat(state.opens_at)
            closes = time.fromisoformat(state.closes_at)
            today_label = f"Por hoje (das {_hour(opens)} às {_hour(closes)})"

    return (
        PeriodOption(PERIOD_30M, "Por 30 minutos", not closed_reason, closed_reason),
        PeriodOption(PERIOD_1H, "Por 1 hora", not closed_reason, closed_reason),
        PeriodOption(PERIOD_TODAY, today_label, today_ok, "" if today_ok else "A loja não abre mais hoje."),
        PeriodOption(
            PERIOD_OPEN,
            "Sem prazo (até alguém desligar)" if target else "Sem prazo (até alguém religar)",
            True,
        ),
        PeriodOption(PERIOD_CUSTOM, "Escolher período…", True),
    )


def resolve_period(
    channel,
    *,
    target: bool,
    period: str,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    now: datetime | None = None,
) -> tuple[datetime, datetime | None]:
    """``(início, fim)`` da janela; fim ``None`` = sem prazo."""
    from shopman.shop.services import business_calendar

    now = now or timezone.now()
    if period not in PERIODS:
        raise ChannelSwitchError("Escolha por quanto tempo.")
    state = business_calendar.current_business_state(now=now) if governed_by_calendar(channel) else None
    options = {option.key: option for option in period_options(channel, target=target, now=now, state=state)}
    option = options[period]
    if not option.enabled:
        raise ChannelSwitchError(option.reason or "Esta opção não vale agora.")
    if period in _PERIOD_MINUTES:
        return now, now + timedelta(minutes=_PERIOD_MINUTES[period])
    if period == PERIOD_TODAY:
        return now, _today_end(now, state)[0]
    if period == PERIOD_OPEN:
        return now, None
    if starts_at is None or ends_at is None:
        raise ChannelSwitchError("Escolha o início e o fim do período.")
    starts_at = max(starts_at, now)
    if ends_at <= starts_at:
        raise ChannelSwitchError("O fim do período precisa vir depois do início.")
    if ends_at - starts_at > timedelta(days=MAX_CUSTOM_DAYS):
        raise ChannelSwitchError(f"O período cabe em até {MAX_CUSTOM_DAYS} dias. Para mais, use \"sem prazo\".")
    return starts_at, ends_at


# ── Gesto ─────────────────────────────────────────────────────────────────────


def _who(user) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or user.get_username() or "").strip()


@transaction.atomic
def request_switch(
    ref: str,
    is_active: bool,
    *,
    period: str,
    actor,
    approved_by=None,
    reason: str = "",
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    expected_revision: str | None = None,
    now: datetime | None = None,
) -> Activation:
    """Registra a janela pedida no toggle e a aplica se ela já começou.

    ``actor`` é quem operou; ``approved_by`` é o gerente que autorizou (o próprio
    ``actor`` quando ele é gerente). A autorização é conferida por quem chama (a
    API); aqui ela é registrada.
    """
    from shopman.shop.models import Channel

    now = now or timezone.now()
    channel = Channel.objects.select_for_update().filter(ref=ref).first()
    if channel is None:
        raise ChannelSwitchError(f"Canal '{ref}' não encontrado.")
    if not is_switchable(channel):
        raise ChannelSwitchError("O PDV não se desliga por aqui: parar de vender no balcão é fechar o caixa.")
    if expected_revision is not None and revision(channel) != expected_revision:
        raise ChannelSwitchConflict("Este canal mudou. Confira o estado atual antes de ligar ou desligar.")
    reason = " ".join(str(reason or "").split())[:200]
    if not is_active and not reason:
        raise ChannelSwitchError("Escolha ou escreva o motivo.")
    start, end = resolve_period(channel, target=is_active, period=period, starts_at=starts_at, ends_at=ends_at, now=now)
    current = effective_active(channel, now=now)
    if start <= now and current == is_active and end is None:
        raise ChannelSwitchError("O canal já está assim.")

    record = {
        "is_active": is_active,
        "before": current,
        "starts_at": start.isoformat(),
        "ends_at": end.isoformat() if end else None,
        "at": now.isoformat(),
        "by": _who(actor),
        "approved_by": _who(approved_by),
        "reason": reason,
    }
    channel.config = {**(channel.config or {}), ACTIVATION_KEY: record}
    changed = False
    if start <= now and channel.is_active != is_active:
        channel.is_active = is_active
        changed = True
    elif channel.is_active != current:
        # Carimbo atrasado de janela anterior (o worker não passou): acerta junto.
        channel.is_active = current
        changed = True
    channel.save(update_fields=["is_active", "config"])
    _audit(channel, record, actor=actor, approved_by=approved_by, period=period)
    _apply_effects(channel, is_active=channel.is_active, changed=changed, actor=actor)
    current_record = activation(channel)
    _notify_change(channel, current_record, scheduled=start > now, now=now)
    return current_record


def apply_due(*, now: datetime | None = None) -> int:
    """Carimba em ``is_active`` o que as janelas já decidiram. Devolve quantos mudaram.

    Roda no ``maintenance_worker``. Quem decide na hora não depende disto (lê
    :func:`effective_active`); isto serve a quem lê a coluna, e é o que dispara os
    efeitos (reenvio de catálogo ao religar, sinal da TV, sincronização do iFood).
    """
    from shopman.shop.models import Channel

    now = now or timezone.now()
    changed = 0
    for pk in Channel.objects.filter(config__has_key=ACTIVATION_KEY).values_list("pk", flat=True):
        with transaction.atomic():
            channel = Channel.objects.select_for_update().get(pk=pk)
            record = activation(channel)
            if record is None or now < record.starts_at:
                continue
            ended = record.ends_at is not None and now >= record.ends_at
            target = record.before if ended else record.is_active
            config = dict(channel.config or {})
            if ended and not record.auto:
                # O fim do período vira o novo "gesto": o card conta que foi o
                # relógio, e a janela não é reaplicada.
                config[ACTIVATION_KEY] = {
                    "is_active": target, "before": target, "starts_at": record.ends_at.isoformat(),
                    "ends_at": None, "at": record.ends_at.isoformat(), "by": "", "approved_by": "",
                    "reason": "", "auto": True,
                }
            if channel.is_active == target and config == (channel.config or {}):
                continue
            state_changed = channel.is_active != target
            channel.is_active = target
            channel.config = config
            channel.save(update_fields=["is_active", "config"])
            if state_changed:
                changed += 1
                operational_event = "channel.switched_on" if target else "channel.switched_off"
                from shopman.shop.services.observability import operational_event_on_commit

                operational_event_on_commit(operational_event, channel_ref=channel.ref, actor="", reason="fim do período")
            _apply_effects(channel, is_active=target, changed=state_changed, actor=None)
            if state_changed:
                _notify_change(channel, activation(channel) if not ended else None, ended=ended,
                               ended_at=record.ends_at, now=now)
    return changed


def _audit(channel, record: dict, *, actor, approved_by, period: str) -> None:
    from django.contrib.admin.models import CHANGE, LogEntry

    from shopman.shop.services.observability import operational_event_on_commit

    payload = {
        "action": "channel.switch",
        "channel_ref": channel.ref,
        "is_active": record["is_active"],
        "period": period,
        "starts_at": record["starts_at"],
        "ends_at": record["ends_at"],
        "reason": record["reason"],
        "approved_by": getattr(approved_by, "username", "") or "",
    }
    if getattr(actor, "pk", None):
        LogEntry.objects.log_actions(
            user_id=actor.pk,
            queryset=[channel],
            action_flag=CHANGE,
            change_message=json.dumps(payload, ensure_ascii=False),
        )
    operational_event_on_commit(
        "channel.switch_requested",
        **{key: value for key, value in payload.items() if key != "action"},
        actor=getattr(actor, "username", "") or "",
    )


def _apply_effects(channel, *, is_active: bool, changed: bool, actor) -> None:
    from shopman.shop.handlers._sse_emitters import emit_surface_changed

    # Board do Gestor, colunas do Catálogo e a TV relêem.
    emit_surface_changed(channel.ref)
    if channel.ref == IFOOD_CHANNEL_REF:
        # Janela nova ou fim de janela: o iFood precisa das interrupções certas,
        # inclusive as agendadas (o iFood aceita interrupção com início futuro).
        from shopman.shop.services import ifood_merchant

        ifood_merchant.enqueue_sync("channel_switch")
    if changed and is_active:
        _resync_projection(channel.ref)


def _notify_change(channel, record: Activation | None, *, scheduled: bool = False, ended: bool = False,
                   ended_at: datetime | None = None, now: datetime) -> None:
    """Notificação comum (sino) na MUDANÇA de estado — o histórico de quem mexeu.

    Vai para quem gerencia pedidos (``shop.manage_orders``, a régua do Gestor, onde
    o sino mora), no mesmo formato das outras notificações informativas da casa.
    Sem ação e sem link: a notificação conta o que aconteceu; o controle está na
    aba Canais. Falhar aqui vira log, nunca desfaz o gesto.
    """
    title, message = notification_copy(channel, record, scheduled=scheduled, ended=ended, ended_at=ended_at, now=now)
    if not title:
        return

    def _send() -> None:
        try:
            from django.contrib.auth import get_user_model

            from shopman.shop.models import NotificationCategory, UserNotification
            from shopman.shop.services.user_notifications import push_user_notification

            recipients = get_user_model().objects.with_perm(
                "shop.manage_orders", is_active=True, backend="django.contrib.auth.backends.ModelBackend",
            )
            for user in recipients:
                notification = UserNotification.objects.create(
                    user=user, category=NotificationCategory.SYSTEM, title=title, message=message,
                )
                push_user_notification(notification, enqueue_web_push=False)
        except Exception:
            logger.exception("channel_switch.notify_failed channel=%s", channel.ref)

    transaction.on_commit(_send, robust=True)


def notification_copy(channel, record: Activation | None, *, scheduled: bool = False, ended: bool = False,
                      ended_at: datetime | None = None, now: datetime | None = None) -> tuple[str, str]:
    """``(título, mensagem)`` da notificação de mudança. Título diz o que mudou e em qual canal."""
    now = now or timezone.now()
    name = channel.name or channel.ref
    if ended:
        verb = "religado" if channel.is_active else "desligado de novo"
        return f"Canal {verb}: {name}", f"Fim do período ({moment(ended_at, now=now)})."
    if record is None:
        return "", ""
    who = f"Por {record.by}" if record.by else "Pelo Gestor"
    if record.approved_by and record.approved_by != record.by:
        who += f", autorizado por {record.approved_by}"
    reason = f": {record.reason}" if record.reason else ""
    if scheduled:
        verb = "Liga" if record.is_active else "Desliga"
        span = f"{verb} {moment(record.starts_at, now=now)}"
        if record.ends_at:
            span += f" até {moment(record.ends_at, now=now)}"
        kind = "Religação agendada" if record.is_active else "Desligamento agendado"
        return f"{kind}: {name}", f"{span}. {who}{reason}."
    if record.auto:
        return f"Canal {'ligado' if record.is_active else 'desligado'}: {name}", "Início do período agendado."
    title = f"Canal {'ligado' if record.is_active else 'desligado'}: {name}"
    if record.ends_at is None:
        tail = "" if record.is_active else " Sem prazo: fica assim até alguém religar."
    else:
        back = "Desliga de novo" if record.is_active else "Volta a ligar"
        tail = f" {back} {moment(record.ends_at, now=now)}."
    return title, f"{who}{reason}.{tail}"


def _resync_projection(ref: str) -> None:
    """Religar um canal com catálogo externo reenvia o catálogo inteiro.

    Enquanto desligado, a projeção para esse canal é descartada
    (``catalog_projection._channel_or_feed_active``): o que mudou no meio não
    chegou lá, e religar sem reenviar reabriria a loja com preço velho.
    """
    from shopman.offerman.conf import get_projection_backend_channels

    if ref not in set(get_projection_backend_channels()):
        return
    from shopman.offerman.models import ListingItem

    from shopman.shop.handlers.catalog_projection import enqueue_project

    skus = (
        ListingItem.objects.filter(listing__ref=ref)
        .values_list("product__sku", flat=True)
        .distinct()
    )
    for sku in skus:
        enqueue_project(sku, ref, trigger="channel_on")


# ── Janelas de fechamento (iFood) ─────────────────────────────────────────────


def off_windows(channel, *, now: datetime | None = None) -> list[tuple[datetime, datetime | None]]:
    """Os intervalos em que o toggle deixa o canal DESLIGADO, de agora em diante.

    ``(início, fim)``, fim ``None`` = sem prazo. Os inícios são os do gesto (não
    "agora"), para que a mesma pergunta dê sempre os mesmos blocos: é assim que a
    reconciliação do iFood reconhece o que já pediu.
    """
    now = now or timezone.now()
    tz = timezone.get_current_timezone()
    anchor = datetime(*_ANCHOR, tzinfo=tz)
    record = activation(channel)
    if record is None:
        return [] if channel.is_active else [(anchor, None)]
    segments: list[tuple[datetime, datetime | None, bool]] = []
    # Antes da janela vale o estado que o canal tinha no gesto.
    previous_start = anchor
    if record.auto:
        previous_start = record.starts_at
    segments.append((previous_start, record.starts_at, record.before))
    segments.append((record.starts_at, record.ends_at, record.is_active))
    if record.ends_at is not None:
        segments.append((record.ends_at, None, record.before))
    windows = []
    for start, end, active in segments:
        if active or (end is not None and end <= now) or (end is not None and end <= start):
            continue
        if windows and windows[-1][1] == start:
            windows[-1] = (windows[-1][0], end)
        else:
            windows.append((start, end))
    return windows


__all__ = [
    "ACTIVATION_KEY",
    "Activation",
    "ChannelSwitchConflict",
    "ChannelSwitchError",
    "MAX_CUSTOM_DAYS",
    "PERIODS",
    "PeriodOption",
    "activation",
    "apply_due",
    "closed_by_shop",
    "effective_active",
    "ensure_accepting_orders",
    "governed_by_calendar",
    "is_channel_active",
    "is_switchable",
    "pos_channel_ref",
    "moment",
    "notification_copy",
    "off_windows",
    "period_options",
    "reason_presets",
    "request_switch",
    "resolve_period",
    "revision",
    "scheduled_line",
    "state_line",
]
