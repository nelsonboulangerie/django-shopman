"""A DANFE da NFC-e que viaja com a sacola do pedido de entrega.

Decisão do dono (25/09/2026): pedido de ENTREGA sai com a DANFE NFC-e
impressa, dentro da sacola. O papel é o MESMO do balcão, composto por
``receipt_escpos.danfe_nfce`` a partir de ``fiscal_danfe.build_danfe``, e o
carimbo também é o mesmo (``danfe_printed_at``): a partir da segunda
composição o papel sai REIMPRESSÃO, seja qual for a tela que pediu.

## Quem imprime é o servidor, não a tela aberta

A primeira versão imprimia pela estação onde o Gestor estava aberto. Num
tablet sem impressora, nada saía. Agora a DANFE automática sai pelo relay do
servidor (``PrintJob``, o mesmo das etiquetas de produção) para a impressora
do despacho (:func:`danfe_destination`), e o agente dessa impressora a busca
por HTTPS. Onde o Gestor está aberto deixou de importar.

O disparo mora no servidor e tem duas portas, porque a ordem dos fatos varia:

- **a nota autoriza** (o caso normal: na entrega a NFC-e nasce no despacho) →
  o handler fiscal anuncia ``shop.signals.nfce_authorized``;
- **o pedido é despachado** com a nota já autorizada → ``order_changed``.

As duas chamam :func:`enqueue_auto_print`, que decide sob lock do pedido e
grava o carimbo junto com o trabalho: quem chega depois encontra o carimbo e
não imprime outra vez.

## O tempo não vira portão

Regra dura do dono: **expedição sem NFC-e só AVISA, nunca segura a sacola**.
Nada aqui pergunta "pode despachar?". Depois de :data:`AUTO_PRINT_WINDOW` do
despacho a sacola já foi embora, e a DANFE não sai mais sozinha; o trabalho
também expira nesse prazo, para um agente que volta à vida não cuspir papel de
pedido que já está na rua.

## Quando não sai

Sem impressora de despacho, impressora que não busca o trabalho em
:data:`RELAY_GRACE`, ou agente que recusa: o card diz "DANFE não impressa" com
o motivo e o botão, e um ``OperatorAlert`` (``danfe_print_failed``, público
pedidos, aviso e não crítico) leva ao card. O alerta fecha sozinho quando a
DANFE sai.

## O botão do card

:func:`print_on_demand` manda pela mesma impressora do despacho. Sem ela, e
só então, devolve os bytes para a página relaiar ao agente local da estação
(o caminho da primeira versão), para o balcão que ainda não pareou o relay
continuar imprimindo.

## O que fica de fora

- **Retirada**: a DANFE fica no card (o cliente pode pedir no balcão), mas não
  sai sozinha.
- **iFood**: a sacola do iFood segue a regra do iFood; nada aqui a toca.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

#: A chave do carimbo em ``Order.data``, a mesma do PDV (data-schemas.md).
PRINT_STAMP_KEY = "danfe_printed_at"

#: Até quando, depois do despacho, a DANFE ainda sai sozinha.
AUTO_PRINT_WINDOW = timedelta(minutes=10)

#: O agente busca trabalho a cada 2 s. Trabalho parado na fila além disto é
#: impressora que não está respondendo, e o card passa a dizer isso.
RELAY_GRACE = timedelta(minutes=2)

#: Marca, em ``Terminal.metadata["station"]``, a impressora que recebe a DANFE
#: das entregas. Escrita pelo Admin (Terminais do PDV).
DESTINATION_FLAG = "prints_delivery_danfe"

#: O terminal que ``cashman.Terminal.default()`` cria: o balcão da loja de um
#: PDV só. Sem nenhuma impressora marcada, a DANFE vai para ele.
COUNTER_TERMINAL_REF = "pdv-main"

#: O alerta de DANFE que não saiu (público pedidos, ``OperatorAlert``).
ALERT_TYPE = "danfe_print_failed"

#: Estados da DANFE no card do Gestor.
STATE_PRINTED = "printed"
STATE_SENDING = "sending"
STATE_NOT_PRINTED = "not_printed"
STATE_ON_DISPATCH = "on_dispatch"
STATE_AVAILABLE = "available"


def _is_ifood(order) -> bool:
    from shopman.shop.services.ifood_ingest import IFOOD_CHANNEL_REF

    return (getattr(order, "channel_ref", "") or "") == IFOOD_CHANNEL_REF


def _is_delivery(order) -> bool:
    from shopman.shop.services.order_helpers import get_fulfillment_type

    return get_fulfillment_type(order) == "delivery"


# ── Para onde vai ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class DanfeDestination:
    """A impressora do despacho, resolvida no servidor."""

    terminal: object | None
    label: str = ""
    problem: str = ""

    @property
    def available(self) -> bool:
        return self.terminal is not None and not self.problem


def _terminal_label(terminal) -> str:
    return str(getattr(terminal, "label", "") or getattr(terminal, "ref", ""))


def _is_marked(terminal) -> bool:
    metadata = terminal.metadata if isinstance(terminal.metadata, dict) else {}
    station = metadata.get("station") if isinstance(metadata.get("station"), dict) else {}
    return station.get(DESTINATION_FLAG) is True


def danfe_destination() -> DanfeDestination:
    """A impressora que recebe a DANFE das entregas.

    Na ordem: a marcada em Terminais do PDV ("Imprime a DANFE das entregas");
    sem marca, o balcão (``pdv-main``); sem balcão com agente, a única
    impressora da loja com agente pareado. Imprimir pelo servidor exige a
    credencial do agente de impressão (``PrintAgentCredential``): é ela que
    deixa o agente buscar o trabalho.
    """
    from shopman.cashman.models import Terminal

    from shopman.backstage.models import PrintAgentCredential

    with_relay = set(
        PrintAgentCredential.objects.filter(is_active=True, terminal__is_active=True).values_list(
            "terminal_id", flat=True
        )
    )
    terminals = list(Terminal.objects.filter(is_active=True).order_by("ref"))
    marked = [terminal for terminal in terminals if _is_marked(terminal)]
    if marked:
        terminal = marked[0]
        label = _terminal_label(terminal)
        if terminal.pk not in with_relay:
            return DanfeDestination(
                terminal,
                label,
                f"A impressora de {label} está marcada para a DANFE, mas o agente de impressão dela "
                "não está pareado. No gestor, em Terminais do PDV, emita a credencial do agente.",
            )
        return DanfeDestination(terminal, label)
    eligible = [terminal for terminal in terminals if terminal.pk in with_relay]
    counter = next((terminal for terminal in eligible if terminal.ref == COUNTER_TERMINAL_REF), None)
    if counter is not None:
        return DanfeDestination(counter, _terminal_label(counter))
    if len(eligible) == 1:
        return DanfeDestination(eligible[0], _terminal_label(eligible[0]))
    if not eligible:
        return DanfeDestination(
            None,
            "",
            "Nenhuma impressora recebe a DANFE pelo servidor. No gestor, em Terminais do PDV, "
            "emita a credencial do agente de impressão do balcão.",
        )
    return DanfeDestination(
        None,
        "",
        "Há mais de uma impressora com agente e nenhuma marcada para a DANFE. No gestor, em "
        "Terminais do PDV, marque \"Imprime a DANFE das entregas\" em uma delas.",
    )


# ── O que o pedido sabe ───────────────────────────────────────────────


@dataclass(frozen=True)
class DanfeState:
    """O que o servidor sabe da DANFE de um pedido, sem olhar a impressora."""

    #: Há nota autorizada e o Gestor pode imprimi-la (o iFood fica de fora).
    printable: bool = False
    #: A DANFE já foi composta uma vez (a próxima é REIMPRESSÃO).
    printed: bool = False
    #: A DANFE deve sair sozinha agora (entrega despachada há pouco, sem carimbo).
    auto_print: bool = False


def danfe_state(order, *, now=None) -> DanfeState:
    """A DANFE deste pedido: existe? já saiu? deve sair sozinha agora?"""
    from shopman.orderman.models import Order

    data = getattr(order, "data", None) or {}
    if _is_ifood(order) or not data.get("nfce_access_key") or data.get("nfce_cancelled"):
        return DanfeState()
    printed = bool(data.get(PRINT_STAMP_KEY))
    dispatched_at = getattr(order, "dispatched_at", None)
    now = now or timezone.now()
    auto_print = (
        not printed
        and order.status == Order.Status.DISPATCHED
        and _is_delivery(order)
        and dispatched_at is not None
        and now - dispatched_at <= AUTO_PRINT_WINDOW
    )
    return DanfeState(printable=True, printed=printed, auto_print=auto_print)


# ── O card ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DanfeCard:
    """A linha da DANFE no card do Gestor."""

    printable: bool = False
    printed: bool = False
    #: ``printed`` · ``sending`` · ``not_printed`` · ``on_dispatch`` · ``available``.
    state: str = ""
    #: Por que não saiu, com o que fazer. Vazio fora de ``not_printed``.
    problem: str = ""


@dataclass(frozen=True)
class DanfeReads:
    """A leitura em lote do quadro: a última tentativa de cada pedido e o destino."""

    jobs: dict
    destination: DanfeDestination | None


def read_for(orders) -> DanfeReads:
    """Uma consulta para o quadro inteiro, só dos pedidos que têm nota."""
    from shopman.backstage.models import PrintJob

    refs = [
        order.ref
        for order in orders
        if (order.data or {}).get("nfce_access_key") and not _is_ifood(order)
    ]
    if not refs:
        return DanfeReads(jobs={}, destination=None)
    latest: dict = {}
    for job in (
        PrintJob.objects.filter(kind=PrintJob.Kind.ORDER_DANFE, order_ref__in=refs)
        .select_related("target_terminal")
        .order_by("order_ref", "-created_at", "-pk")
    ):
        latest.setdefault(job.order_ref, job)
    return DanfeReads(jobs=latest, destination=danfe_destination())


def _job_problem(job, *, now) -> tuple[str, str]:
    """(estado, motivo) da última tentativa pelo relay."""
    from shopman.backstage.models import PrintJob

    label = _terminal_label(job.target_terminal) if job.target_terminal else "do despacho"
    status = job.status
    if status in {PrintJob.Status.SPOOLED, PrintJob.Status.AWAITING_CONFIRMATION, PrintJob.Status.CONFIRMED}:
        return STATE_PRINTED, ""
    if status in {PrintJob.Status.QUEUED, PrintJob.Status.LEASED}:
        if status == PrintJob.Status.QUEUED and now - job.created_at > RELAY_GRACE:
            return STATE_NOT_PRINTED, (
                f"A impressora de {label} não buscou a DANFE. Confira se o computador dela está ligado."
            )
        return STATE_SENDING, ""
    if status == PrintJob.Status.UNCERTAIN:
        return STATE_NOT_PRINTED, (
            f"Não deu para confirmar se a DANFE saiu na impressora de {label}. Confira o papel; "
            "se não saiu, imprima de novo."
        )
    if status == PrintJob.Status.FAILED:
        return STATE_NOT_PRINTED, f"A impressora de {label} recusou a DANFE. Confira o papel e imprima de novo."
    return STATE_NOT_PRINTED, f"A impressora de {label} não imprimiu a DANFE a tempo."


def card_state(order, *, reads: DanfeReads | None = None, now=None) -> DanfeCard:
    """O que o card mostra: saiu, está saindo, não saiu (e por quê), ou está à mão."""
    from shopman.orderman.models import Order

    now = now or timezone.now()
    base = danfe_state(order, now=now)
    if not base.printable:
        return DanfeCard()
    if reads is None:
        reads = read_for([order])
    job = reads.jobs.get(order.ref)
    if job is not None:
        state, problem = _job_problem(job, now=now)
        return DanfeCard(printable=True, printed=base.printed, state=state, problem=problem)
    if base.printed:
        # Composta por outra rota (PDV, ou o agente local da estação).
        return DanfeCard(printable=True, printed=True, state=STATE_PRINTED)
    if not _is_delivery(order):
        return DanfeCard(printable=True, state=STATE_AVAILABLE)
    if order.status in (Order.Status.NEW, Order.Status.ACCEPTED, Order.Status.PREPARING, Order.Status.READY):
        return DanfeCard(printable=True, state=STATE_ON_DISPATCH)
    if base.auto_print:
        destination = reads.destination or danfe_destination()
        if not destination.available:
            return DanfeCard(printable=True, state=STATE_NOT_PRINTED, problem=destination.problem)
        # O disparo está a caminho (o sinal roda no commit da mesma transação).
        return DanfeCard(printable=True, state=STATE_SENDING)
    return DanfeCard(printable=True, state=STATE_NOT_PRINTED)


# ── Composição e trabalho ─────────────────────────────────────────────


class DanfeRefused(Exception):
    """A DANFE não sai por esta rota, com a frase para o operador e o código."""

    def __init__(self, message: str, *, code: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


@dataclass(frozen=True)
class DanfePrint:
    """O resultado do botão: foi para a impressora do despacho, ou volta os bytes."""

    via: str
    reprint: bool
    target_label: str = ""
    payload: bytes = b""


#: Estados em que o papel pode ter saído. Trabalho recusado pelo agente, que
#: expirou na fila ou foi cancelado nunca virou papel, e a próxima composição
#: não é reimpressão.
_PAPER_STATES = frozenset({"leased", "spooled", "awaiting_confirmation", "confirmed", "uncertain"})


def _paper_may_exist(order) -> bool:
    from shopman.backstage.models import PrintJob

    if not (order.data or {}).get(PRINT_STAMP_KEY):
        return False
    jobs = PrintJob.objects.filter(kind=PrintJob.Kind.ORDER_DANFE, order_ref=order.ref)
    if not jobs.exists():
        # O carimbo veio do PDV ou do agente local da estação: houve papel.
        return True
    return jobs.filter(status__in=_PAPER_STATES).exists()


def _compose(order_ref: str, *, reprint: bool) -> bytes:
    from shopman.backstage.services.receipt_escpos import danfe_nfce
    from shopman.shop.views.fiscal_danfe import build_danfe

    return danfe_nfce(build_danfe(order_ref), reprint=reprint)


def _stamp(order) -> None:
    if (order.data or {}).get(PRINT_STAMP_KEY):
        return
    data = dict(order.data or {})
    data[PRINT_STAMP_KEY] = timezone.now().isoformat()
    order.data = data
    order.save(update_fields=["data", "updated_at"])


def _create_job(order, destination: DanfeDestination, *, payload: bytes, reprint: bool, actor=None, station_ref=""):
    from shopman.backstage.models import PrintJob

    access_key = str((order.data or {}).get("nfce_access_key") or "")
    document = {
        "purpose": "delivery_danfe",
        "order_ref": order.ref,
        "nfce_access_key": access_key,
        "reprint": reprint,
    }
    document_bytes = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return PrintJob.objects.create(
        kind=PrintJob.Kind.ORDER_DANFE,
        transport=PrintJob.Transport.RELAY,
        status=PrintJob.Status.QUEUED,
        target_terminal=destination.terminal,
        requested_by=actor if getattr(actor, "pk", None) else None,
        requested_by_ref=(actor.get_username() if getattr(actor, "pk", None) else "sistema")[:150],
        requested_station_ref=str(station_ref or "")[:80],
        source_revision=f"nfce:{access_key}"[:256],
        document=document,
        document_sha256=hashlib.sha256(document_bytes).hexdigest(),
        payload=payload,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        payload_size=len(payload),
        label_count=1,
        order_ref=order.ref,
        expires_at=timezone.now() + AUTO_PRINT_WINDOW,
    )


def _cancel_waiting_jobs(order_ref: str) -> None:
    """O botão substitui a tentativa que ainda está na fila: um papel, não dois."""
    from shopman.backstage.models import PrintJob

    PrintJob.objects.filter(
        kind=PrintJob.Kind.ORDER_DANFE, order_ref=order_ref, status=PrintJob.Status.QUEUED
    ).update(status=PrintJob.Status.CANCELLED, updated_at=timezone.now())


def enqueue_auto_print(order_ref: str):
    """A DANFE que ninguém pediu: sai uma vez, pela impressora do despacho.

    Chamada no commit da autorização da nota e do despacho. Sob lock do pedido:
    a segunda chamada encontra o carimbo e não faz nada. Sem impressora de
    despacho, nada é carimbado (nenhum papel foi composto) e o alerta avisa.
    Devolve o ``PrintJob`` criado, ou ``None``.
    """
    from shopman.orderman.models import Order

    destination = None
    with transaction.atomic():
        order = Order.objects.select_for_update().filter(ref=order_ref).first()
        if order is None or not danfe_state(order).auto_print:
            return None
        destination = danfe_destination()
        if destination.available:
            payload = _compose(order.ref, reprint=False)
            _stamp(order)
            job = _create_job(order, destination, payload=payload, reprint=False)
            transaction.on_commit(lambda: _announce(order_ref))
            return job
    _alert_not_printed(order_ref, destination.problem)
    _announce(order_ref)
    return None


def print_on_demand(order_ref: str, *, actor=None, station_ref: str = "", local_agent: bool = False) -> DanfePrint:
    """O botão do card: imprimir, ou reimprimir, a DANFE do pedido.

    Vai pela impressora do despacho. Sem ela, devolve os bytes para a página
    relaiar ao agente local desta estação (``local_agent``); sem nenhum dos
    dois, recusa com o motivo e não carimba nada.
    """
    from shopman.orderman.models import Order

    with transaction.atomic():
        order = Order.objects.select_for_update().filter(ref=order_ref).first()
        if order is None:
            raise DanfeRefused("Pedido não encontrado.", code="not_found", status=404)
        if _is_ifood(order):
            raise DanfeRefused(
                "A sacola do iFood segue a regra do iFood: a DANFE não sai pelo Gestor.",
                code="danfe_ifood",
            )
        if not danfe_state(order).printable:
            raise DanfeRefused("A NFC-e deste pedido ainda não foi autorizada.", code="danfe_not_authorized")
        destination = danfe_destination()
        if not destination.available and not local_agent:
            raise DanfeRefused(
                f"A DANFE não tem para onde sair. {destination.problem}", code="danfe_no_printer"
            )
        reprint = _paper_may_exist(order)
        payload = _compose(order.ref, reprint=reprint)
        _stamp(order)
        if destination.available:
            _cancel_waiting_jobs(order.ref)
            _create_job(order, destination, payload=payload, reprint=reprint, actor=actor, station_ref=station_ref)
            transaction.on_commit(lambda: _announce(order_ref))
            return DanfePrint(via="relay", reprint=reprint, target_label=destination.label)
    # Pelo agente local da estação: a página entrega os bytes. O carimbo já
    # conta como papel; o alerta de "não saiu" deixa de valer.
    _resolve_alert(order_ref)
    return DanfePrint(via="local", reprint=reprint, payload=payload)


# ── Depois que a impressora responde ──────────────────────────────────


def on_job_changed(job) -> None:
    """O agente respondeu (ou a fila venceu): fecha ou abre o alerta e avisa o quadro."""
    from shopman.backstage.models import PrintJob

    if job.kind != PrintJob.Kind.ORDER_DANFE or not job.order_ref:
        return
    state, problem = _job_problem(job, now=timezone.now())
    if state == STATE_PRINTED:
        _resolve_alert(job.order_ref)
    elif state == STATE_NOT_PRINTED:
        _alert_not_printed(job.order_ref, problem)
    _announce(job.order_ref)


def sweep_stale_jobs(*, now=None) -> int:
    """A impressora que não buscou a DANFE vira alerta (o card já diz na hora).

    Roda no ``maintenance_worker``. Reconcilia leases vencidos (viram
    "incerto") e filas vencidas (viram "expirado") e alerta cada pedido cuja
    última tentativa não virou papel.
    """
    from shopman.backstage.models import PrintJob
    from shopman.backstage.services.print_jobs import reconcile_job_state

    now = now or timezone.now()
    alerted = 0
    stale = PrintJob.objects.filter(
        kind=PrintJob.Kind.ORDER_DANFE,
        status__in=(PrintJob.Status.QUEUED, PrintJob.Status.LEASED),
        created_at__lte=now - RELAY_GRACE,
    ).order_by("pk")
    for job in stale:
        job = reconcile_job_state(job)
        state, problem = _job_problem(job, now=now)
        if state == STATE_NOT_PRINTED:
            _alert_not_printed(job.order_ref, problem)
            alerted += 1
    return alerted


def _alert_not_printed(order_ref: str, problem: str) -> None:
    from shopman.shop.services.observability import create_operator_alert

    create_operator_alert(
        type=ALERT_TYPE,
        severity="warning",
        order_ref=order_ref,
        # A chave aparece no texto: assim o dedupe acha o alerta sem o sufixo
        # técnico que ``create_operator_alert`` pendura quando ela falta.
        dedupe_key=f"DANFE da entrega {order_ref}",
        message=(
            f"A DANFE da entrega {order_ref} não foi impressa. {problem} "
            "Imprima pelo card do pedido antes de a sacola sair."
        ).replace("  ", " "),
    )


def _resolve_alert(order_ref: str) -> None:
    from shopman.shop.adapters import alert as alert_adapter

    alert_adapter.resolve(ALERT_TYPE, order_ref=order_ref, actor="DANFE impressa")


def _announce(order_ref: str) -> None:
    """O quadro relê: a linha da DANFE mudou."""
    from shopman.orderman.models import Order

    from shopman.shop.handlers._sse_emitters import emit_danfe_update

    order = Order.objects.filter(ref=order_ref).first()
    if order is not None:
        emit_danfe_update(order)


# ── Os gatilhos ───────────────────────────────────────────────────────


def _enqueue_safely(order_ref: str) -> None:
    try:
        enqueue_auto_print(order_ref)
    except Exception:
        # A nota e o despacho já aconteceram e não podem desfazer por causa do
        # papel. O card diz "DANFE não impressa" e o botão continua lá.
        logger.exception("order_danfe.auto_print_failed", extra={"order_ref": order_ref})


def on_nfce_authorized(sender, order=None, **kwargs) -> None:
    """A nota autorizou: se a entrega já saiu, a DANFE vai atrás dela."""
    ref = getattr(order, "ref", "")
    if ref:
        transaction.on_commit(lambda: _enqueue_safely(ref))


def on_order_changed(sender, order=None, event_type="", **kwargs) -> None:
    """A entrega foi despachada com a nota já autorizada: a DANFE sai agora."""
    from shopman.orderman.models import Order

    if order is None or event_type != "status_changed" or order.status != Order.Status.DISPATCHED:
        return
    if not (order.data or {}).get("nfce_access_key"):
        return
    ref = order.ref
    transaction.on_commit(lambda: _enqueue_safely(ref))
