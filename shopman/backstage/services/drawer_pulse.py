"""A gaveta aberta de qualquer posto, com autoria: o pulso pelo relay.

Decisão do dono (04/10/2026, SUITE-UX §16): no tablet, ao receber em dinheiro, o
atendente leva o dinheiro até o Balcão e, **na frente da gaveta**, toca "Abrir
gaveta do Balcão". A gaveta pendura no RJ11 da impressora do Balcão e abre com
os cinco bytes ``ESC p m t1 t2``; quem os manda é o agente local do PC do Balcão,
que o tablet não alcança. O caminho é o relay de impressão que já existe
(``PrintJob`` ``transport=relay``, o mesmo da DANFE e da Via Cozinha): o
servidor põe um trabalho de **pulso de gaveta** na fila do terminal, o agente
daquele terminal busca e entrega os bytes à fila da impressora. O agente é um
cano: não sabe que aquilo é gaveta.

## Toda abertura deixa linha no livro

Antes de qualquer pulso, uma linha ``drawer_open`` no livro do turno daquela
gaveta, com quem (``operator``, o PIN de quem está no dispositivo que pediu,
seja quem for que esteja logado no PC do Balcão), de qual dispositivo
(``station_device_id``, carimbado pelo escritor único), quando e por quê
(``purpose``: ``sale`` com o pedido, ou ``no_sale`` com o motivo). Sem a linha,
o pulso não sai. A resposta do agente volta ao livro como uma nota filha
(``drawer_pulse_result``): o gerente lê "pulso entregue" ou "não chegou" ao lado
da abertura, no relatório do turno.

## Nunca finge sucesso

O trabalho vale :data:`PULSE_WINDOW`. Um pulso que chegasse minutos depois
abriria a gaveta com ninguém na frente dela, então o que não foi buscado nesse
prazo expira e a tela diz que o Balcão não respondeu. A tela acompanha o
trabalho por :func:`pulse_state` até ``sent`` (o agente entregou à impressora)
ou uma falha nomeada.

## O que NÃO muda

A gaveta continua uma só por terminal e o fechamento continua cego. A abertura
não mexe em dinheiro (efeito zero no saldo); o dinheiro da venda já entrou pela
linha ``sale``.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from shopman.backstage.services.exceptions import POSError

logger = logging.getLogger(__name__)

#: Quanto o pulso espera na fila. O agente busca a cada 2 s; passado isto, ou o
#: agente está fora, ou a rede do Balcão caiu, e abrir depois seria abrir a
#: gaveta sem ninguém na frente.
PULSE_WINDOW = timedelta(seconds=30)

#: Por que a gaveta abriu: venda em dinheiro, ou sem venda (com motivo).
PURPOSE_SALE = "sale"
PURPOSE_NO_SALE = "no_sale"
PURPOSES = (PURPOSE_SALE, PURPOSE_NO_SALE)

#: Como a abertura chega à gaveta: o navegador do Balcão chuta pelo agente da
#: própria máquina (``local``) ou o servidor manda pelo relay (``relay``).
VIA_LOCAL = "local"
VIA_RELAY = "relay"
VIAS = (VIA_LOCAL, VIA_RELAY)

#: A nota filha que guarda a resposta do agente ao pulso.
PULSE_RESULT_EVENT = "drawer_pulse_result"

#: Estado do trabalho → o que a tela diz.
_SENDING = frozenset({"queued", "leased"})
_SENT = frozenset({"spooled", "awaiting_confirmation", "confirmed"})


@dataclass(frozen=True)
class PulseState:
    ref: str
    #: ``sending`` · ``sent`` · ``failed`` · ``expired`` · ``uncertain``
    state: str
    message: str
    terminal_label: str


def relay_capability(terminal) -> dict:
    """O tablet pode pedir o pulso a esta gaveta? Vai para a Projection do PDV.

    ``available`` diz que existe caminho (gaveta pelo agente e credencial do relay
    emitida para o terminal); ``online`` diz que o agente buscou trabalho há
    pouco. A tela usa ``online`` para AVISAR antes ("o Balcão não responde há
    pouco"), nunca para esconder o botão: quem diz se abriu é o trabalho.
    """
    from shopman.backstage.models import PrintAgentCredential
    from shopman.backstage.services.pos_hardware import CashDrawerConfig
    from shopman.backstage.services.print_jobs import LEASE_SECONDS

    label = str(getattr(terminal, "label", "") or getattr(terminal, "ref", "") or "Balcão")
    if terminal is None:
        return {"available": False, "online": False, "terminal_label": label, "reason": "Sem caixa neste posto."}
    drawer = CashDrawerConfig.from_terminal(terminal)
    if not drawer.kicks_by_software:
        return {
            "available": False,
            "online": False,
            "terminal_label": label,
            "reason": f"A gaveta do {label} abre com a chave: o sistema não tem como abrir.",
        }
    credential = (
        PrintAgentCredential.objects.filter(terminal=terminal, is_active=True).order_by("-last_seen_at", "-pk").first()
    )
    if credential is None:
        return {
            "available": False,
            "online": False,
            "terminal_label": label,
            "reason": (
                f"O agente do {label} não tem a credencial do relay. "
                "No gestor, em Terminais do PDV, emita a credencial do agente."
            ),
        }
    online = bool(
        credential.last_seen_at and credential.last_seen_at >= timezone.now() - timedelta(seconds=LEASE_SECONDS)
    )
    return {
        "available": True,
        "online": online,
        "terminal_label": label,
        "reason": "" if online else f"O agente do {label} não responde há pouco. Confira o PC do {label}.",
    }


def open_drawer(
    *,
    operator,
    terminal_ref: str = "",
    purpose: str = PURPOSE_NO_SALE,
    order_ref: str = "",
    reason: str = "",
    via: str = VIA_LOCAL,
):
    """Registra a abertura e, pelo relay, põe o pulso na fila. Devolve ``(entry, job)``.

    ``via=local``: o navegador do Balcão chuta depois do ``ok`` (o caminho de
    sempre), e aqui só nasce a linha. ``via=relay``: a linha e o trabalho do
    pulso nascem na MESMA transação; sem caminho de relay, nada é gravado e a
    recusa diz por quê.
    """
    from shopman.backstage.services.pos import _open_shift_or_raise, _record

    purpose = str(purpose or PURPOSE_NO_SALE).strip()
    if purpose not in PURPOSES:
        raise POSError("Diga por que a gaveta vai abrir: uma venda ou sem venda.")
    via = str(via or VIA_LOCAL).strip()
    if via not in VIAS:
        raise POSError("Caminho de abertura desconhecido.")
    order_ref = str(order_ref or "").strip()[:50]
    reason = str(reason or "").strip()[:120]

    shift = _open_shift_or_raise(operator, terminal_ref)
    terminal = shift.terminal
    if purpose == PURPOSE_SALE:
        if not order_ref:
            raise POSError("Diga de qual venda é o dinheiro.")
        if not _cash_landed(shift, order_ref):
            raise POSError(
                f"A venda {order_ref} não entrou em dinheiro nesta gaveta. "
                "Para abrir sem venda, escolha o motivo."
            )
        if not reason:
            reason = f"Venda {order_ref}"
    elif not reason:
        raise POSError("Informe o motivo da abertura.")

    payload = {"purpose": purpose, "via": via}
    if via == VIA_LOCAL:
        entry = _record("drawer_open", shift=shift, operator=operator, order_ref=order_ref, reason=reason, payload=payload)
        return entry, None

    capability = relay_capability(terminal)
    if not capability["available"]:
        raise POSError(capability["reason"])
    with transaction.atomic():
        job = _create_pulse_job(terminal=terminal, operator=operator, purpose=purpose, order_ref=order_ref)
        payload["pulse_job"] = str(job.ref)
        entry = _record("drawer_open", shift=shift, operator=operator, order_ref=order_ref, reason=reason, payload=payload)
        document = dict(job.document)
        document["entry_id"] = entry.pk
        # O documento congelado aponta para a linha do livro que o autorizou; o
        # hash acompanha (o agente nunca lê o documento, só os bytes).
        job.document = document
        job.document_sha256 = hashlib.sha256(_canonical(document)).hexdigest()
        job.save(update_fields=("document", "document_sha256", "updated_at"))
    return entry, job


def _cash_landed(shift, order_ref: str) -> bool:
    """O dinheiro desta venda entrou NESTA gaveta (linha ``sale`` com valor)?"""
    from shopman.cashman.models import Entry

    return Entry.objects.filter(
        shift=shift,
        kind__in=(Entry.Kind.SALE, Entry.Kind.COD_SETTLED),
        order_ref=order_ref,
        amount_q__gt=0,
    ).exists()


def sale_cash_summary(shift, order_ref: str) -> dict:
    """O dinheiro e o troco da venda, do livro: o cartão "Dinheiro da comanda" lê daqui."""
    from shopman.cashman.models import Entry

    entry = (
        Entry.objects.filter(shift=shift, kind=Entry.Kind.SALE, order_ref=order_ref).order_by("id").first()
    )
    if entry is None:
        return {}
    payload = entry.payload or {}
    return {
        "cash_q": int(entry.amount_q or 0),
        "received_q": int(payload.get("received_q") or 0),
        "change_q": int(payload.get("change_q") or 0),
    }


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _create_pulse_job(*, terminal, operator, purpose: str, order_ref: str):
    from shopman.backstage.models import PrintJob
    from shopman.backstage.services.pos_hardware import CashDrawerConfig
    from shopman.backstage.services.receipt_escpos import drawer_kick

    drawer = CashDrawerConfig.from_terminal(terminal)
    payload = drawer_kick(pin=drawer.pulse_pin, on_ms=drawer.pulse_on_ms, off_ms=drawer.pulse_off_ms)
    document = {
        "purpose": "drawer_pulse",
        "drawer_purpose": purpose,
        "order_ref": order_ref,
        "terminal": terminal.ref,
        "pulse": {"pin": drawer.pulse_pin, "on_ms": drawer.pulse_on_ms, "off_ms": drawer.pulse_off_ms},
    }
    now = timezone.now()
    return PrintJob.objects.create(
        kind=PrintJob.Kind.DRAWER_PULSE,
        transport=PrintJob.Transport.RELAY,
        status=PrintJob.Status.QUEUED,
        target_terminal=terminal,
        requested_by=operator,
        requested_by_ref=str(operator.get_username())[:150],
        requested_station_ref=terminal.ref[:80],
        source_revision=f"drawer_pulse:{terminal.ref}:{now.isoformat()}"[:256],
        document=document,
        document_sha256=hashlib.sha256(_canonical(document)).hexdigest(),
        payload=payload,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        payload_size=len(payload),
        label_count=1,
        order_ref=order_ref,
        copy_number=1,
        expires_at=now + PULSE_WINDOW,
    )


def pulse_state(*, ref, terminal_ref: str) -> PulseState:
    """Em que pé está o pulso. Só o terminal que pediu lê (``terminal_ref`` da estação)."""
    from shopman.backstage.models import PrintJob
    from shopman.backstage.services.print_jobs import reconcile_job_state

    job = (
        PrintJob.objects.select_related("target_terminal")
        .filter(ref=ref, kind=PrintJob.Kind.DRAWER_PULSE, target_terminal__ref=terminal_ref)
        .first()
    )
    if job is None:
        raise POSError("Pulso não encontrado para esta gaveta.")
    job = reconcile_job_state(job)
    _close_in_ledger(job)
    return _state_of(job)


def _state_of(job) -> PulseState:
    label = str(job.target_terminal.label or job.target_terminal.ref) if job.target_terminal_id else "Balcão"
    status = job.status
    if status in _SENDING:
        return PulseState(str(job.ref), "sending", f"Abrindo a gaveta do {label}…", label)
    if status in _SENT:
        return PulseState(str(job.ref), "sent", f"Gaveta do {label} aberta.", label)
    if status == "expired":
        return PulseState(
            str(job.ref),
            "expired",
            f"O {label} não respondeu: a gaveta não abriu. Confira o agente no PC do {label} ou abra na chave.",
            label,
        )
    if status == "uncertain":
        return PulseState(
            str(job.ref),
            "uncertain",
            f"O agente do {label} recebeu o pulso e não confirmou. Olhe a gaveta antes de pedir de novo.",
            label,
        )
    return PulseState(
        str(job.ref),
        "failed",
        f"A impressora do {label} recusou o pulso: a gaveta não abriu. Abra na chave.",
        label,
    )


def on_job_changed(job) -> None:
    """O agente respondeu (ack): a resposta vai ao livro, ao lado da abertura."""
    try:
        _close_in_ledger(job)
    except Exception:
        logger.exception("drawer_pulse.ledger_note_failed", extra={"job": str(job.ref)})


def _close_in_ledger(job) -> None:
    """Uma nota filha da abertura com a resposta final do agente, uma vez só."""
    from shopman.backstage.services.pos import _record
    from shopman.cashman.models import Entry

    state = _state_of(job)
    if state.state == "sending":
        return
    entry_id = (job.document or {}).get("entry_id")
    if not entry_id:
        return
    opening = Entry.objects.filter(pk=entry_id, kind=Entry.Kind.DRAWER_OPEN).select_related("shift").first()
    if opening is None:
        return
    if Entry.objects.filter(parent=opening, kind=Entry.Kind.NOTE, payload__event=PULSE_RESULT_EVENT).exists():
        return
    detail = ""
    attempt = job.attempts.order_by("-sequence").first() if hasattr(job, "attempts") else None
    if attempt is not None and attempt.detail:
        detail = str(attempt.detail)[:200]
    try:
        _record(
            "note",
            shift=opening.shift,
            operator=opening.operator,
            parent=opening,
            reason="Resposta do agente ao pulso da gaveta",
            payload={"event": PULSE_RESULT_EVENT, "status": state.state, "job": str(job.ref), "detail": detail},
        )
    except POSError:
        # Turno fechado entre o pulso e a resposta: NOTE é permitido em turno
        # fechado, então isto é o caso raro de corrida com o próprio registro.
        logger.info("drawer_pulse.ledger_note_skipped", extra={"job": str(job.ref)})
