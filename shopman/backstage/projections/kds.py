"""KDSBoardProjection — read models for the Kitchen Display System (Fase 4).

Translates KDS instances and the tickets of the preparation stations into immutable
projections. A Saída não tem quadro aqui (SUITE-UX §15 e §16: a Saída é uma só, no
Gestor); deste módulo ela só leva as estações de cada pedido
(``kitchen_station_chips``), que o cartão do Gestor mostra.

O quadro é sempre o de HOJE: a prévia de outra data foi para a Produção/Encomendas
(SUITE-UX §9, "quem executa o hoje não planeja").

Never imports from ``shopman.backstage.views.*``.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.services import operator_orders
from shopman.shop.services.order_helpers import get_commitment_date, get_fulfillment_type, json_quantity
from shopman.shop.services.pos import display_tab_ref, is_numeric_tab_ref

from .order_queue import (
    _DEFAULT_CHANNEL_ICON,
    CHANNEL_ICONS,
    _test_order_label,
)

logger = logging.getLogger(__name__)

ACTIVE_TICKET_STATUSES = ("pending", "in_progress")
RECENT_CANCELLED_WINDOW = timedelta(minutes=10)
RECENT_DONE_WINDOW = timedelta(minutes=30)
RECENT_DONE_LIMIT = 12


# ── Projections ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class KDSItemProjection:
    """A single item within a KDS ticket."""

    sku: str
    name: str
    qty: int | str
    notes: str
    stock_warning: str  # "" = no warning


@dataclass(frozen=True)
class KDSTicketProjection:
    """A KDS ticket card (prep/picking station)."""

    pk: int
    order_ref: str
    channel_icon: str
    customer_name: str
    fulfillment_icon: str
    created_at_display: str
    elapsed_seconds: int
    target_seconds: int  # target SLA in seconds (for K12 timer context)
    timer_class: str  # "timer-ok", "timer-warning", "timer-late"
    items: tuple[KDSItemProjection, ...]
    status: str
    # Comanda disparada antes do pagamento muda de dono quando o Order nasce:
    # o pedido vira a referência principal; a comanda permanece riscada apenas
    # para conferência visual e para deixar claro que já foi liberada.
    previous_tab_ref: str = ""
    status_label: str = ""
    is_cancelled: bool = False
    cancelled_at_display: str = ""
    completed_at_display: str = ""
    # Order-level notes shown to the kitchen: the operator's kitchen note (from the
    # gestor) and the customer's checkout note (order_notes). Empty when absent.
    kitchen_note: str = ""
    customer_note: str = ""
    # Pedido de teste da homologação do iFood NÃO vira ticket (``kds.dispatch``
    # o suprime). O crachá existe para o que já está no painel: ticket criado
    # antes desta trava, ou disparado por outro caminho. Vazio no pedido de
    # verdade — quem vê o crachá sabe que aquilo não se produz.
    test_order_label: str = ""
    # A gêmea do gate no card da estação (prévia v4, cozinha-estacao4.html, K11):
    # quando o servidor vai recusar o Pronto (pedido sem confirmação, pagamento
    # digital ainda não capturado), o card diz ANTES do toque. Era um toast 5 s
    # depois de tocar, quando a janela de "Desfazer" fechava e o POST voltava
    # recusado. Iniciar continua livre ("pode adiantar"). "" quando libera.
    finish_block_label: str = ""
    finish_block_reason: str = ""
    # Volumes do pedido (sacolas, caixas), declarados por quem embalou: aqui na
    # estação, no posto Saída ou no Gestor (``Order.data["volumes"]``, 0 = não
    # declarado). ``volumes_order_ref`` é o ``Order.ref`` de verdade para o POST
    # ``orders/<ref>/volumes/`` e ``volumes_revision`` a base da intenção; os dois
    # vazios quando o ticket ainda é de comanda (sem pedido) ou é prévia agendada,
    # e aí o gesto não aparece.
    volumes: int = 0
    volumes_order_ref: str = ""
    volumes_revision: str = ""
    # Quem iniciou este ticket e a que horas ("Rafael", "21:56"), de
    # ``Order.data["kds_started"]``: o nome de chamada do operador (o primeiro nome
    # da conta), nunca o login. Vazio antes do início e no ticket de comanda.
    started_by: str = ""
    started_at_display: str = ""
    # Encomenda (pedido com data combinada, feito antes do dia): o card diz
    # "Encomenda · <cliente>" (prévia v4, nota 6). Venda do dia não mostra cliente,
    # canal nem telefone: o código chama o pedido.
    is_preorder: bool = False
    # Hora combinada com o cliente, quando o pedido tem uma: "retira às 22:30" /
    # "entrega às 22:30". Vazio sem hora combinada.
    due_time_display: str = ""
    # Alguém da estação já deu "Visto" neste ticket (ou já o iniciou): o aviso de
    # pedido novo para em todas as telas da estação juntas (K20, registrado no
    # servidor por estação). No cancelado, é o "Visto" DEPOIS do cancelamento.
    seen: bool = False


@dataclass(frozen=True)
class KDSExitStationChipProjection:
    """Uma estação do pedido, vista da Saída: em que pé ela está com ele.

    A estação de tela dá baixa sozinha — o chip só mostra o estado. A estação
    SEM tela (tem impressora, ``KDSInstance.print_terminal``) recebeu o pedido
    em papel, e quem dá a baixa dela é a Saída: o chip diz quando o papel saiu
    e oferece "Pronto" (decisão do dono, 26/09/2026).
    """

    station_ref: str
    station_name: str
    #: A estação recebe o pedido impresso (não tem tela).
    prints: bool
    #: "pending" · "in_progress" · "done" — o MENOS avançado dos tickets da
    #: estação neste pedido: ela só está pronta quando todos estão.
    state: str
    #: "na fila" · "em preparo" · "pronto"
    state_label: str
    #: Só na estação sem tela, com ticket aberto: "impresso às 10:42" ·
    #: "na fila da impressora" · "não imprimiu". Vazio quando não há papel.
    paper_label: str = ""
    #: True quando o papel não saiu (falhou, expirou): a Saída avisa a estação.
    paper_failed: bool = False
    #: Itens desta estação retirados do pedido depois do disparo (o papel
    #: CANCELADO saiu na bancada). Zero quando não há.
    cancelled_items: int = 0
    #: A Saída pode dar "Pronto" por esta estação agora.
    can_mark_ready: bool = False
    #: Estação pronta num pedido que ainda está na casa: o ticket que o Gestor
    #: devolve à cozinha ("Voltar para Lanches", ``kds/tickets/<pk>/recall/``).
    #: ``None`` quando não há o que devolver.
    recall_ticket_pk: int | None = None


@dataclass(frozen=True)
class KDSInstanceSummaryProjection:
    """A KDS instance in the index (station selector)."""

    ref: str
    name: str
    type: str
    type_display: str
    # ATIVOS: pendentes MAIS em preparo. O campo já se chamava `pending_count` e
    # sempre foi preenchido com o total do board — "6 na fila" mandava o cozinheiro
    # para a estação onde cinco daqueles seis já tinham dono. É a mesma grandeza que
    # o board mostra, e agora com o mesmo nome (um nome por conceito).
    active_count: int


@dataclass(frozen=True)
class KDSBoardProjection:
    """Top-level read model for a KDS display."""

    instance_ref: str
    instance_name: str
    instance_type: str
    tickets: tuple[KDSTicketProjection, ...]
    counts: dict[str, int]  # "pending", "in_progress", "total"
    cancelled_tickets: tuple[KDSTicketProjection, ...] = ()
    recent_done: tuple[KDSTicketProjection, ...] = ()  # para recall (desfazer finalização)
    # Como a estação provisionada se mostra (prévia v4, nota 1: "densidade e som
    # saem do botão: vêm da estação provisionada"). É da BANCADA, não do toque de
    # quem passa: o cadastro guarda (``KDSInstance.sound_enabled`` e
    # ``KDSInstance.config["density"]``) e todas as telas da estação seguem.
    density: str = "cozy"
    sound_enabled: bool = True


@dataclass(frozen=True)
class KDSCustomerOrderProjection:
    """Privacy-safe order status for a customer-facing ready board."""

    ref: str
    status: str
    status_label: str
    updated_at_display: str


@dataclass(frozen=True)
class KDSCustomerStatusProjection:
    """Customer-facing KDS status split by preparation and pickup readiness."""

    preparing: tuple[KDSCustomerOrderProjection, ...]
    ready: tuple[KDSCustomerOrderProjection, ...]
    updated_at_display: str


# ── Builders ───────────────────────────────────────────────────────────


def build_kds_index() -> tuple[KDSInstanceSummaryProjection, ...]:
    """Build the KDS instance selector (index page)."""
    from shopman.backstage.models import KDSInstance

    instances = KDSInstance.objects.filter(is_active=True).order_by("name")
    result: list[KDSInstanceSummaryProjection] = []

    for inst in instances:
        if inst.type == "expedition":
            # A Saída mora no Gestor (SUITE-UX §15): a lista só a aponta, com
            # quantos pedidos estão prontos para sair hoje.
            count = sum(
                1
                for order in Order.objects.filter(status=Order.Status.READY)
                if _due_today(order, today=timezone.localdate())
            )
        else:
            # A mesma conta do board de hoje: encomenda futura não é trabalho do turno.
            count = int(build_kds_board(inst.ref).counts.get("total", 0))

        result.append(
            KDSInstanceSummaryProjection(
                ref=inst.ref,
                name=inst.name,
                type=inst.type,
                type_display=inst.get_type_display(),
                active_count=count,
            )
        )

    return tuple(result)


def build_kds_board(instance_ref: str) -> KDSBoardProjection:
    """Build the KDS board projection for a preparation station, today."""
    from shopman.backstage.models import KDSInstance, KDSTicket
    from shopman.backstage.services.exceptions import KDSInstanceNotFound

    instance = KDSInstance.objects.filter(ref=instance_ref, is_active=True).first()
    if instance is None:
        raise KDSInstanceNotFound(f"Estação de KDS não encontrada: {instance_ref}.")
    if instance.type == "expedition":
        # A Saída é uma só, no Gestor (SUITE-UX §15 e §16): a Cozinha não tem
        # quadro para ela. A lista de estações já leva quem a escolhe para lá.
        raise KDSInstanceNotFound("A Saída fica no Gestor.")

    today = timezone.localdate()
    active_all = list(
        KDSTicket.objects.filter(
            kds_instance=instance,
            status__in=ACTIVE_TICKET_STATUSES,
        )
        .order_by("created_at")
    )
    active_session_keys = {ticket.session_key for ticket in active_all if ticket.session_key}
    now = timezone.now()
    cancelled_all = list(
        KDSTicket.objects.filter(
            kds_instance=instance,
            status="cancelled",
            acknowledged_at__isnull=True,
        )
        .filter(
            Q(cancelled_at__gte=now - RECENT_CANCELLED_WINDOW)
            | Q(session_key__in=active_session_keys)
        )
        .order_by("-cancelled_at", "-created_at")
    )
    done_all = list(
        KDSTicket.objects.filter(
            kds_instance=instance,
            status="done",
            completed_at__gte=now - RECENT_DONE_WINDOW,
        )
        .order_by("-completed_at")[:RECENT_DONE_LIMIT]
    )

    all_rows = [*active_all, *cancelled_all, *done_all]
    sources = {ticket.pk: _resolve_ticket_source(ticket) for ticket in all_rows}
    # Ticket de encomenda disparado antes da data não é trabalho do turno: ele
    # aparece (e toca) no dia combinado.
    active = [ticket for ticket in active_all if _due_today(sources[ticket.pk], today=today)]
    cancelled = [ticket for ticket in cancelled_all if _due_today(sources[ticket.pk], today=today)]
    from shopman.shop.services import kds as kds_core

    # A lista de concluídos existe só para o "desfazer finalização": ticket de
    # pedido que já saiu da cozinha (despachado, concluído, cancelado) não entra,
    # porque o servidor recusaria o desfazer (``recall_block_reason``).
    done = [
        ticket for ticket in done_all
        if _due_today(sources[ticket.pk], today=today)
        and not kds_core.recall_block_reason(sources[ticket.pk])
    ]

    names = _operator_names(active, sources)
    tickets = tuple(_build_ticket(t, instance, source=sources[t.pk], names=names) for t in active)
    cancelled_tickets = tuple(_build_ticket(t, instance, source=sources[t.pk]) for t in cancelled)
    recent_done = tuple(_build_ticket(t, instance, source=sources[t.pk]) for t in done)
    pending = sum(1 for t in tickets if t.status == "pending")
    in_progress = sum(1 for t in tickets if t.status == "in_progress")

    return KDSBoardProjection(
        instance_ref=instance.ref,
        instance_name=instance.name,
        instance_type=instance.type,
        tickets=tickets,
        counts={
            "pending": pending,
            "in_progress": in_progress,
            "total": len(tickets),
            "cancelled_recent": len(cancelled_tickets),
            "done_recent": len(recent_done),
        },
        cancelled_tickets=cancelled_tickets,
        recent_done=recent_done,
        density=station_density(instance),
        sound_enabled=bool(instance.sound_enabled),
    )


#: As densidades da grade que a estação pode guardar (``KDSInstance.config["density"]``).
STATION_DENSITIES = ("compact", "cozy", "roomy")


def station_density(instance) -> str:
    """A densidade guardada no cadastro da estação; a padrão quando não há."""
    value = str((instance.config or {}).get("density") or "")
    return value if value in STATION_DENSITIES else "cozy"


def _operator_names(tickets, sources: dict) -> dict[str, str]:
    """``login → nome de chamada`` de quem iniciou estes tickets, numa consulta só.

    ``Order.data["kds_started"][pk]["by"]`` guarda o login (o ator da API); o card
    diz o primeiro nome da conta ("iniciado por Rafael"). Sem nome, o login.
    """
    from django.contrib.auth import get_user_model

    logins: set[str] = set()
    for ticket in tickets:
        source = sources.get(ticket.pk)
        started = ((getattr(source, "data", None) or {}) if source is not None else {}).get("kds_started")
        record = started.get(str(ticket.pk)) if isinstance(started, dict) else None
        if isinstance(record, dict) and record.get("by"):
            logins.add(str(record["by"]))
    if not logins:
        return {}
    names: dict[str, str] = {}
    for username, first_name in get_user_model().objects.filter(username__in=logins).values_list(
        "username", "first_name"
    ):
        names[username] = (first_name or "").strip().split(" ")[0] or username
    return names


def build_kds_ticket(ticket_pk: int) -> KDSTicketProjection:
    """Build a single ticket projection (for HTMX partial re-renders)."""
    from shopman.backstage.models import KDSTicket

    ticket = KDSTicket.objects.select_related("kds_instance").get(pk=ticket_pk)
    return _build_ticket(ticket, ticket.kds_instance)


@dataclass(frozen=True)
class KitchenPaperProjection:
    """O card do KDS, para o posto que não tem tela: a Via Cozinha impressa.

    Nasce do MESMO ``_build_ticket`` que monta o card da tela — referência do
    pedido, comanda anterior, nome de chamada, itens, observações e as duas
    notas —, para o papel nunca chamar o pedido por um nome e a tela por outro.
    O que só o papel precisa (nome do posto, canal por extenso, recebimento)
    vem ao lado. Nenhum valor: preço na cozinha não decide nada.
    """

    station_name: str
    card: KDSTicketProjection
    channel_label: str
    #: "ENTREGA" · "RETIRADA" · "" — o mesmo corte do ícone do card
    #: (``fulfillment_icon``), com a retirada dita só quando o pedido a declara.
    fulfillment_label: str
    fired_at_display: str


def build_kitchen_paper(ticket) -> KitchenPaperProjection:
    """O que a Via Cozinha deste ticket imprime (``receipt_escpos.kitchen_ticket``)."""
    from shopman.shop.models import Channel

    instance = ticket.kds_instance
    source = _resolve_ticket_source(ticket)
    card = _build_ticket(ticket, instance, source=source)
    source_data = (getattr(source, "data", None) or {}) if source is not None else {}
    channel_ref = str(getattr(source, "channel_ref", "") or "")
    channel_label = ""
    if channel_ref:
        channel_label = (
            Channel.objects.filter(ref=channel_ref).values_list("name", flat=True).first() or channel_ref
        )
    fulfillment_type = source_data.get("fulfillment_type") or source_data.get("delivery_method", "")
    if fulfillment_type == "delivery":
        fulfillment_label = "ENTREGA"
    elif fulfillment_type == "pickup":
        fulfillment_label = "RETIRADA"
    else:
        fulfillment_label = ""
    return KitchenPaperProjection(
        station_name=str(instance.name),
        card=card,
        channel_label=str(channel_label),
        fulfillment_label=fulfillment_label,
        fired_at_display=_format_time(ticket.created_at),
    )


@dataclass(frozen=True)
class KDSPrintedTicketReceiptProjection:
    """O que o balcão diz depois do "Pronto" de uma estação sem tela.

    O PDV e o leitor de código fecham o ticket sem olhar para ele: o aviso
    precisa dizer, numa linha, QUAL pedido de QUAL estação ficou pronto —
    "Lanches pronto · Ana · #1234". ``completed_now`` separa a baixa de agora
    do ticket que outra porta já tinha concluído.
    """

    ticket_pk: int
    station_name: str
    order_ref: str
    #: O código curto que o balcão fala ("1234", "A47") — o fim do ref.
    order_code: str
    customer_name: str
    status: str
    completed_now: bool
    #: A linha do aviso, pronta: "Lanches pronto · Ana · #1234".
    message: str


def build_printed_ticket_receipt(ticket, *, completed_now: bool) -> KDSPrintedTicketReceiptProjection:
    """O aviso do "Pronto" dado pelo PDV ou pelo leitor (``api/kds.py``)."""
    from shopman.shop.services.operator_orders import short_ref

    instance = ticket.kds_instance
    card = _build_ticket(ticket, instance)
    order_code = short_ref(card.order_ref) if card.order_ref else ""
    verb = "pronto" if completed_now else "já estava pronto"
    parts = [f"{instance.name} {verb}"]
    if card.customer_name:
        parts.append(card.customer_name)
    if order_code:
        parts.append(f"#{order_code}")
    return KDSPrintedTicketReceiptProjection(
        ticket_pk=ticket.pk,
        station_name=str(instance.name),
        order_ref=card.order_ref,
        order_code=order_code,
        customer_name=card.customer_name,
        status=ticket.status,
        completed_now=completed_now,
        message=" · ".join(parts),
    )


def build_kds_customer_status(*, limit: int = 24) -> KDSCustomerStatusProjection:
    """Build a public pickup board without customer names, phones, totals, or addresses.

    Shows committed pickup Orders (READY vs em preparo) **plus** open POS comandas that
    were fired to the kitchen before payment. Those exist only as open ``Session`` rows
    (no ``Order`` yet), so an Order-fed board never showed the customer that their order
    is already being made. Pre-commit comandas join the "em preparo" column with a
    privacy-safe numeric/opaque code only (never the named tab — ``tab_display`` can be a
    customer name on this public screen) and are de-duplicated against committed Orders by
    ``session_key`` so a just-paid comanda is not listed twice.
    """
    from shopman.orderman.models import Session

    # O painel é do DIA: pedido de outro dia que ficou aberto (esquecido em
    # "pronto", ticket nunca finalizado) não é chamada para o cliente do salão,
    # e encomenda de amanhã também não. O dia do pedido é a data do compromisso
    # quando há, senão o dia em que ele nasceu — pelo relógio da loja
    # (``localdate``), o mesmo do quadro do KDS. Mais recentes primeiro.
    today = timezone.localdate()
    day_start = timezone.make_aware(datetime.combine(today, time.min))
    fetch = max(limit * 2, limit)
    orders_qs = (
        Order.objects.filter(
            status__in=[
                Order.Status.ACCEPTED,
                Order.Status.PREPARING,
                Order.Status.READY,
            ]
        )
        .filter(Q(data__delivery_date=today.isoformat()) | Q(created_at__gte=day_start))
        .order_by("-ready_at", "-updated_at", "-created_at")[:fetch]
    )

    preparing: list[KDSCustomerOrderProjection] = []
    ready: list[KDSCustomerOrderProjection] = []
    committed_session_keys: set[str] = set()

    for order in orders_qs:
        if order.session_key:
            committed_session_keys.add(order.session_key)
        if (get_commitment_date(order) or timezone.localdate(order.created_at)) != today:
            continue
        if get_fulfillment_type(order) == "delivery":
            continue
        projection = KDSCustomerOrderProjection(
            ref=order.ref,
            status=order.status,
            status_label="Pronto para retirar" if order.status == Order.Status.READY else "Em preparo",
            updated_at_display=_format_time(order.ready_at or order.updated_at or order.created_at),
        )
        if order.status == Order.Status.READY:
            ready.append(projection)
        else:
            preparing.append(projection)

    # Pre-commit POS comandas fired to the kitchen but not yet paid (open Sessions).
    sessions_qs = Session.objects.filter(state="open", updated_at__gte=day_start).order_by("-updated_at")[:fetch]
    for session in sessions_qs:
        if session.session_key in committed_session_keys:
            continue  # already surfaced as its committed Order (dedup on payment)
        data = session.data or {}
        if not data.get("fired_lines"):
            continue  # nothing fired to the kitchen yet → not "em preparo"
        if (data.get("fulfillment_type") or data.get("delivery_method") or "pickup") == "delivery":
            continue  # pickup/counter only — delivery never shows on the pickup board
        preparing.append(
            KDSCustomerOrderProjection(
                ref=_public_comanda_code(session),
                status=Order.Status.PREPARING,
                status_label="Em preparo",
                updated_at_display=_format_time(session.updated_at),
            )
        )

    # Apply the display budget without starving READY (the pickup priority): keep the
    # ready column first, then fill "em preparo" with whatever slots remain.
    ready = ready[:limit]
    preparing = preparing[: max(0, limit - len(ready))]

    return KDSCustomerStatusProjection(
        preparing=tuple(preparing),
        ready=tuple(ready),
        updated_at_display=_format_time(timezone.now()),
    )


def _public_comanda_code(session) -> str:
    """A privacy-safe public code for a pre-commit POS comanda.

    The pickup board is a PUBLIC screen, so it must never leak a named tab
    (``tab_display`` / ``tab_ref`` can be a customer name like "João"). A comanda
    that has the shape of a NUMBER OF THIS HOUSE shows its unpadded number
    ("1012"); anything else falls back to a short, stable, non-identifying code
    derived from the session key — deterministic so it stays put across the
    board's 10s refresh.

    ⚠️ A pergunta é ``is_numeric_tab_ref``, e NÃO ``isdigit()``. Um telefone tem
    onze dígitos e é ``isdigit()``; o balcão abre comanda com o telefone do cliente
    o tempo todo (é o identificador que ele já pediu para o WhatsApp), e a
    normalização só faz ``zfill`` em numéricos de até oito — acima disso guarda o
    valor cru. Somando: o telefone ia inteiro para a TV do salão, em fonte de 7rem,
    por uma função cujo docstring promete proteger contra exatamente isso.

    O assert-negativo de PII que existia não pegava: ele testa nome, não dígito.
    """
    data = session.data or {}
    for candidate in (data.get("tab_ref"), session.handle_ref):
        text = str(candidate or "").strip()
        if is_numeric_tab_ref(text):
            return display_tab_ref(text)
    digest = hashlib.blake2s(str(session.session_key).encode("utf-8"), digest_size=2).hexdigest().upper()
    return f"#{digest}"


# ── Internals ──────────────────────────────────────────────────────────


_EXIT_STATE_LABELS = {"pending": "na fila", "in_progress": "em preparo", "done": "pronto"}


def exit_station_chips(order: Order, tickets, *, papers) -> tuple[KDSExitStationChipProjection, ...]:
    """Em que pé cada estação está com este pedido (a Saída e o cartão do Gestor).

    Uma régua só para as duas telas da saída: quem falta, o papel da estação sem
    tela, o "Pronto" que a Saída dá por ela e o ticket que volta à cozinha.
    """
    from shopman.shop.services import kds as kds_core

    by_station: dict[int, list] = {}
    for ticket in tickets:
        by_station.setdefault(ticket.kds_instance_id, []).append(ticket)

    recallable = not kds_core.recall_block_reason(order)
    chips: list[KDSExitStationChipProjection] = []
    for station_tickets in by_station.values():
        station = station_tickets[0].kds_instance
        live = [ticket for ticket in station_tickets if ticket.status != "cancelled"]
        if not live:
            continue  # estação que só tem item retirado não espera nada
        cancelled_items = sum(
            len(ticket.items or [])
            for ticket in station_tickets
            if ticket.status == "cancelled" and ticket.acknowledged_at is None
        )
        open_tickets = [ticket for ticket in live if ticket.status in ACTIVE_TICKET_STATUSES]
        if any(ticket.status == "pending" for ticket in open_tickets):
            state = "pending"
        elif open_tickets:
            state = "in_progress"
        else:
            state = "done"
        prints = bool(station.print_terminal_id)
        paper_label = ""
        paper_failed = False
        if prints and open_tickets:
            # O papel mais recente da estação neste pedido é o que está na bancada.
            paper = next(
                (papers[ticket.pk] for ticket in reversed(open_tickets) if ticket.pk in papers),
                None,
            )
            if paper is not None:
                paper_label, paper_failed = paper.label, paper.failed
        recall_ticket_pk = None
        if state == "done" and recallable:
            done = [ticket for ticket in live if ticket.status == "done"]
            recall_ticket_pk = max(done, key=lambda ticket: (ticket.completed_at or ticket.created_at, ticket.pk)).pk
        chips.append(
            KDSExitStationChipProjection(
                station_ref=station.ref,
                station_name=station.name,
                prints=prints,
                state=state,
                state_label=_EXIT_STATE_LABELS[state],
                paper_label=paper_label,
                paper_failed=paper_failed,
                cancelled_items=cancelled_items,
                can_mark_ready=prints and bool(open_tickets),
                recall_ticket_pk=recall_ticket_pk,
            )
        )
    # Quem ainda falta vem primeiro; a ordem entre estações é a do nome.
    chips.sort(key=lambda chip: (chip.state == "done", chip.station_name))
    return tuple(chips)


def kitchen_station_chips(orders) -> dict[str, tuple[KDSExitStationChipProjection, ...]]:
    """As estações de cada pedido, numa leitura só (o quadro do Gestor).

    ``{order.ref: chips}``; pedido sem ticket de cozinha não entra. Duas
    consultas (tickets e papéis) para o quadro inteiro, não uma por cartão.
    """
    from shopman.backstage.models import KDSTicket
    from shopman.backstage.services import kitchen_ticket_print

    keyed = {order.session_key: order for order in orders if order.session_key}
    if not keyed:
        return {}
    tickets_by_key: dict[str, list] = {}
    for ticket in (
        KDSTicket.objects.filter(session_key__in=list(keyed))
        .exclude(kds_instance__type="expedition")
        .select_related("kds_instance")
        .order_by("created_at", "pk")
    ):
        tickets_by_key.setdefault(ticket.session_key, []).append(ticket)
    if not tickets_by_key:
        return {}
    papers = kitchen_ticket_print.paper_states([
        ticket.pk
        for tickets in tickets_by_key.values()
        for ticket in tickets
        if ticket.status in ACTIVE_TICKET_STATUSES and ticket.kds_instance.print_terminal_id
    ])
    chips: dict[str, tuple[KDSExitStationChipProjection, ...]] = {}
    for key, tickets in tickets_by_key.items():
        order = keyed[key]
        order_chips = exit_station_chips(order, tickets, papers=papers)
        if order_chips:
            chips[order.ref] = order_chips
    return chips


def _due_today(source, *, today: date) -> bool:
    """Trabalho de hoje: sem data combinada, ou com a data combinada já chegada."""
    commitment = get_commitment_date(source)
    return commitment is None or commitment <= today


def _resolve_ticket_source(ticket):
    """Resolve a ticket's ``session_key`` to its current source for display.

    Returns the committed Order when it exists, otherwise the open Session
    (comanda fired progressively before commit). Both expose ``data`` /
    ``handle_ref`` / ``channel_ref``; ``ref`` only exists on Order, so the
    pre-commit comanda falls back to its handle (tab label) for the heading.

    An empty ``session_key`` is invalid (a real source always has one): it must
    never resolve, or every empty-key ticket would collapse onto the same
    arbitrary ``filter(session_key="").first()`` source.
    """
    from shopman.orderman.models import Session

    if not ticket.session_key:
        return None

    order = (
        Order.objects.filter(session_key=ticket.session_key)
        .order_by("-id")
        .first()
    )
    if order is not None:
        return order
    return (
        Session.objects.filter(session_key=ticket.session_key, state="open")
        .order_by("-id")
        .first()
    )


def _display_order_refs(source, source_data: dict, handle_ref: str, session_key: str) -> tuple[str, str]:
    """Resolve current order ref plus the former comanda reference.

    Prefers the operator-chosen POS tab label (``tab_display`` — e.g. "Mesa 5",
    or "1012" already stripped of the 8-digit storage padding), so a *named* tab
    surfaces on the KDS instead of a bare id (B6-14). ``tab_display`` lives in the
    open ``Session.data`` (comanda fired before payment) and is copied into
    ``Order.data`` at commit, so it is stable across the fire→pay transition.

    Falls back to the normalized ``tab_ref``, then the order ref / handle / session
    key. Numeric values are shown without their leading-zero padding so the kitchen
    calls "1012", never "00001012" (B2-6). Web/iFood refs (e.g.
    ``WEB-20260713-1012``) are non-numeric and pass through unchanged; the surface
    still splits the {channel-date-} prefix from the called code.
    """
    tab_display = str(source_data.get("tab_display") or "").strip()
    tab_ref = str(source_data.get("tab_ref") or "").strip()
    tab_label = tab_display or (display_tab_ref(tab_ref) if tab_ref else "")
    committed_ref = str(getattr(source, "ref", "") or "").strip()
    if committed_ref:
        return display_tab_ref(committed_ref), tab_label
    return tab_label or display_tab_ref(handle_ref or session_key), ""


def _build_ticket(ticket, instance, *, source=None, names: dict[str, str] | None = None) -> KDSTicketProjection:
    now = timezone.now()
    is_cancelled = ticket.status == "cancelled"
    elapsed_until = ticket.cancelled_at if is_cancelled and ticket.cancelled_at else now
    elapsed = (elapsed_until - ticket.created_at).total_seconds()
    target_sec = instance.target_time_minutes * 60

    if elapsed < target_sec:
        timer_class = "timer-ok"
    elif elapsed < target_sec * 2:
        timer_class = "timer-warning"
    else:
        timer_class = "timer-late"

    if source is None:
        source = _resolve_ticket_source(ticket)
    source_data = (getattr(source, "data", None) or {}) if source is not None else {}
    handle_ref = getattr(source, "handle_ref", "") if source is not None else ""
    order_ref, previous_tab_ref = _display_order_refs(
        source, source_data, handle_ref, ticket.session_key
    )
    channel_ref = getattr(source, "channel_ref", "") if source is not None else ""
    customer_name = (
        source_data.get("customer", {}).get("name", "")
        or handle_ref
        or ""
    )
    fulfillment_type = source_data.get("fulfillment_type") or source_data.get("delivery_method", "")
    is_delivery = fulfillment_type == "delivery"
    fulfillment_icon = "local_shipping" if is_delivery else "storefront"

    raw_items = ticket.items
    if instance.type == "picking":
        raw_items = _add_stock_warnings(raw_items)

    items = tuple(
        KDSItemProjection(
            sku=it.get("sku", ""),
            name=it.get("name", it.get("sku", "")),
            qty=json_quantity(it.get("qty", 1)),
            notes=it.get("notes", ""),
            stock_warning=it.get("stock_warning", ""),
        )
        for it in raw_items
    )

    return KDSTicketProjection(
        pk=ticket.pk,
        order_ref=order_ref,
        channel_icon=CHANNEL_ICONS.get(channel_ref or "", _DEFAULT_CHANNEL_ICON),
        customer_name=customer_name,
        fulfillment_icon=fulfillment_icon,
        created_at_display=_format_datetime(ticket.created_at),
        elapsed_seconds=int(elapsed),
        target_seconds=int(target_sec),
        timer_class=timer_class,
        items=items,
        status=ticket.status,
        previous_tab_ref=previous_tab_ref,
        status_label=_ticket_status_label(ticket.status),
        is_cancelled=is_cancelled,
        cancelled_at_display=_format_time(ticket.cancelled_at),
        completed_at_display=_format_time(ticket.completed_at),
        kitchen_note=str(source_data.get("kitchen_note", "") or ""),
        customer_note=str(source_data.get("order_notes", "") or ""),
        test_order_label=_test_order_label(source) if source is not None else "",
        is_preorder=_is_preorder(source),
        due_time_display=_due_time_display(source_data, is_delivery=is_delivery),
        seen=ticket_seen(ticket),
        **_finish_block(ticket, source),
        **_volumes_fields(source),
        **_start_fields(ticket, source_data, names or {}),
    )


def ticket_seen(ticket) -> bool:
    """Alguém da estação já viu este ticket (K20): o aviso para nas telas dela.

    Ticket aberto: um "Visto" registrado, ou alguém já o iniciou (quem tocou no
    card viu o pedido). Cancelado: o "Visto" precisa ser DEPOIS do cancelamento,
    porque o cancelamento é um aviso novo sobre um pedido que a estação já viu.
    """
    if ticket.status == "cancelled":
        return bool(ticket.seen_at and ticket.cancelled_at and ticket.seen_at >= ticket.cancelled_at)
    if ticket.status == "pending":
        return ticket.seen_at is not None
    return True


def _is_preorder(source) -> bool:
    """Encomenda: o pedido tem data combinada e foi feito antes dela."""
    commitment = get_commitment_date(source)
    created_at = getattr(source, "created_at", None)
    if commitment is None or created_at is None:
        return False
    return timezone.localdate(created_at) < commitment


def _due_time_display(source_data: dict, *, is_delivery: bool) -> str:
    """ "retira às 22:30" / "entrega às 22:30"; vazio sem hora combinada."""
    value = str(
        source_data.get("delivery_time")
        or source_data.get("pickup_time")
        or source_data.get("scheduled_time")
        or ""
    ).strip()[:5]
    if len(value) != 5 or value[2] != ":" or not (value[:2] + value[3:]).isdigit():
        return ""
    return f"{'entrega' if is_delivery else 'retira'} às {value}"


def _volumes_fields(source) -> dict:
    """Os volumes do pedido e a base para declará-los da estação (só pedido de verdade)."""
    if not isinstance(source, Order):
        return {}
    value = (source.data or {}).get("volumes")
    return {
        "volumes": value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0,
        "volumes_order_ref": source.ref,
        "volumes_revision": operator_orders.operational_revision(source, field="volumes"),
    }


def _start_fields(ticket, source_data: dict, names: dict[str, str]) -> dict:
    """Quem iniciou o ticket e quando (``Order.data["kds_started"][str(pk)]``)."""
    started = source_data.get("kds_started")
    record = started.get(str(ticket.pk)) if isinstance(started, dict) else None
    if not isinstance(record, dict):
        return {}
    try:
        at = datetime.fromisoformat(str(record.get("at") or ""))
    except ValueError:
        at = None
    if at is not None and timezone.is_naive(at):
        at = timezone.make_aware(at)
    return {
        "started_by": names.get(str(record.get("by") or ""), str(record.get("by") or "")),
        "started_at_display": _format_time(at) if at is not None else "",
    }


def _finish_block(ticket, source) -> dict[str, str]:
    """Por que o Pronto deste ticket seria recusado agora, na voz da cozinha.

    A mesma régua de ``kds.complete_ticket``: pedido NEW ainda não foi confirmado;
    pedido ACCEPTED só entra em preparo quando o ``payment_gate`` deixa. Comanda
    pré-commit (Session) e pedido já em preparo não têm bloqueio aqui.
    """
    empty = {"finish_block_label": "", "finish_block_reason": ""}
    if ticket.status not in ACTIVE_TICKET_STATUSES or not isinstance(source, Order):
        return empty
    if source.status == Order.Status.NEW:
        return {
            "finish_block_label": "Pedido não confirmado",
            "finish_block_reason": "Pode adiantar; o botão Pronto libera quando o pedido for confirmado.",
        }
    if source.status != Order.Status.ACCEPTED:
        return empty
    from shopman.shop.services import payment_gate

    if not payment_gate.payment_blocks_transition(
        source, current_status=Order.Status.ACCEPTED, target_status=Order.Status.PREPARING
    ):
        return empty
    from shopman.backstage.presentation.status import payment_method_label

    method = str(((source.data or {}).get("payment") or {}).get("method") or "")
    name = payment_method_label(method) if method else "Pagamento"
    return {
        "finish_block_label": f"{name} não confirmado",
        "finish_block_reason": "Pode adiantar; o botão Pronto libera quando o pagamento entrar.",
    }


def _ticket_status_label(status: str) -> str:
    labels = {
        "pending": "Pendente",
        "in_progress": "Em preparo",
        "done": "Concluído",
        "cancelled": "Cancelado",
    }
    return labels.get(status, status)


def _add_stock_warnings(items: list[dict]) -> list[dict]:
    """Add stock_warning to items where physical stock is low or zero."""
    try:
        from shopman.stockman.models import Quant, StockAlert
    except ImportError:
        return items

    skus = [item.get("sku") for item in items if item.get("sku")]
    if not skus:
        return items

    quant_qs = (
        Quant.objects.filter(sku__in=skus)
        .filter(Q(target_date__isnull=True) | Q(target_date__lte=timezone.localdate()))
        .values("sku")
        .annotate(total=Coalesce(Sum("_quantity"), Decimal("0")))
    )
    stock_by_sku = {row["sku"]: row["total"] for row in quant_qs}

    alert_mins: dict[str, Decimal] = {}
    for alert in StockAlert.objects.filter(sku__in=skus, is_active=True):
        alert_mins[alert.sku] = alert.min_quantity

    enriched = []
    for item in items:
        item = dict(item)
        sku = item.get("sku", "")
        available = stock_by_sku.get(sku, Decimal("0"))

        if available <= 0:
            item["stock_warning"] = "Sem estoque"
        elif sku in alert_mins and available < alert_mins[sku]:
            item["stock_warning"] = f"Últimas {int(available)} un."

        enriched.append(item)

    return enriched


def _format_datetime(dt) -> str:
    if dt is None:
        return ""
    local = timezone.localtime(dt)
    return local.strftime("%d/%m às %H:%M")


def _format_time(dt) -> str:
    if dt is None:
        return ""
    local = timezone.localtime(dt)
    return local.strftime("%H:%M")
