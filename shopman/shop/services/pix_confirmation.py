"""
PIX confirmation — canonical handler shared by every ingress path.

The same body of code runs for:

1. **Real EFI webhook.** ``EfiPixWebhookView`` authenticates the request
   (mTLS + shared token) and delegates to :func:`confirm_pix`.
2. **Mock PIX backend.** Tests may opt in to a ``mock_pix.confirm`` directive;
   the ``MockPixConfirmHandler`` fires after the configured delay and calls
   :func:`confirm_pix`. Manual dev flows use the explicit dev confirmation
   button instead, so refreshes never pay a PIX by themselves.
3. **Tests.** Integration tests call :func:`confirm_pix` directly to
   exercise the downstream flow without going through HTTP.

There is no environment branch here — dev and prod run the same code. The
only thing that differs is *who calls it*: EFI's servers in production, an
explicit dev action, or an opt-in mock directive in tests.

Contrato do dinheiro (o que este módulo promete)
------------------------------------------------

Um Pix confirmado é dinheiro que JÁ está na conta da loja. A partir daí só
existem três desfechos honestos, e nenhum deles é silêncio:

* **cobre a cobrança** → captura no Payman e o pedido segue (``on_paid``);
* **não cobre** → NÃO captura (o Payman só aceita uma captura por intent, e
  capturar a menos queimaria a cobrança para o resto do pagamento), registra
  o recebimento no pedido e alerta;
* **a cobrança não pode mais receber** (cancelada, falha, expirada, ou nem
  existe no livro) → o dinheiro é registrado num intent próprio, estornado
  quando o pedido está cancelado, e alertado sempre.

Três defeitos concretos moram nessas regras, e o comentário de cada um está
no ponto onde ele era possível:

1. Pix que caía DEPOIS do cancelamento era descartado em silêncio (o intent
   ``cancelled`` não entrava em nenhum ramo de captura), e o alerta que sobrava
   dizia ao operador que o cliente havia pago A MENOS e que o pedido "segue
   aguardando pagamento" — com o pedido cancelado e o dinheiro na conta, sem
   estorno.
2. Pix parcial capturava o intent pelo valor recebido. Como o Payman admite
   uma captura por intent, o segundo Pix não tinha mais onde entrar: o cliente
   desembolsava R$ 9,00 e o livro registrava R$ 1,00.
3. Sem intent para o ``txid``, o pedido era procurado por ``icontains`` — um
   ``txid`` que fosse PEDAÇO de qualquer ``intent_ref`` casava (``"PAY-"`` casa
   com todos) e marcava o pedido de outro cliente como pago, usando como prova
   de suficiência o valor declarado pelo próprio webhook.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from shopman.orderman.models import Order

logger = logging.getLogger(__name__)

#: Cobranças que não recebem mais. O Payman recusa captura nelas
#: (``invalid_transition`` no ``capture``, ``reconciliation_terminal_drift`` na
#: reconciliação) e essa recusa é um CONTRATO, não um erro a engolir: o
#: dinheiro entrou de qualquer forma e precisa de outro lugar no livro.
_DEAD_CHARGE_STATUSES = frozenset({"cancelled", "failed"})

#: Janela de debounce dos alertas. O valor recebido entra na chave de dedupe
#: (``message_contains``): um segundo Pix que MUDA o quadro alerta de novo, em
#: vez de ficar escondido atrás do alerta do primeiro.
_ALERT_DEBOUNCE = timedelta(minutes=15)


def confirm_pix(*, txid: str, e2e_id: str = "", amount: str = "") -> None:
    """Registrar um Pix recebido e, se ele cobre a cobrança, despachar ``on_paid``.

    Parameters
    ----------
    txid:
        The PIX transaction id. Used to locate the ``PaymentIntent`` via
        ``PaymentService.get_by_gateway_id``.
    e2e_id:
        End-to-end transaction id from the PIX network. É a identidade do Pix
        na rede, e por isso a chave do recibo: dois Pix distintos somam, o
        mesmo Pix reapresentado não conta duas vezes.
    amount:
        Paid amount as a decimal string (``"12.50"``) — the gateway's own
        wire format. (EFI calls this field ``valor``; the name stops at the
        webhook.) Ausência ou formato ilegível NÃO é presumido como "pagou o
        total": vira indeterminação, que espera e grita.

    Nunca levanta por problema de conteúdo (valor ausente, valor a mais,
    cobrança morta, pedido desconhecido). O webhook da Efí só para de
    reentregar em 2xx, então uma exceção determinística aqui viraria uma
    reentrega infinita da MESMA falha, com o pedido travado para sempre.
    Falha de infraestrutura continua subindo: essa a reentrega cura.
    """
    from shopman.payman import PaymentService

    reported_q = _reported_amount_q(amount, txid=txid)
    db_intent = _intent_for_pix_txid(PaymentService, txid)

    if db_intent is None:
        _confirm_pix_without_charge(txid=txid, e2e_id=e2e_id, reported_q=reported_q)
        return

    order = _order_for_charge(db_intent)
    if order is None:
        logger.warning(
            "pix_confirmation: intent %s pago mas pedido %s não encontrado",
            db_intent.ref, db_intent.order_ref,
        )
        _alert(
            db_intent.order_ref,
            alert_type="payment_reconciliation_failed",
            severity="critical",
            message=(
                f"Recebemos um PIX de {_money(reported_q)} da cobrança {db_intent.ref}, "
                f"mas o pedido {db_intent.order_ref} não existe mais. "
                "Confira no gateway e concilie à mão."
            ),
        )
        return

    if db_intent.status in _DEAD_CHARGE_STATUSES:
        _confirm_pix_on_dead_charge(
            order, db_intent, txid=txid, e2e_id=e2e_id, reported_q=reported_q,
        )
        return

    _confirm_pix_on_live_charge(
        order, db_intent, txid=txid, e2e_id=e2e_id, reported_q=reported_q,
    )


# ── cobrança viva (pending / authorized / captured) ──


def _confirm_pix_on_live_charge(order, db_intent, *, txid, e2e_id, reported_q) -> None:
    """O caminho normal: a cobrança está de pé e o Pix vem cobri-la."""
    received_q = _record_pix_receipt(order, txid=txid, e2e_id=e2e_id, amount_q=reported_q)
    authorized_q = int(db_intent.amount_q or 0)

    if received_q is None:
        # Webhook autenticado SEM o valor pago. Isto já foi lido como "cobre o
        # total" (o parse caía num default = valor da cobrança) e despachava
        # ``on_paid``: pedido entregue sem que ninguém conferisse um centavo.
        # Ausência de valor não é prova de pagamento, é indeterminação.
        logger.warning(
            "pix_confirmation: Pix sem valor legível order=%s txid=%s", order.ref, txid,
        )
        _alert(
            order.ref,
            alert_type="payment_reconciliation_failed",
            severity="error",
            message=(
                f"PIX do pedido {order.ref} chegou sem o valor pago. "
                "Nada foi capturado e o pedido segue aguardando pagamento; "
                "confira o valor no gateway e confirme à mão."
            ),
            debounce_on=f"PIX do pedido {order.ref} chegou sem o valor pago",
        )
        return

    if received_q < authorized_q:
        # NÃO capturar é o conserto. O Payman admite UMA captura por intent:
        # capturar R$ 1,00 de uma cobrança de R$ 9,00 mandava o intent para
        # ``captured`` e o segundo Pix não tinha mais onde entrar. Deixando a
        # cobrança de pé, o Pix que completa o valor captura o total.
        logger.warning(
            "pix_confirmation: Pix abaixo do autorizado order=%s recebido_q=%s autorizado_q=%s",
            order.ref, received_q, authorized_q,
        )
        _alert_insufficient(order, received_q=received_q, expected_q=authorized_q)
        return

    outcome = _capture_charge(db_intent, txid=txid, e2e_id=e2e_id)
    if outcome == "dead":
        # A cobrança morreu entre a leitura e a captura (cancelamento em
        # paralelo, ou cobrança expirada). Mesmo desfecho do ramo de cobrança
        # morta: o dinheiro entrou e não pode sumir.
        _confirm_pix_on_dead_charge(
            order, db_intent, txid=txid, e2e_id=e2e_id, reported_q=reported_q,
        )
        return

    captured_q = _captured_balance_q(order, db_intent)
    if captured_q is None or captured_q < int(getattr(order, "total_q", 0) or 0):
        # Capturamos, mas o livro não cobre o pedido (cobrança menor que o
        # total, pedido alterado depois do QR). A prova de suficiência é
        # SEMPRE o Payman, nunca o valor que o webhook declarou.
        logger.warning(
            "pix_confirmation: captura insuficiente para o pedido order=%s capturado_q=%s",
            order.ref, captured_q,
        )
        _alert_insufficient(
            order,
            received_q=captured_q,
            expected_q=int(getattr(order, "total_q", 0) or 0),
        )
        return

    if received_q > authorized_q:
        # Pix a MAIOR levantava ``capture_exceeds_authorized`` (a captura ia
        # pelo valor do webhook), o webhook respondia 500 e a Efí repetia a
        # falha para sempre. Captura-se o AUTORIZADO e a diferença vira tarefa
        # de gente, com o valor na mão.
        _alert(
            order.ref,
            alert_type="payment_reconciliation_failed",
            severity="error",
            message=(
                f"PIX do pedido {order.ref} recebido acima do total: "
                f"{_money(received_q)} de {_money(authorized_q)}. "
                f"Capturamos {_money(authorized_q)}; devolva "
                f"{_money(received_q - authorized_q)} ao cliente pelo gateway."
            ),
            debounce_on=f"PIX do pedido {order.ref} recebido acima do total: {_money(received_q)}",
        )

    should_dispatch = _claim_paid_dispatch(order)

    _ack_alerts(order)
    _cancel_stale_intents(order, keep_intent_ref=db_intent.ref)

    if should_dispatch:
        from shopman.shop.lifecycle import dispatch

        dispatch(order, "on_paid")


# ── cobrança morta (cancelada, falha, expirada) ──


def _confirm_pix_on_dead_charge(order, db_intent, *, txid, e2e_id, reported_q) -> None:
    """Dinheiro que caiu numa cobrança que não recebe mais.

    Era o buraco silencioso: ``cancelled`` não casava com nenhum ramo de
    captura, o Pix era descartado, e a checagem seguinte perguntava ao Payman,
    ouvia "não capturado" e concluía *pagamento insuficiente* — alerta dizendo
    que o cliente pagou de menos, com o pedido cancelado e o dinheiro parado na
    conta da loja.

    O dinheiro entrou: ele vai para o livro num intent próprio (a cobrança
    morta não aceita captura, e o Payman está certo em recusar). Com o pedido
    cancelado, o ramo canônico do lifecycle (``_on_paid`` → ``payment.refund``
    + alerta ``payment_after_cancel``) é quem estorna, e ele só é alcançável
    porque o dinheiro agora existe no livro: sem intent capturado,
    ``payment.refund`` não teria o que devolver.
    """
    received_q = _record_pix_receipt(order, txid=txid, e2e_id=e2e_id, amount_q=reported_q)

    if reported_q is None:
        logger.warning(
            "pix_confirmation: Pix sem valor em cobrança encerrada order=%s txid=%s",
            order.ref, txid,
        )
        _alert(
            order.ref,
            alert_type="payment_reconciliation_failed",
            severity="critical",
            message=(
                f"Um PIX caiu na cobrança já encerrada do pedido {order.ref}, sem o valor "
                "informado. Não foi possível registrar nem devolver sozinho; "
                "confira no gateway."
            ),
            debounce_on=f"Um PIX caiu na cobrança já encerrada do pedido {order.ref}, sem o valor",
        )
        return

    booked_ref, already_booked = _book_pix_outside_charge(
        order, db_intent, txid=txid, e2e_id=e2e_id, amount_q=int(reported_q),
    )
    if already_booked:
        logger.info(
            "pix_confirmation: Pix em cobrança encerrada já registrado order=%s intent=%s",
            order.ref, booked_ref,
        )
        return

    if booked_ref is None:
        _alert(
            order.ref,
            alert_type="payment_reconciliation_failed",
            severity="critical",
            message=(
                f"PIX de {_money(received_q)} caiu na cobrança encerrada do pedido "
                f"{order.ref} e NÃO foi possível registrá-lo no livro. "
                "Concilie no gateway antes de qualquer estorno."
            ),
        )
        return

    if order.status == Order.Status.CANCELLED:
        logger.warning(
            "pix_confirmation: Pix após cancelamento order=%s valor_q=%s intent=%s",
            order.ref, reported_q, booked_ref,
        )
        from shopman.shop.lifecycle import dispatch

        # Ramo canônico, o mesmo que o webhook do Stripe usa: estorna e alerta
        # ``payment_after_cancel``. Um dono só para "pagamento chegou depois do
        # cancelamento".
        dispatch(order, "on_paid")
        return

    # Pedido vivo com cobrança morta: cliente pagou o QR velho, ou pagou duas
    # vezes. Máquina nenhuma distingue os dois casos, e os dois precisam de
    # gente. O que não pode faltar é o dinheiro estar no livro e alguém saber.
    _alert(
        order.ref,
        alert_type="payment_reconciliation_failed",
        severity="critical",
        message=(
            f"PIX de {_money(reported_q)} do pedido {order.ref} caiu numa cobrança já "
            f"encerrada ({_charge_status_label(db_intent.status)}). O valor foi registrado no "
            "livro e nada foi confirmado sozinho; confira se o pedido foi pago duas vezes "
            "e devolva pelo gateway se for o caso."
        ),
        debounce_on=f"PIX de {_money(reported_q)} do pedido {order.ref} caiu numa cobrança já",
    )


def _book_pix_outside_charge(
    order, db_intent, *, txid: str, e2e_id: str, amount_q: int,
) -> tuple[str | None, bool]:
    """Registrar no Payman dinheiro que a cobrança original não pode receber.

    Devolve ``(intent_ref, já_estava_registrado)``.

    Por que um intent NOVO e não a cobrança morta: o Payman recusa captura em
    intent terminal, e ele está certo — o livro contaria como recebida uma
    cobrança que foi cancelada. O dinheiro é um fato à parte, e ganha o
    registro dele.

    Por que ``gateway=""`` com o ``txid`` no ``gateway_id``: o par
    ``(gateway, gateway_id)`` é ÚNICO no Payman e a cobrança morta já ocupa
    ``("efi", txid)``. O ``txid`` precisa ficar no ``gateway_id`` porque é por
    ele que ``adapters/payment_efi.refund`` acha a cobrança para pedir a
    devolução; sem isso o estorno automático não teria como sair.
    """
    from shopman.payman import PaymentError, PaymentService

    gateway_data = {
        "txid": txid,
        "e2e_id": e2e_id,
        "booked_by": "pix_confirmation",
        "reason": "pix_recebido_em_cobranca_encerrada",
        "superseded_intent_ref": db_intent.ref,
        "superseded_status": db_intent.status,
    }
    idempotency_key = f"pix-outside-charge:{txid}:{e2e_id}"[:128]

    try:
        intent = PaymentService.create_intent(
            order.ref,
            int(amount_q),
            "pix",
            gateway="",
            gateway_id=txid,
            gateway_data=gateway_data,
            idempotency_key=idempotency_key,
        )
    except Exception:
        logger.warning(
            "pix_confirmation: registro do Pix com txid falhou, tentando sem gateway_id order=%s txid=%s",
            order.ref, txid, exc_info=True,
        )
        try:
            intent = PaymentService.create_intent(
                order.ref,
                int(amount_q),
                "pix",
                gateway="",
                gateway_id="",
                gateway_data=gateway_data,
                idempotency_key=idempotency_key,
            )
        except Exception:
            logger.exception(
                "pix_confirmation: não foi possível registrar o Pix order=%s txid=%s",
                order.ref, txid,
            )
            return None, False

    if intent.status in ("captured", "refunded"):
        return intent.ref, True

    try:
        if intent.status == "pending":
            PaymentService.authorize(intent.ref, gateway_id=intent.gateway_id)
        PaymentService.capture(intent.ref, gateway_id=intent.gateway_id)
    except PaymentError:
        logger.exception(
            "pix_confirmation: falha ao capturar o registro do Pix order=%s intent=%s",
            order.ref, intent.ref,
        )
        return None, False

    logger.info(
        "pix_confirmation: Pix fora da cobrança registrado order=%s intent=%s valor_q=%s",
        order.ref, intent.ref, amount_q,
    )
    return intent.ref, False


# ── sem cobrança no livro ──


def _confirm_pix_without_charge(*, txid: str, e2e_id: str, reported_q) -> None:
    """Nenhum intent tem esse ``txid``.

    A busca do pedido é por IGUALDADE. Era ``intent_ref__icontains=txid``, e
    um ``txid`` que fosse pedaço de qualquer ``intent_ref`` casava — ``"PAY-"``
    casa com todos — marcando o pedido de OUTRO cliente como pago. E, naquele
    ramo, a suficiência vinha do valor que o próprio webhook declarava, sem
    contrapartida no Payman: gravava ``captured_at`` e despachava ``on_paid``.
    Como ``captured_at`` é o guard de idempotência, o pagamento de verdade que
    chegasse depois capturava no Payman e não disparava mais nada.

    Sem intent não há contrapartida no livro, então aqui NUNCA se confirma
    pagamento. Registra e alerta.
    """
    order = Order.objects.filter(data__payment__intent_ref=txid).first()
    if order is None:
        logger.warning(
            "pix_confirmation: no payment intent or order for txid=%s", txid,
        )
        return

    received_q = _record_pix_receipt(order, txid=txid, e2e_id=e2e_id, amount_q=reported_q)
    logger.warning(
        "pix_confirmation: Pix sem cobrança no livro order=%s txid=%s valor_q=%s",
        order.ref, txid, received_q,
    )
    _alert(
        order.ref,
        alert_type="payment_reconciliation_failed",
        severity="critical",
        message=(
            f"PIX de {_money(received_q)} chegou para o pedido {order.ref} sem cobrança "
            "correspondente no livro. Nada foi confirmado sozinho; concilie no gateway."
        ),
        debounce_on=f"PIX de {_money(received_q)} chegou para o pedido {order.ref} sem cobrança",
    )


# ── escrita no pedido ──


def _record_pix_receipt(order, *, txid: str, e2e_id: str, amount_q) -> int | None:
    """Gravar o recebimento no pedido e devolver o total recebido até agora.

    Os recibos ficam num mapa por Pix (``payment.pix_receipts``), não num
    número solto: é o que permite dois Pix parciais SOMAREM para cobrir a
    cobrança sem que uma reapresentação do mesmo Pix conte duas vezes. A chave
    é o ``e2e_id`` (identidade do Pix na rede); quando o chamador não tem um,
    ``txid:<txid>``, que ao menos torna a repetição do mesmo txid idempotente.

    Devolve ``None`` quando nenhum dos Pix recebidos trouxe valor legível.
    """
    key = e2e_id or f"txid:{txid}"
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        data = dict(locked.data or {})
        payment_data = dict(data.get("payment") or {})
        receipts = dict(payment_data.get("pix_receipts") or {})
        receipts[key] = int(amount_q) if amount_q is not None else None
        payment_data["pix_receipts"] = receipts

        known = [int(v) for v in receipts.values() if v is not None]
        received_q = sum(known) if known else None
        if received_q is not None:
            payment_data["paid_amount_q"] = received_q
        if e2e_id:
            payment_data["e2e_id"] = e2e_id

        data["payment"] = payment_data
        locked.data = data
        locked.save(update_fields=["data", "updated_at"])

    order.data = data
    return received_q


def _claim_paid_dispatch(order) -> bool:
    """Gravar ``captured_at`` e devolver True só para quem ganhou a corrida.

    ``captured_at`` marca captura SUFICIENTE: é o guard de idempotência do
    ``on_paid`` e nunca é gravado num pagamento parcial.
    """
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        data = dict(locked.data or {})
        payment_data = dict(data.get("payment") or {})
        if payment_data.get("captured_at"):
            return False
        captured_at = _captured_at_for_payment(locked) or timezone.now()
        payment_data["captured_at"] = captured_at.isoformat()
        data["payment"] = payment_data
        locked.data = data
        locked.save(update_fields=["data", "updated_at"])

    order.data = data
    return True


# ── Payman ──


def _capture_charge(db_intent, *, txid: str, e2e_id: str) -> str:
    """Autorizar e capturar a cobrança pelo valor AUTORIZADO.

    Devolve ``"captured"`` (inclui o replay de uma cobrança já capturada) ou
    ``"dead"`` quando a cobrança não recebe mais.

    A captura vai pelo valor autorizado, nunca pelo valor que o webhook
    declarou: capturar a mais levantava ``capture_exceeds_authorized`` (500
    eterno na reentrega da Efí) e capturar a menos queimava a cobrança.
    """
    from shopman.payman import PaymentError, PaymentService

    try:
        if db_intent.status == "pending":
            PaymentService.authorize(
                db_intent.ref,
                gateway_id=txid,
                gateway_data={"e2e_id": e2e_id},
            )
        if db_intent.status in ("pending", "authorized"):
            PaymentService.capture(db_intent.ref, gateway_id=txid)
    except PaymentError as e:
        if e.code == "intent_expired":
            # Cobrança vencida que ainda assim recebeu. Levantar aqui daria
            # 500 e reentrega infinita; o dinheiro vai para o ramo de cobrança
            # morta, que registra e alerta.
            return "dead"
        if e.code != "invalid_transition":
            raise
        # Corrida: outro caminho capturou (segue), ou a cobrança morreu.
        current = PaymentService.get(db_intent.ref)
        if current.status in _DEAD_CHARGE_STATUSES:
            return "dead"
    return "captured"


def _captured_balance_q(order, db_intent) -> int | None:
    """Quanto o Payman mostra capturado (menos devolvido) para este pedido.

    Com ``payment.intent_ref`` no pedido, a fonte é a mesma do webhook Stripe
    (``payment.captured_balance_q``). Sem ela, a contrapartida é a própria
    cobrança que o gateway apontou. Nos dois casos quem responde é o livro; o
    valor declarado pelo webhook nunca serve de prova.
    """
    from shopman.shop.services import payment as payment_service

    if ((order.data or {}).get("payment") or {}).get("intent_ref"):
        return payment_service.captured_balance_q(order)

    try:
        from shopman.payman import PaymentService

        return (
            PaymentService.captured_total(db_intent.ref)
            - PaymentService.refunded_total(db_intent.ref)
        )
    except Exception:
        logger.warning(
            "pix_confirmation: saldo capturado ilegível order=%s intent=%s",
            order.ref, db_intent.ref, exc_info=True,
        )
        return None


def _intent_for_pix_txid(payment_service, txid: str):
    """Locate the PIX intent for both real EFI and local mock gateways."""
    for gateway in ("efi", "mock"):
        intent = payment_service.get_by_gateway_id(txid, gateway=gateway)
        if intent is not None:
            return intent
    return None


def _order_for_charge(db_intent):
    order = Order.objects.filter(data__payment__intent_ref=db_intent.ref).first()
    if order is not None:
        return order
    return Order.objects.filter(ref=db_intent.order_ref).first()


def _cancel_stale_intents(order, *, keep_intent_ref: str) -> None:
    try:
        from shopman.shop.services import payment as payment_service

        payment_service.cancel_stale_intents(order, keep_intent_ref=keep_intent_ref)
    except Exception:
        logger.debug("pix_confirmation_cancel_stale_intents_failed order=%s", order.ref, exc_info=True)


def _captured_at_for_payment(order):
    payment_data = order.data.get("payment", {}) if order.data else {}
    intent_ref = payment_data.get("intent_ref")
    if not intent_ref:
        return None
    try:
        from shopman.payman import PaymentService

        intent = PaymentService.get(intent_ref)
    except Exception:
        logger.debug(
            "pix_confirmation: unable to read captured_at for order=%s intent=%s",
            order.ref,
            intent_ref,
            exc_info=True,
        )
        return None
    return intent.captured_at


# ── valor ──


def _reported_amount_q(amount: str, *, txid: str) -> int | None:
    """Centavos do valor informado pelo gateway, ou ``None`` se indeterminado.

    Aceita o formato ISO da Efí (``"8.00"``) e também o pt-BR (``"8,00"``),
    que antes explodia no ``Decimal`` e virava 500 eterno na reentrega.
    Ausência e formato ilegível devolvem ``None``: indeterminado espera, nunca
    é presumido como "pagou o total".
    """
    from shopman.utils.monetary import brl_to_q

    raw = str(amount or "").strip()
    if not raw:
        return None
    raw = raw.replace("R$", "").replace(" ", "").replace(" ", "")
    if "," in raw:
        # pt-BR: ponto é milhar, vírgula é decimal.
        raw = raw.replace(".", "").replace(",", ".")
    try:
        parsed = Decimal(raw)
    except (InvalidOperation, ValueError):
        logger.warning("pix_confirmation: valor ilegível (%r) txid=%s", amount, txid)
        return None
    if parsed <= 0:
        logger.warning("pix_confirmation: valor não positivo (%r) txid=%s", amount, txid)
        return None
    return brl_to_q(parsed)


def _money(amount_q) -> str:
    from shopman.utils.monetary import format_money

    if amount_q is None:
        return "valor não informado"
    return f"R$ {format_money(int(amount_q))}"


def _charge_status_label(status: str) -> str:
    return {"cancelled": "cancelada", "failed": "com falha"}.get(status, status)


# ── alertas ──


def _alert_insufficient(order, *, received_q, expected_q) -> None:
    missing_q = None
    if received_q is not None and expected_q is not None:
        missing_q = max(int(expected_q) - int(received_q), 0)
    message = (
        f"PIX do pedido {order.ref} recebido abaixo do total: "
        f"{_money(received_q)} de {_money(expected_q)}."
    )
    if missing_q:
        message += f" Faltam {_money(missing_q)}."
    message += (
        " A cobrança segue de pé e captura sozinha quando o restante cair; "
        "o pedido continua aguardando pagamento."
    )
    _alert(
        order.ref,
        alert_type="payment_insufficient",
        severity="error",
        message=message,
        # O valor recebido entra na dedupe: um segundo Pix parcial MUDA o
        # quadro e precisa alertar de novo. Com debounce só por tipo, o
        # segundo Pix ficava invisível por 15 minutos.
        debounce_on=f"recebido abaixo do total: {_money(received_q)} de {_money(expected_q)}",
    )


def _alert(
    order_ref: str,
    *,
    alert_type: str,
    severity: str,
    message: str,
    debounce_on: str = "",
) -> None:
    try:
        from shopman.shop.adapters import alert as alert_adapter

        if debounce_on and alert_adapter.recent_exists(
            alert_type,
            timezone.now() - _ALERT_DEBOUNCE,
            order_ref=order_ref,
            message_contains=debounce_on,
        ):
            return
        alert_adapter.create(alert_type, severity, message, order_ref=order_ref)
    except Exception:
        logger.warning(
            "pix_confirmation_alert_failed type=%s order=%s", alert_type, order_ref, exc_info=True,
        )


def _ack_alerts(order) -> None:
    """Baixar os alertas que o pagamento acabou de resolver.

    Inclui ``payment_insufficient``: o parcial que ficou pendurado foi
    completado, e um alerta que já não descreve a realidade é ruído que faz o
    operador perseguir dinheiro que já entrou.
    """
    try:
        from shopman.shop.adapters import alert as alert_adapter

        alert_adapter.acknowledge("payment_failed", order_ref=order.ref)
        alert_adapter.acknowledge("payment_insufficient", order_ref=order.ref)
    except Exception:
        logger.debug("pix_confirmation_alert_ack_failed order=%s", order.ref, exc_info=True)


__all__ = ["confirm_pix"]
