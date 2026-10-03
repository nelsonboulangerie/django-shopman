"""Precisa de você: a fila das filas da Central (SUITE-UX §4.1 e §6, UX-H1).

A Central soma as filas dos papéis do operador e mostra o ITEM EXATO primeiro: "Pedido K7Q2
para aceitar", "Pedido F15 atrasado", "Lote de Croissant passou do tempo". Cada item traz o
essencial da decisão, a hora que importa (há quanto espera, ou quanto falta) e um gesto que
abre o lugar exato no app certo.

**Só fontes que já existem.** Nada aqui é regra nova: cada fonte é a mesma leitura que o app
de destino já faz, recortada para o que pede alguém agora.

- Gestor: pedido NOVO esperando aceite (a Entrada do quadro, `order_queue`), com o prazo da
  confirmação otimista (`confirmation.timeout`) ou o do marketplace (`data.ifood.confirm_by`).
- Cozinha: pedido de estação que passou da meta da estação (a régua do card do KDS).
- PDV: encomenda de retirada para hoje cuja janela começa na próxima hora (Encomendas do PDV).
- Produção: lote iniciado que passou do tempo da receita (o "atrasado" do painel da Produção).
- Marketing: anúncio esperando decisão, antes de caducar (o "Hoje" do Marketing).
- Avisos: alerta operacional ainda não visto, de erro ou crítico, que tem lugar num app
  (o sino do Gestor ou o contexto da Produção).

**Permissão é por item, não por tela.** Cada fonte só entra para quem pode AGIR nela, com o
mesmo predicado que guarda a porta do app (e, no Marketing, a permissão de aprovar). Se o app
de destino não tem URL configurada, o item também não entra: nunca um gesto para link morto.

**Uma fonte que falha não derruba a Central.** A Central é a home do operador: cada fonte
roda isolada e, se quebrar, sai do resultado com um aviso no log.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from urllib.parse import quote, urlencode

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from shopman.backstage import permissions

logger = logging.getLogger(__name__)

#: Quantos itens a Central mostra em foco; o resto vira "+N" (FILA nunca pagina).
FOCUS_LIMIT = 6

#: Meta do aceite: o card do Gestor fica urgente aos 4 minutos (`order_queue._timer_class`).
ACCEPT_TARGET_SECONDS = 240

#: Quanto à frente a Central olha as encomendas de retirada do PDV.
PREORDER_HORIZON = timedelta(hours=1)

#: Item com prazo fica âmbar quando falta menos que isto.
DUE_SOON_SECONDS = 15 * 60

#: Anúncio sem prazo de caducar: entra na fila, mas atrás do que tem relógio.
_NO_DEADLINE_SLACK = 6 * 3600

#: Alertas que repetiriam um item que a Central já mostra pela fonte própria.
_ALERTS_SHOWN_BY_THEIR_SOURCE = frozenset({"stale_new_order", "production_late"})


@dataclass(frozen=True)
class HubQueueItemProjection:
    """Um item que pede este operador agora, com o gesto que abre o lugar exato."""

    key: str
    app: str  # ref do tile de destino (gestor, kds, pos, production, marketing)
    app_label: str
    kind: str  # order_to_accept | ticket_late | preorder_pickup | work_order_late | announcement_review | alert
    title: str
    detail: str
    #: Começo da espera (ISO). A Central mostra "há N min" quando ``time_mode`` é ``since``.
    waiting_since: str
    #: O prazo que importa (ISO), ou vazio.
    due_at: str
    #: Como o prazo entra na frase: "aceita sozinho em" (contagem) ou "retira às" (relógio).
    due_label: str
    due_style: str  # "countdown" | "clock" | ""
    #: O prazo na hora da loja ("10:15"), para ``due_style == "clock"``.
    due_clock: str
    time_mode: str  # "since" (há quanto espera) | "until" (quanto falta para o prazo)
    #: Passou da meta, ou o prazo está perto: a Central pinta o tempo de âmbar.
    attention: bool
    action_label: str
    url: str
    #: Folga em segundos até estourar (negativa = estourou). Ordena entre apps.
    slack_seconds: int = 0


@dataclass(frozen=True)
class HubAppStatusProjection:
    """A linha de estado do bloco de um app, que concorda com a fila."""

    attention: str = ""  # o que pede alguém ("1 para aceitar"), pintado de âmbar
    summary: str = ""  # o resto, calmo ("11 ativos")


@dataclass(frozen=True)
class HubQueueProjection:
    items: tuple[HubQueueItemProjection, ...]
    total_count: int
    more_count: int
    server_now: str


@dataclass
class _Collected:
    items: list[HubQueueItemProjection] = field(default_factory=list)
    statuses: dict[str, HubAppStatusProjection] = field(default_factory=dict)


# ── Utilidades ─────────────────────────────────────────────────────────


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _clock(value: datetime | None) -> str:
    return timezone.localtime(value).strftime("%H:%M") if value else ""


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _called_code(ref: str) -> str:
    """O código que se chama em voz alta: o que vem depois do último hífen do ref."""
    value = str(ref or "").strip()
    return value.rsplit("-", 1)[-1] if "-" in value else value


def _join_url(base: str, path: str, query: dict[str, str] | None = None) -> str:
    url = base.rstrip("/") + "/" + path.lstrip("/")
    return f"{url}?{urlencode(query)}" if query else url


def _attention(slack: float, *, time_mode: str) -> bool:
    return slack <= 0 or (time_mode == "until" and slack <= DUE_SOON_SECONDS)


def _parse_iso(raw: str) -> datetime | None:
    value = parse_datetime(str(raw or "").strip()) if raw else None
    if value is not None and timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _truncate(text: str, limit: int = 140) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 3].rstrip() + "..."


# ── Fontes ─────────────────────────────────────────────────────────────


def _orders(user, base: str, label: str, now: datetime, out: _Collected) -> None:
    """Gestor: pedido novo esperando aceite (a Entrada do quadro)."""
    from shopman.orderman.models import Order

    from shopman.backstage.projections import order_queue
    from shopman.backstage.projections.preorders import _channel_labels, _fallback_channel_label
    from shopman.shop.services import order_composition
    from shopman.shop.services.pos_sales_mode import is_pos_counter_order

    active = [
        order
        for order in Order.objects.filter(status__in=order_queue.ACTIVE_STATUSES).order_by("created_at")
        if not is_pos_counter_order(order)
    ]
    # Encomenda de data futura vive em "Agendados", não é trabalho do dia (mesma régua do quadro).
    today_work = [
        order
        for order in active
        if not (order.status in ("new", "accepted", "preparing") and order_queue._is_future_preorder(order))
    ]
    to_accept = [order for order in today_work if order.status == "new"]
    deadlines = order_queue._confirmation_deadlines([order.ref for order in to_accept])
    channels = _channel_labels({order.channel_ref or "" for order in to_accept})

    for order in to_accept:
        elapsed = (now - order.created_at).total_seconds()
        slack = ACCEPT_TARGET_SECONDS - elapsed
        deadline_iso, deadline_action = deadlines.get(order.ref) or order_queue._external_deadline(order) or ("", "")
        deadline = _parse_iso(deadline_iso)
        due_label = ""
        if deadline is not None:
            due_label = "cancela sozinho em" if deadline_action == "cancel" else "aceita sozinho em"
            if deadline_action == "cancel":
                # Vencer aqui perde o pedido: é o prazo do marketplace que manda.
                slack = min(slack, (deadline - now).total_seconds())
        data = order.data or {}
        customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
        customer_name = order_queue._format_customer_display(
            customer.get("name", "") or customer.get("phone", "") or data.get("customer_phone", "") or order.handle_ref or ""
        )
        channel = channels.get(order.channel_ref or "", "") or _fallback_channel_label(order.channel_ref)
        detail = " · ".join(
            part
            for part in (
                channel,
                customer_name,
                order_queue._money(order_composition.effective_total_q(order)),
            )
            if part
        )
        out.items.append(
            HubQueueItemProjection(
                key=f"gestor:order:{order.ref}",
                app="gestor",
                app_label=label,
                kind="order_to_accept",
                title=f"Pedido {_called_code(order.ref)} para aceitar",
                detail=detail,
                waiting_since=_iso(order.created_at),
                due_at=_iso(deadline),
                due_label=due_label,
                due_style="countdown" if deadline is not None else "",
                due_clock="",
                time_mode="since",
                attention=_attention(slack, time_mode="since"),
                action_label="Abrir pedido",
                url=_join_url(base, quote(order.ref, safe="")),
                slack_seconds=int(slack),
            )
        )

    out.statuses["gestor"] = _merge_status(
        out.statuses.get("gestor"),
        HubAppStatusProjection(
            attention=f"{len(to_accept)} para aceitar" if to_accept else "",
            summary=_plural(len(today_work), "ativo", "ativos"),
        ),
    )


def _kds(user, base: str, label: str, now: datetime, out: _Collected) -> None:
    """Cozinha: pedido de estação que passou da meta da estação."""
    from shopman.backstage.models import KDSTicket
    from shopman.backstage.projections import kds as kds_projection

    today = timezone.localdate()
    tickets = list(
        KDSTicket.objects.filter(
            status__in=kds_projection.ACTIVE_TICKET_STATUSES,
            kds_instance__is_active=True,
        )
        .exclude(kds_instance__type="expedition")
        .select_related("kds_instance")
        .order_by("created_at")
    )
    on_today = []
    for ticket in tickets:
        source = kds_projection._resolve_ticket_source(ticket)
        # Mesma régua do quadro da estação: hoje inclui backlog; encomenda futura não.
        if kds_projection._source_matches_service_date(source, selected_date=today, today=today):
            on_today.append((ticket, source))

    late = 0
    for ticket, source in on_today:
        instance = ticket.kds_instance
        target = instance.target_time_minutes * 60
        elapsed = (now - ticket.created_at).total_seconds()
        if elapsed < target:
            continue
        late += 1
        card = kds_projection._build_ticket(ticket, instance, source=source)
        items = ", ".join(f"{item.qty}x {item.name}" for item in card.items[:3])
        if len(card.items) > 3:
            items += "..."
        title = f"Pedido {_called_code(card.order_ref)} atrasado"
        out.items.append(
            HubQueueItemProjection(
                key=f"kds:ticket:{ticket.pk}",
                app="kds",
                app_label=label,
                kind="ticket_late",
                title=f"{title}: {items}" if items else title,
                detail=f"Estação {instance.name} · meta {instance.target_time_minutes} min",
                waiting_since=_iso(ticket.created_at),
                due_at="",
                due_label="",
                due_style="",
                due_clock="",
                time_mode="since",
                attention=True,
                action_label="Abrir estação",
                url=_join_url(base, quote(instance.ref, safe="")),
                slack_seconds=int(target - elapsed),
            )
        )

    out.statuses["kds"] = HubAppStatusProjection(
        attention=_plural(late, "pedido atrasado", "pedidos atrasados") if late else "",
        summary=_plural(len(on_today), "pedido nas estações", "pedidos nas estações"),
    )


def _preorders(user, base: str, label: str, now: datetime, out: _Collected) -> None:
    """PDV: encomenda de retirada para hoje, com a janela começando na próxima hora."""
    from shopman.backstage.projections.preorders import build_preorder_list

    today = timezone.localdate()
    listing = build_preorder_list(date_from=today, date_to=today)
    cards = [card for day in listing.days for card in day.orders]
    open_pickups = [
        card
        for card in cards
        if card.fulfillment_type == "pickup" and card.situation not in ("delivered", "out_for_delivery")
    ]
    due_now = 0
    tz = timezone.get_current_timezone()
    for card in open_pickups:
        if not card.window_start:
            continue
        hour, minute = (int(part) for part in card.window_start.split(":"))
        starts_at = timezone.make_aware(datetime.combine(today, time(hour, minute)), tz)
        slack = (starts_at - now).total_seconds()
        if starts_at - now > PREORDER_HORIZON:
            continue
        due_now += 1
        detail_parts = [card.items_summary]
        if card.payment_state == "to_receive" and card.balance_display:
            detail_parts.append(f"a receber {card.balance_display}")
        out.items.append(
            HubQueueItemProjection(
                key=f"pos:preorder:{card.ref}",
                app="pos",
                app_label=label,
                kind="preorder_pickup",
                title=f"Encomenda de {card.customer_name} para retirar" if card.customer_name else "Encomenda para retirar",
                detail=" · ".join(part for part in detail_parts if part),
                waiting_since="",
                due_at=_iso(starts_at),
                due_label="retira às",
                due_style="clock",
                due_clock=card.window_start,
                time_mode="until",
                attention=_attention(slack, time_mode="until"),
                action_label="Abrir encomenda",
                url=_join_url(base, f"preorders/{quote(card.ref, safe='')}"),
                slack_seconds=int(slack),
            )
        )

    out.statuses["pos"] = HubAppStatusProjection(
        attention=f"{due_now} para retirar na próxima hora" if due_now else "",
        summary=_plural(len(open_pickups), "encomenda para retirar hoje", "encomendas para retirar hoje"),
    )


def _production(user, base: str, label: str, now: datetime, out: _Collected) -> None:
    """Produção: lote iniciado que passou do tempo da receita (o "atrasado" do painel)."""
    from shopman.craftsman.models import WorkOrder

    from shopman.backstage.projections import production as production_projection

    started = list(
        WorkOrder.objects.filter(status=WorkOrder.Status.STARTED).select_related("recipe").order_by("started_at", "created_at")
    )
    late = 0
    for wo in started:
        if not production_projection._is_late_started(wo):
            continue
        late += 1
        started_at = wo.started_at or wo.created_at
        target = production_projection._target_minutes(wo)
        elapsed = (now - started_at).total_seconds()
        recipe_name = wo.recipe.name or wo.recipe.output_sku or wo.recipe.ref
        query = {"q": wo.ref}
        if wo.target_date:
            query["date"] = wo.target_date.isoformat()
        out.items.append(
            HubQueueItemProjection(
                key=f"production:work_order:{wo.ref}",
                app="production",
                app_label=label,
                kind="work_order_late",
                title=f"Lote de {recipe_name} passou do tempo",
                detail=f"{wo.ref} · iniciado às {_clock(started_at)} · meta {target} min",
                waiting_since=_iso(started_at),
                due_at="",
                due_label="",
                due_style="",
                due_clock="",
                time_mode="since",
                attention=True,
                action_label="Abrir lote",
                url=_join_url(base, "expedite", query),
                slack_seconds=int(target * 60 - elapsed),
            )
        )

    today_orders = WorkOrder.objects.filter(target_date=timezone.localdate()).exclude(status=WorkOrder.Status.VOID)
    total = today_orders.count()
    finished = today_orders.filter(status=WorkOrder.Status.FINISHED).count()
    out.statuses["production"] = _merge_status(
        out.statuses.get("production"),
        HubAppStatusProjection(
            attention=_plural(late, "lote passou do tempo", "lotes passaram do tempo") if late else "",
            summary=f"{finished} de {_plural(total, 'lote finalizado hoje', 'lotes finalizados hoje')}" if total else "",
        ),
    )


def _marketing(user, base: str, label: str, now: datetime, out: _Collected) -> None:
    """Marketing: anúncio esperando decisão, antes de caducar."""
    if not (permissions.is_superuser(user) or user.has_perm("shop.approve_marketing_announcements")):
        # Quem só vê o Marketing não decide anúncio: o item não é dele.
        return
    from shopman.backstage.projections.marketing import _platform_label
    from shopman.shop.models import Announcement, AnnouncementStatus

    pending = [
        announcement
        for announcement in Announcement.objects.filter(status=AnnouncementStatus.PENDING_REVIEW)
        .select_related("rule", "template")
        .order_by("created_at")
        if not announcement.is_expired(now=now)
    ]
    for announcement in pending:
        name = (
            (announcement.rule.name if announcement.rule_id else "")
            or (announcement.template.name if announcement.template_id else "")
            or "anúncio avulso"
        )
        platforms = ", ".join(_platform_label(platform) for platform in (announcement.platforms or []))
        audience_total = int((announcement.audience or {}).get("total") or 0)
        detail_parts = [platforms]
        if audience_total:
            detail_parts.append(_plural(audience_total, "pessoa", "pessoas"))
        expires = announcement.expires_at
        if expires is not None:
            slack = (expires - now).total_seconds()
            time_mode = "until"
        else:
            slack = _NO_DEADLINE_SLACK
            time_mode = "since"
        out.items.append(
            HubQueueItemProjection(
                key=f"marketing:announcement:{announcement.pk}",
                app="marketing",
                app_label=label,
                kind="announcement_review",
                title=f"Anúncio para decidir: {name}",
                detail=" · ".join(part for part in detail_parts if part),
                waiting_since=_iso(announcement.created_at),
                due_at=_iso(expires),
                due_label="decide até" if expires is not None else "",
                due_style="clock" if expires is not None else "",
                due_clock=_clock(expires),
                time_mode=time_mode,
                attention=_attention(slack, time_mode=time_mode),
                action_label="Revisar",
                url=_join_url(base, f"announcements/{announcement.pk}"),
                slack_seconds=int(slack),
            )
        )

    out.statuses["marketing"] = HubAppStatusProjection(
        attention=_plural(len(pending), "anúncio para decidir", "anúncios para decidir") if pending else "",
    )


def _alerts(user, urls: dict[str, str], labels: dict[str, str], now: datetime, out: _Collected) -> None:
    """Avisos: alerta não visto, de erro ou crítico, que tem lugar num app."""
    from shopman.backstage.models import OperatorAlert
    from shopman.backstage.projections.alerts import _alert_actions, readable_message
    from shopman.backstage.services import alerts as alert_service

    can_orders = permissions.can_manage_orders(user) and urls.get("gestor")
    can_production = permissions.can_operate_production(user) and urls.get("production")
    if not (can_orders or can_production):
        return

    rows = (
        alert_service._active_for(user)
        .filter(acknowledged=False, severity__in=("error", "critical"))
        .exclude(type__in=_ALERTS_SHOWN_BY_THEIR_SOURCE)[:50]
    )
    counts: dict[str, int] = {}
    for alert in rows:
        app = ""
        surface = ""
        if alert.type in OperatorAlert.PRODUCTION_TYPES:
            # Alerta de produção carrega o ref do LOTE em ``order_ref``: nunca vira "Abrir o
            # pedido" no Gestor. Sem a Produção, ele fica no sino de quem a opera.
            app = "production" if can_production else ""
        elif can_orders and (alert.audience == "orders" or alert.order_ref) and alert.type not in alert_service.ORDERS_SCOPE_EXCLUDED:
            app, surface = "gestor", "orders"
        if not app:
            continue
        target_date = ""
        if app == "production" and alert.order_ref:
            from shopman.craftsman.models import WorkOrder

            wo_date = WorkOrder.objects.filter(ref=alert.order_ref).values_list("target_date", flat=True).first()
            target_date = wo_date.isoformat() if wo_date else ""
        open_actions = [
            action
            for action in _alert_actions(alert, target_date=target_date, surface=surface)
            if action.kind == "open_alert_context"
        ]
        if not open_actions:
            continue
        action = open_actions[0]
        counts[app] = counts.get(app, 0) + 1
        critical = alert.severity == "critical"
        out.items.append(
            HubQueueItemProjection(
                key=f"{app}:alert:{alert.pk}",
                app=app,
                app_label=labels[app],
                kind="alert",
                title=alert.get_type_display(),
                detail=_truncate(readable_message(alert.message)),
                waiting_since=_iso(alert.created_at),
                due_at="",
                due_label="",
                due_style="",
                due_clock="",
                time_mode="since",
                attention=critical,
                action_label=action.label,
                url=_join_url(urls[app], action.href),
                # Crítico vai para o topo; erro entra no meio, atrás do que estourou a meta.
                slack_seconds=-3600 if critical else DUE_SOON_SECONDS,
            )
        )
    for app, count in counts.items():
        out.statuses[app] = _merge_status(
            out.statuses.get(app),
            HubAppStatusProjection(attention=_plural(count, "aviso", "avisos")),
        )


def _merge_status(current: HubAppStatusProjection | None, extra: HubAppStatusProjection) -> HubAppStatusProjection:
    if current is None:
        return extra
    return HubAppStatusProjection(
        attention=" · ".join(part for part in (current.attention, extra.attention) if part),
        summary=" · ".join(part for part in (current.summary, extra.summary) if part),
    )


# ── Montagem ───────────────────────────────────────────────────────────

_Source = Callable[[object, str, str, datetime, _Collected], None]

#: (ref do app, predicado de quem pode agir, fonte). O predicado é o MESMO da porta do app.
_SOURCES: tuple[tuple[str, Callable[[object], bool], _Source], ...] = (
    ("gestor", permissions.can_manage_orders, _orders),
    ("kds", permissions.can_operate_kds, _kds),
    ("pos", permissions.can_operate_pos, _preorders),
    ("production", permissions.can_operate_production, _production),
    ("marketing", permissions.can_manage_campaigns, _marketing),
)


def collect_hub_queue(
    user,
    *,
    urls: dict[str, str],
    labels: dict[str, str],
    now: datetime | None = None,
) -> tuple[HubQueueProjection, dict[str, HubAppStatusProjection]]:
    """A fila das filas de ``user`` e a linha de estado de cada app que ele abre.

    ``urls`` e ``labels`` vêm do registro da Central: só entra item de app que o operador
    pode abrir E que tem URL configurada.
    """
    now = now or timezone.now()
    out = _Collected()
    for app, can_act, source in _SOURCES:
        base = urls.get(app)
        if not base or not can_act(user):
            continue
        try:
            source(user, base, labels[app], now, out)
        except Exception:
            logger.warning("hub_queue.source_failed app=%s", app, exc_info=True)
    try:
        _alerts(user, urls, labels, now, out)
    except Exception:
        logger.warning("hub_queue.source_failed app=alerts", exc_info=True)

    ordered = sorted(out.items, key=lambda item: (item.slack_seconds, item.waiting_since or item.due_at, item.key))
    focus = tuple(ordered[:FOCUS_LIMIT])
    return (
        HubQueueProjection(
            items=focus,
            total_count=len(ordered),
            more_count=max(0, len(ordered) - len(focus)),
            server_now=_iso(now),
        ),
        out.statuses,
    )
