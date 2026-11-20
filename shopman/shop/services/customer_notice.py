"""Avisar o cliente com um toque (WP-G07; decisão 4 do dono, 17/11/2026: "pela API").

Três avisos que a casa dá ANTES de o cliente perceber, escolhidos pelo Caixa no detalhe
do pedido:

- ``delayed`` ("Vai atrasar"): a nova previsão, que o Caixa escolhe entre poucas horas
  prontas (um toque, sem campo para preencher);
- ``item_missing`` ("Faltou um item"): o que vai faltar, com a quantidade;
- ``reschedule`` ("Precisamos remarcar"): a encomenda inteira não fica pronta na data.

O texto é o aprovado pelo dono em 20/11/2026 (``notification_copy.CUSTOMER_COPY``), e o
envio é o caminho de sempre (``notification.send``): Directive, cadeia de canais,
recibo no pedido. Este módulo só decide QUANDO cada aviso cabe, monta a frase variável
(``status_note``) e guarda o envio contra o clique duplo. A frase chega pronta no
payload, porque é o Caixa quem escolhe a hora e o que falta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from django.utils import formats, timezone
from shopman.orderman.models import Directive, Order
from shopman.utils.formatting import format_clock

from shopman.shop.services import notification
from shopman.shop.services.order_helpers import is_test_order

DELAYED = "delayed"
ITEM_MISSING = "item_missing"
RESCHEDULE = "reschedule"
KINDS = (DELAYED, ITEM_MISSING, RESCHEDULE)

TEMPLATE_OF = {
    DELAYED: "order_delayed",
    ITEM_MISSING: "order_item_missing",
    RESCHEDULE: "order_reschedule_needed",
}

#: O nome do gesto, o mesmo que o recibo do pedido mostra.
LABEL_OF = {
    DELAYED: "Vai atrasar",
    ITEM_MISSING: "Faltou um item",
    RESCHEDULE: "Precisamos remarcar",
}

#: As horas prontas do "Vai atrasar", em minutos a partir de agora.
DELAY_STEPS = (30, 60, 120)
#: As horas prontas caem em múltiplos de 10 min: "16h30", nunca "16h27".
_CLOCK_STEP_MINUTES = 10

_OPEN_STATUSES = frozenset({Order.Status.NEW, Order.Status.ACCEPTED, Order.Status.PREPARING})


class CustomerNoticeRefused(Exception):
    """O aviso não cabe agora, ou a escolha da tela não serve. ``field`` aponta a entrada."""

    def __init__(self, message: str, *, code: str = "customer_notice_refused", field: str = ""):
        super().__init__(message)
        self.code = code
        self.field = field


@dataclass(frozen=True)
class DelayChoice:
    """Uma hora pronta do "Vai atrasar"."""

    value: str
    label: str
    note: str


@dataclass(frozen=True)
class MissingLine:
    """Uma linha do pedido que pode faltar."""

    line_id: str
    name: str
    qty: Decimal
    qty_display: str


@dataclass(frozen=True)
class Availability:
    kind: str
    label: str
    enabled: bool
    reason: str
    delay_choices: tuple[DelayChoice, ...] = field(default_factory=tuple)
    lines: tuple[MissingLine, ...] = field(default_factory=tuple)


# ── Quando cabe ─────────────────────────────────────────────────────────────


def offered(order: Order) -> bool:
    """O gesto aparece no pedido? Só no pedido aberto da casa: o iFood avisa pelo app
    dele, e o pronto ou encerrado não tem atraso nem falta a avisar."""
    return order.channel_ref != "ifood" and not is_test_order(order) and order.status in _OPEN_STATUSES


def order_refusal(order: Order) -> str:
    """Por que nenhum dos três cabe neste pedido; vazio quando cabem."""
    if order.channel_ref == "ifood":
        return "O cliente do iFood fala com a casa pelo app do iFood."
    if is_test_order(order):
        return "Pedido de teste não avisa ninguém."
    if order.status not in _OPEN_STATUSES:
        return "O pedido já ficou pronto ou terminou: não há o que avisar por aqui."
    customer = (order.data or {}).get("customer") or {}
    phone = str(customer.get("phone") or (order.data or {}).get("customer_phone") or "").strip()
    if not phone and not str(customer.get("ref") or "").strip():
        return "O pedido não tem o telefone do cliente."
    return ""


def availability(order: Order, *, now: datetime | None = None) -> tuple[Availability, ...]:
    """Os três gestos, na ordem da tela, cada um com o motivo quando não cabe."""
    now = now or timezone.now()
    blocked = order_refusal(order)
    out = []
    for kind in KINDS:
        reason = blocked or _kind_refusal(order, kind, now)
        out.append(
            Availability(
                kind=kind,
                label=LABEL_OF[kind],
                enabled=not reason,
                reason=reason,
                delay_choices=delay_choices(order, now=now) if kind == DELAYED and not reason else (),
                lines=missing_lines(order) if kind == ITEM_MISSING and not reason else (),
            )
        )
    return tuple(out)


def _kind_refusal(order: Order, kind: str, now: datetime) -> str:
    if kind == DELAYED:
        day = _commitment_day(order)
        if day is not None and day > timezone.localdate(now):
            return "A encomenda é para outro dia. Se ela não fica pronta na data, use Precisamos remarcar."
        return ""
    if kind == ITEM_MISSING:
        return "" if missing_lines(order) else "O pedido não tem itens."
    if kind == RESCHEDULE:
        return "" if notification._commitment_note(order) else "Só a encomenda tem data combinada para remarcar."
    raise CustomerNoticeRefused("Escolha um dos três avisos.", code="customer_notice_kind", field="kind")


def _commitment_day(order: Order):
    from datetime import date

    try:
        return date.fromisoformat(str((order.data or {}).get("delivery_date") or "").strip())
    except ValueError:
        return None


# ── O que o Caixa escolhe ──────────────────────────────────────────────────


def delay_choices(order: Order, *, now: datetime | None = None) -> tuple[DelayChoice, ...]:
    """As horas prontas: daqui a 30 min, 1 h e 2 h, em múltiplos de 10 min."""
    now = timezone.localtime(now or timezone.now())
    base = now.replace(second=0, microsecond=0)
    rest = base.minute % _CLOCK_STEP_MINUTES
    if rest:
        base += timedelta(minutes=_CLOCK_STEP_MINUTES - rest)
    out = []
    for minutes in DELAY_STEPS:
        at = base + timedelta(minutes=minutes)
        out.append(DelayChoice(value=at.isoformat(), label=f"{format_clock(at)} ({_in(minutes)})", note=eta_phrase(at, now=now)))
    return tuple(out)


def _in(minutes: int) -> str:
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"em {hours} hora" if hours == 1 else f"em {hours} horas"
    return f"em {minutes} min"


def eta_phrase(at: datetime, *, now: datetime | None = None) -> str:
    """"hoje, às 16h30", "amanhã, às 9h" ou "sábado, 04/10, às 9h", sem ponto final."""
    at = timezone.localtime(at)
    today = timezone.localdate(now or timezone.now())
    day = at.date()
    if day == today:
        when = "hoje"
    elif day == today + timedelta(days=1):
        when = "amanhã"
    else:
        when = f"{formats.date_format(day, 'l').lower()}, {formats.date_format(day, 'd/m')}"
    return f"{when}, às {format_clock(at)}"


def missing_lines(order: Order) -> tuple[MissingLine, ...]:
    """As linhas do pedido, na ordem dele, com a quantidade como o cliente a lê."""
    units = _units({item.sku for item in order.items.all()})
    return tuple(
        MissingLine(
            line_id=item.line_id,
            name=item.name or item.sku,
            qty=item.qty,
            qty_display=qty_display(item.qty, units.get(item.sku, "")),
        )
        for item in order.items.all().order_by("pk")
    )


def _units(skus: set[str]) -> dict[str, str]:
    try:
        from shopman.offerman.models import Product
    except ImportError:  # pragma: no cover — o Offerman está sempre instalado
        return {}
    return dict(Product.objects.filter(sku__in=skus).values_list("sku", "unit"))


def qty_display(qty: Decimal, unit: str = "") -> str:
    """"2 unidades", "1 unidade", "0,5 kg"."""
    value = Decimal(qty).normalize()
    text = format(value, "f").replace(".", ",")
    if unit == "kg":
        return f"{text} kg"
    return f"{text} unidade" if value == 1 else f"{text} unidades"


def missing_phrase(order: Order, chosen: list[dict]) -> str:
    """"Focaccia (2 unidades)" ou "Focaccia (2 unidades) e Brioche (1 unidade)".

    ``chosen``: ``[{"line_id": ..., "qty": ...}]``; sem ``qty``, a linha inteira.
    """
    lines = {line.line_id: line for line in missing_lines(order)}
    units = _units({item.sku for item in order.items.all()})
    skus = {item.line_id: item.sku for item in order.items.all()}
    parts = []
    seen = set()
    for entry in chosen or []:
        line_id = str((entry or {}).get("line_id") or "")
        line = lines.get(line_id)
        if line is None or line_id in seen:
            raise CustomerNoticeRefused("Marque só itens deste pedido, uma vez cada.", field="lines")
        seen.add(line_id)
        raw = (entry or {}).get("qty")
        try:
            qty = line.qty if raw in (None, "") else Decimal(str(raw))
        except ArithmeticError as exc:
            raise CustomerNoticeRefused("A quantidade que falta não é um número.", field="lines") from exc
        if qty <= 0 or qty > line.qty:
            raise CustomerNoticeRefused(
                f"Do item {line.name} podem faltar até {line.qty_display}.", field="lines"
            )
        parts.append(f"{line.name} ({qty_display(qty, units.get(skus[line_id], ''))})")
    if not parts:
        raise CustomerNoticeRefused("Marque o que vai faltar.", field="lines")
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} e {parts[-1]}"


def note_for(order: Order, kind: str, *, eta: str = "", lines: list[dict] | None = None,
             now: datetime | None = None) -> str:
    """A frase variável (``status_note``) da escolha da tela, ou a recusa dela."""
    now = now or timezone.now()
    refusal = order_refusal(order) or _kind_refusal(order, kind, now)
    if refusal:
        raise CustomerNoticeRefused(refusal)
    if kind == DELAYED:
        offered = {choice.value: choice for choice in delay_choices(order, now=now)}
        choice = offered.get(str(eta or ""))
        if choice is None:
            # A tela leu as horas um tempo atrás: aceita a hora lida se ainda está à frente.
            try:
                at = datetime.fromisoformat(str(eta or ""))
            except ValueError as exc:
                raise CustomerNoticeRefused("Escolha a nova previsão.", field="eta") from exc
            if timezone.is_naive(at) or at <= now or at > now + timedelta(days=1):
                raise CustomerNoticeRefused("Essa hora já passou. Escolha a nova previsão de novo.", field="eta")
            return eta_phrase(at, now=now)
        return choice.note
    if kind == ITEM_MISSING:
        return missing_phrase(order, lines or [])
    return notification._commitment_note(order)


# ── O texto e o envio ───────────────────────────────────────────────────────


def message(order: Order, kind: str, note: str) -> str:
    """A mensagem como o cliente a lê, para o Caixa conferir antes de enviar.

    O mesmo texto que sai (o do Admin, quando a loja o curou), com o nome, o pedido e a
    frase já escritos. A linha do link fica de fora: o link é pessoal e, no WhatsApp,
    vira o botão "Acompanhar pedido".
    """
    from shopman.shop.adapters._notification_templates import db_template, derive_context, render_template
    from shopman.shop.notification_copy import CUSTOMER_COPY

    template = TEMPLATE_OF[kind]
    _, body = db_template(template)
    body = body or CUSTOMER_COPY[template]["body"]
    body = "\n".join(line for line in body.split("\n") if "{tracking_url}" not in line)
    customer = (order.data or {}).get("customer") or {}
    ctx = derive_context(
        {
            "order_ref": order.ref,
            "customer_name": str(customer.get("name") or "") if isinstance(customer, dict) else "",
            "shop_name": notification._shop_name(),
            "status_note": note,
        }
    )
    return render_template(body, ctx).replace("*", "").strip()


def notice_revision(order: Order) -> str:
    """O que a mensagem leu do pedido: o estado, os itens e a data combinada."""
    from shopman.shop.services.remote_mutations import mutation_fingerprint

    data = order.data or {}
    return mutation_fingerprint(
        {
            "status": order.status,
            "items": sorted((item.line_id, str(item.qty)) for item in order.items.all()),
            "delivery_date": data.get("delivery_date"),
            "delivery_time_slot": data.get("delivery_time_slot"),
        }
    )


def send(order: Order, kind: str, note: str) -> Directive:
    """Enfileira o aviso pelo caminho de sempre e devolve a Directive dele.

    Os guardas do reenvio valem aqui também: envio anterior do mesmo aviso ainda
    saindo, ou de aceite não confirmado, ou de menos de um minuto atrás, recusa
    (``notification.NotificationResendRefused``). Cada aviso legítimo é uma ocorrência
    nova (o segundo atraso do dia é outro aviso).
    """
    template = TEMPLATE_OF[kind]
    refusal = notification.delivery_uncertainty_refusal(order, template)
    if refusal is not None:
        raise refusal
    history = Directive.objects.filter(topic=notification.TOPIC, payload__order_ref=order.ref, payload__template=template)
    latest = history.order_by("-created_at", "-pk").first()
    if latest is not None:
        if latest.status in (Directive.Status.QUEUED, Directive.Status.RUNNING):
            raise notification.NotificationResendRefused(
                "notification_send_pending", "O aviso anterior ainda está saindo. Aguarde um instante."
            )
        age = (timezone.now() - latest.created_at).total_seconds()
        if age < notification.RESEND_MIN_INTERVAL_SECONDS:
            wait = max(1, int(notification.RESEND_MIN_INTERVAL_SECONDS - age))
            raise notification.NotificationResendRefused(
                "notification_resend_too_soon", f"Este aviso acabou de sair. Aguarde {wait} s para mandar de novo."
            )
    notification.send(order, template, occurrence=str(history.count() + 1), status_note=note)
    directive = notification.latest_delivery(order, template)
    if directive is None:  # pragma: no cover — o pedido de teste já foi recusado antes
        raise CustomerNoticeRefused("O aviso não foi enfileirado.")
    return directive
