"""A Via Cozinha: o posto do KDS que não tem tela recebe os pedidos impressos.

Decisão do dono (26/09/2026): o posto de Lanches não tem tablet, tem uma
impressora térmica de rede (Epson TM-T20X, 48 colunas). Os itens roteados para
ele saem impressos sozinhos, e ligar isso é escolher a impressora no posto
(``KDSInstance.print_terminal``, no Admin das estações KDS). Posto sem
impressora escolhida continua sendo posto de tela, e nada aqui o toca.

## Um papel por ticket, pelo relay

O roteamento não muda: ``shop.services.kds.fire_lines`` cria um ``KDSTicket``
por posto por disparo, como sempre. Este módulo escuta o ``post_save`` do
ticket e, no commit, põe o papel na fila do relay (``PrintJob``, o mesmo das
etiquetas de produção e da DANFE da entrega) para o terminal do posto. O
agente daquele terminal busca o trabalho por HTTPS e o entrega à fila do
sistema operacional — para uma impressora de rede, a fila CUPS
``socket://IP:9100``.

O papel é composto aqui, no servidor, por ``receipt_escpos.kitchen_ticket`` a
partir da mesma projeção do card da tela. O agente é um cano.

## Três momentos imprimem

- **o ticket nasce** vivo (pedido novo, prato disparado da comanda): o papel
  do pedido;
- **o ticket nasce cancelado**: é o comprovante dos itens retirados de um
  ticket que continua vivo (``adapters.kds.unfire_session_lines``). Sai o papel
  CANCELADO só com eles;
- **o ticket vivo é cancelado** (pedido cancelado, comanda que desfez o
  disparo inteiro): sai o CANCELADO — mas só se o papel do pedido pode ter
  saído. Se o papel ainda está na fila, ele é cancelado na fila, e a cozinha
  não recebe nem um nem outro. Se nunca houve papel, não há o que desdizer.

## Idempotência

Cada papel tem uma série determinística por ticket (:func:`series_ref_for`,
``uuid5`` do id do ticket e do momento), e a série é única no banco com a via
1. O ``save`` que roda de novo, o ``on_commit`` duplicado ou o sinal que chega
duas vezes encontram a série e não imprimem outra vez.

## O tempo não vira papel velho

O trabalho vale :data:`AUTO_PRINT_WINDOW`, o mesmo prazo da DANFE da entrega:
um agente que volta de pane não pode imprimir a comanda de horas atrás, que
já foi resolvida de outro jeito (ou nunca vai ser).

## Quando não sai

Impressora do posto sem agente pareado, terminal desativado, agente que recusa
o papel ou que não o busca em :data:`RELAY_GRACE`: abre o alerta
``kitchen_print_failed`` (público pedidos — o posto não tem tela para vê-lo),
com o posto e o pedido no texto. Ele fecha sozinho quando o papel sai.

## O que NÃO acontece ao imprimir

O status do ticket não muda. Decisão do dono (26/09/2026): imprimir não dá
baixa. Quem conclui o ticket da estação sem tela é a **Saída** (o "Pronto" do
chip da estação no card do pedido), o **PDV** (o card do ticket, aberto pela
linha que foi para a cozinha) ou o **leitor de código** da bancada, que lê o
QR impresso no papel (:func:`ticket_code`). O ponto
``KDSInstance.config["on_print"]`` (:data:`ON_PRINT_CONFIG_KEY`) continua com
um único valor, :data:`ON_PRINT_KEEP`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

#: O mesmo prazo da DANFE automática (``order_danfe.AUTO_PRINT_WINDOW``): depois
#: dele, o papel na fila expira em vez de sair.
AUTO_PRINT_WINDOW = timedelta(minutes=10)

#: O agente busca trabalho a cada 2 s. Papel parado na fila além disto é
#: impressora que não está respondendo, e vira alerta.
RELAY_GRACE = timedelta(minutes=2)

#: O alerta do papel que não saiu (``OperatorAlert``, público pedidos).
ALERT_TYPE = "kitchen_print_failed"

#: O que acontece com o ticket quando o papel sai. Decidido pelo dono
#: (26/09/2026): nada — imprimir não dá baixa; quem conclui é a Saída, o PDV ou
#: o leitor de código. O único valor é :data:`ON_PRINT_KEEP`.
ON_PRINT_CONFIG_KEY = "on_print"
ON_PRINT_KEEP = "keep"

#: Os dois papéis possíveis de um ticket.
MOMENT_FIRED = "fired"
MOMENT_CANCELLED = "cancelled"

#: Estados em que o papel pode ter saído. Recusado, expirado ou cancelado na
#: fila nunca virou papel — e aí não há CANCELADO a mandar.
_PAPER_STATES = frozenset({"leased", "spooled", "awaiting_confirmation", "confirmed", "uncertain"})

_SERIES_NAMESPACE = uuid.UUID("5c0b7c9e-7a51-4c8e-9f0e-6b1f2e7c4a10")


def series_ref_for(ticket_pk: int, *, moment: str) -> uuid.UUID:
    """A série do papel deste ticket neste momento: a mesma em toda chamada."""
    return uuid.uuid5(_SERIES_NAMESPACE, f"kds-ticket:{int(ticket_pk)}:{moment}")


def on_print_behavior(instance) -> str:
    """O que a estação faz com o ticket ao imprimir: sempre :data:`ON_PRINT_KEEP`."""
    config = instance.config if isinstance(instance.config, dict) else {}
    value = str(config.get(ON_PRINT_CONFIG_KEY) or ON_PRINT_KEEP)
    if value != ON_PRINT_KEEP:
        logger.warning(
            "kitchen_ticket_print.on_print_unknown",
            extra={"kds_instance": instance.ref, "on_print": value},
        )
    return ON_PRINT_KEEP


# ── O código do papel: o leitor da bancada dá o pronto ────────────────
#
# A Via Cozinha imprime um QR com o código do ticket; o leitor de código no PC
# do PDV (modo teclado, HID) "digita" esse código e o balcão conclui o ticket
# (decisão do dono, 26/09/2026). O código não pode ser o pk puro: qualquer um
# que digitasse "KT-1235" concluiria o lanche do vizinho. Vai o pk E uma
# assinatura (HMAC com a SECRET_KEY) — adivinhar a assinatura de um ticket
# alheio é inviável.
#
# O alfabeto é o que um leitor em modo teclado entrega igual em qualquer
# leiaute (US ou ABNT2): letras, dígitos e o hífen. Nada de barra, dois
# pontos ou acento, que mudam de tecla entre leiautes.

TICKET_CODE_PREFIX = "KT-"
_TICKET_CODE_SIG_LEN = 10
_TICKET_CODE_SALT = "shopman.backstage.kitchen_ticket_code"


def _ticket_code_signature(ticket_pk: int) -> str:
    import base64

    from django.utils.crypto import salted_hmac

    digest = salted_hmac(_TICKET_CODE_SALT, f"kds-ticket:{int(ticket_pk)}", algorithm="sha256").digest()
    return base64.b32encode(digest).decode("ascii")[:_TICKET_CODE_SIG_LEN]


def ticket_code(ticket_pk: int) -> str:
    """O código impresso no QR da Via Cozinha: ``KT-<pk>-<assinatura>``."""
    return f"{TICKET_CODE_PREFIX}{int(ticket_pk)}-{_ticket_code_signature(ticket_pk)}"


def ticket_pk_from_code(code: str) -> int | None:
    """O ticket de um código lido; ``None`` para código que não é desta casa.

    Aceita minúsculas (leitor com Caps Lock trocado) e espaço nas pontas. A
    assinatura é comparada em tempo constante.
    """
    import re

    from django.utils.crypto import constant_time_compare

    pattern = r"KT-(\d{1,12})-([A-Z2-7]{" + str(_TICKET_CODE_SIG_LEN) + "})"
    match = re.fullmatch(pattern, str(code or "").strip().upper())
    if match is None:
        return None
    pk = int(match.group(1))
    if not constant_time_compare(match.group(2), _ticket_code_signature(pk)):
        return None
    return pk


# ── O que a Saída lê do papel ─────────────────────────────────────────


@dataclass(frozen=True)
class PaperState:
    """Em que pé está o papel de um ticket, na voz de quem está na Saída."""

    #: "impresso às 10:42" · "na fila da impressora" · "não imprimiu"
    label: str
    #: O papel não saiu e não vai sair sozinho: a estação precisa ser avisada.
    failed: bool = False


def paper_states(ticket_pks) -> dict[int, PaperState]:
    """O papel do pedido (momento ``fired``) de cada ticket, quando houve papel.

    Ticket sem ``PrintJob`` fica de fora: a estação ganhou a impressora depois
    do disparo, ou o pedido era de teste. A hora do "impresso" é a da resposta
    do agente (``updated_at`` ao chegar num estado de papel) — a mais próxima
    da hora em que a folha caiu na bancada.
    """
    from shopman.backstage.models import PrintJob

    pks = [int(pk) for pk in ticket_pks]
    if not pks:
        return {}
    by_series = {series_ref_for(pk, moment=MOMENT_FIRED): pk for pk in pks}
    out: dict[int, PaperState] = {}
    for job in PrintJob.objects.filter(series_ref__in=list(by_series), copy_number=1).only(
        "series_ref", "status", "updated_at", "confirmed_at"
    ):
        pk = by_series.get(job.series_ref)
        if pk is None:
            continue
        if job.status in _PAPER_STATES:
            when = job.confirmed_at or job.updated_at
            out[pk] = PaperState(label=f"impresso às {timezone.localtime(when).strftime('%H:%M')}")
        elif job.status == PrintJob.Status.QUEUED:
            out[pk] = PaperState(label="na fila da impressora")
        elif job.status in {PrintJob.Status.FAILED, PrintJob.Status.EXPIRED}:
            out[pk] = PaperState(label="não imprimiu", failed=True)
    return out


# ── O gatilho ─────────────────────────────────────────────────────────


def on_ticket_saved(sender, instance, created=False, update_fields=None, raw=False, **kwargs) -> None:
    """``post_save`` do ``KDSTicket``: ticket novo, ou ticket que virou cancelado."""
    if raw:
        return
    becoming_cancelled = (
        not created
        and instance.status == "cancelled"
        and (update_fields is None or "status" in update_fields)
    )
    if not (created or becoming_cancelled):
        return
    # Posto sem impressora: nem agenda o trabalho. A pergunta é barata e evita
    # um on_commit por ticket em todo posto de tela.
    if not _station_prints(instance.kds_instance_id):
        return
    ticket_pk = instance.pk
    transaction.on_commit(lambda: _enqueue_safely(ticket_pk, created=created))


def _station_prints(kds_instance_id) -> bool:
    from shopman.backstage.models import KDSInstance

    return KDSInstance.objects.filter(pk=kds_instance_id, print_terminal__isnull=False).exists()


def _enqueue_safely(ticket_pk: int, *, created: bool) -> None:
    try:
        enqueue(ticket_pk, created=created)
    except Exception:
        # O pedido e o disparo já aconteceram e não se desfazem por causa do
        # papel. O alerta é o aviso; o log guarda o porquê.
        logger.exception("kitchen_ticket_print.enqueue_failed", extra={"ticket_pk": ticket_pk})
        _alert_not_printed(ticket_pk, "O papel não pôde ser composto. Confira a estação no gestor.")


# ── O trabalho ────────────────────────────────────────────────────────


def enqueue(ticket_pk: int, *, created: bool = True):
    """Põe na fila o papel devido a este ticket, uma vez. Devolve o ``PrintJob`` ou ``None``."""
    from shopman.backstage.models import KDSTicket, PrintJob
    from shopman.backstage.services.print_jobs import _destination_health

    problem = ""
    with transaction.atomic():
        ticket = (
            KDSTicket.objects.select_for_update()
            .select_related("kds_instance", "kds_instance__print_terminal")
            .filter(pk=ticket_pk)
            .first()
        )
        if ticket is None:
            return None
        station = ticket.kds_instance
        terminal = station.print_terminal
        if terminal is None:
            return None
        on_print_behavior(station)

        if ticket.status == "cancelled":
            moment = MOMENT_CANCELLED
            if not created and not _paper_may_exist_for(ticket):
                # O papel do pedido nunca saiu (ou ainda está na fila, e é
                # cancelado ali): não há o que desdizer na bancada.
                _cancel_waiting(ticket.pk)
                return None
        else:
            moment = MOMENT_FIRED
            if _is_test_order(ticket):
                # Pedido de teste da homologação não vira trabalho na cozinha
                # (``kds.dispatch`` já o suprime; isto cobre o ticket que chegou
                # por outro caminho).
                return None

        series_ref = series_ref_for(ticket.pk, moment=moment)
        if PrintJob.objects.filter(series_ref=series_ref).exists():
            return None

        label = _terminal_label(terminal)
        if not terminal.is_active:
            problem = f"A impressora da estação {station.name} ({label}) está com o terminal desativado."
        else:
            health = _destination_health(terminal)
            if not health.available:
                problem = (
                    f"A impressora da estação {station.name} ({label}) não tem o agente de impressão "
                    "pareado. No gestor, em Terminais do PDV, emita a credencial do agente."
                )
        if not problem:
            return _create_job(ticket, terminal, moment=moment, series_ref=series_ref)
    _alert_not_printed(ticket_pk, problem)
    return None


def _paper_may_exist_for(ticket) -> bool:
    from shopman.backstage.models import PrintJob

    return PrintJob.objects.filter(
        series_ref=series_ref_for(ticket.pk, moment=MOMENT_FIRED),
        status__in=_PAPER_STATES,
    ).exists()


def _cancel_waiting(ticket_pk: int) -> None:
    """O papel do pedido ainda na fila não sai mais: o ticket foi cancelado."""
    from shopman.backstage.models import PrintJob

    PrintJob.objects.filter(
        series_ref=series_ref_for(ticket_pk, moment=MOMENT_FIRED),
        status=PrintJob.Status.QUEUED,
    ).update(status=PrintJob.Status.CANCELLED, updated_at=timezone.now())


def _create_job(ticket, terminal, *, moment: str, series_ref: uuid.UUID):
    from shopman.backstage.models import PrintJob
    from shopman.backstage.services.receipt_escpos import kitchen_ticket

    payload = kitchen_ticket(ticket, reprint=False)
    order_ref = _order_ref(ticket)
    document = {
        "purpose": "kitchen_ticket",
        "kds_ticket": ticket.pk,
        "kds_instance": ticket.kds_instance.ref,
        "session_key": ticket.session_key,
        "moment": moment,
        "items": ticket.items or [],
        "reprint": False,
    }
    document_bytes = json.dumps(document, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    try:
        with transaction.atomic():
            return PrintJob.objects.create(
                kind=PrintJob.Kind.KITCHEN_TICKET,
                transport=PrintJob.Transport.RELAY,
                status=PrintJob.Status.QUEUED,
                target_terminal=terminal,
                requested_by=None,
                requested_by_ref="sistema",
                requested_station_ref=ticket.kds_instance.ref[:80],
                source_revision=f"kds_ticket:{ticket.pk}:{moment}"[:256],
                document=document,
                document_sha256=hashlib.sha256(document_bytes).hexdigest(),
                payload=payload,
                payload_sha256=hashlib.sha256(payload).hexdigest(),
                payload_size=len(payload),
                label_count=1,
                order_ref=order_ref,
                series_ref=series_ref,
                copy_number=1,
                expires_at=timezone.now() + AUTO_PRINT_WINDOW,
            )
    except IntegrityError:
        # Corrida com outro disparo do mesmo papel: a série única segurou.
        return None


def _is_test_order(ticket) -> bool:
    from shopman.backstage.projections.kds import _resolve_ticket_source
    from shopman.shop.services.order_helpers import is_test_order

    source = _resolve_ticket_source(ticket)
    return source is not None and is_test_order(source)


def _order_ref(ticket) -> str:
    """O pedido dono do papel, quando ele já existe (a comanda aberta ainda não tem)."""
    from shopman.orderman.models import Order

    if not ticket.session_key:
        return ""
    return str(
        Order.objects.filter(session_key=ticket.session_key).order_by("-id").values_list("ref", flat=True).first()
        or ""
    )


def _terminal_label(terminal) -> str:
    return str(getattr(terminal, "label", "") or getattr(terminal, "ref", ""))


# ── Depois que a impressora responde ──────────────────────────────────


def _ticket_pk_of(job) -> int | None:
    document = job.document if isinstance(job.document, dict) else {}
    try:
        return int(document.get("kds_ticket"))
    except (TypeError, ValueError):
        return None


def on_job_changed(job) -> None:
    """O agente respondeu: papel saiu fecha o alerta; recusa ou incerteza o abre."""
    from shopman.backstage.models import PrintJob

    if job.kind != PrintJob.Kind.KITCHEN_TICKET:
        return
    ticket_pk = _ticket_pk_of(job)
    if ticket_pk is None:
        return
    if job.status in {PrintJob.Status.SPOOLED, PrintJob.Status.AWAITING_CONFIRMATION, PrintJob.Status.CONFIRMED}:
        _resolve_alert(ticket_pk)
    elif job.status == PrintJob.Status.FAILED:
        _alert_not_printed(ticket_pk, "A impressora recusou o papel. Confira a bobina e a fila do agente.")
    elif job.status == PrintJob.Status.UNCERTAIN:
        _alert_not_printed(ticket_pk, "Não deu para confirmar se o papel saiu. Confira na bancada.")


def sweep_stale_jobs(*, now=None) -> int:
    """Papel que a impressora do posto não buscou vira alerta.

    Roda no ``maintenance_worker``: reconcilia filas vencidas (viram
    "expirado") e leases vencidos (viram "incerto") e alerta cada ticket cujo
    papel não saiu. O dedupe do alerta segura a repetição.
    """
    from shopman.backstage.models import PrintJob
    from shopman.backstage.services.print_jobs import reconcile_job_state

    now = now or timezone.now()
    alerted = 0
    stale = PrintJob.objects.filter(
        kind=PrintJob.Kind.KITCHEN_TICKET,
        status__in=(PrintJob.Status.QUEUED, PrintJob.Status.LEASED),
        created_at__lte=now - RELAY_GRACE,
    ).order_by("pk")
    for job in stale:
        job = reconcile_job_state(job)
        ticket_pk = _ticket_pk_of(job)
        if ticket_pk is None:
            continue
        if job.status in {PrintJob.Status.QUEUED, PrintJob.Status.EXPIRED}:
            _alert_not_printed(
                ticket_pk,
                "A impressora da estação não buscou o papel. Confira se o computador do agente está ligado.",
            )
            alerted += 1
        elif job.status == PrintJob.Status.UNCERTAIN:
            _alert_not_printed(ticket_pk, "Não deu para confirmar se o papel saiu. Confira na bancada.")
            alerted += 1
    return alerted


def _alert_marker(ticket_pk: int) -> str:
    # O marcador aparece no texto: é por ele que o dedupe e a resolução acham o
    # alerta — a comanda aberta ainda não tem pedido para servir de chave.
    # Termina em ":" para "#1" não casar com "#12".
    return f"Via Cozinha #{int(ticket_pk)}:"


def _alert_not_printed(ticket_pk: int, problem: str) -> None:
    from shopman.backstage.models import KDSTicket
    from shopman.shop.services.observability import create_operator_alert

    ticket = KDSTicket.objects.select_related("kds_instance").filter(pk=ticket_pk).first()
    if ticket is None:
        return
    order_ref = _order_ref(ticket)
    marker = _alert_marker(ticket_pk)
    what = "O CANCELADO" if ticket.status == "cancelled" else "O pedido"
    subject = f"do pedido {order_ref}" if order_ref else f"da comanda {ticket.session_key}"
    create_operator_alert(
        type=ALERT_TYPE,
        severity="warning",
        order_ref=order_ref,
        dedupe_key=marker,
        message=(
            f"{marker} {what} {subject} não saiu na impressora da estação {ticket.kds_instance.name}. "
            f"{problem} Avise a bancada."
        ).replace("  ", " "),
    )


def _resolve_alert(ticket_pk: int) -> None:
    from shopman.shop.adapters import alert as alert_adapter

    alert_adapter.resolve_matching(ALERT_TYPE, message_contains=_alert_marker(ticket_pk), actor="Via Cozinha impressa")
