"""
Payment orchestration service.

Core: PaymentService (create_intent, authorize, capture, refund, cancel)
Adapter: get_adapter("payment", method=...) → payment_efi / payment_stripe / payment_mock

The contract between this service and the adapters is defined in
shopman.adapters.payment_types: adapters return PaymentIntent / PaymentResult
dataclasses, not dicts. This service consumes them by attribute access.

order.data["payment"] contract: {intent_ref, method} are the core keys.
Display keys (qr_code, copy_paste, client_secret, expires_at, amount_q) are also stored.
Payman is the live canonical source when an intent exists. Embedded status is
only a compatibility/read fallback for imported or legacy orders without an
intent.

Métodos sem gateway (``cash``, ``external``): o Payman também é o livro
deles (ADR-022). Quando a coleta é no terminal (``payment.collection ==
"terminal"``, escrito pelo PDV) o intent nasce capturado na venda via
``PaymentService.settle``; sem ``collection`` (loja online) ou com coleta na
entrega (COD) o dinheiro ainda não trocou de mãos e o intent nasce no acerto.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from shopman.shop.adapters import get_adapter
from shopman.shop.adapters.payment_types import PaymentIntent, PaymentResult

logger = logging.getLogger(__name__)


def settles_without_gateway(method: str | None) -> bool:
    """True para os métodos que liquidam sem gateway (dinheiro, cobrança externa).

    Dono da lista é o Payman (``PaymentIntent.METHODS_WITHOUT_GATEWAY``); este
    helper existe para quem raciocina a partir do ``Order.data.payment.method``.
    Um intent desses nasce capturado na venda: não há webhook, autorização
    remota nem ``on_paid`` a recuperar (o pedido do PDV já roda o ciclo pelo
    ``payment.timing == "external"``).
    """
    from shopman.payman import PaymentIntent as PaymanIntent

    return str(method or "").strip().lower() in PaymanIntent.METHODS_WITHOUT_GATEWAY


def initiate(order) -> None:
    """
    Create a payment intent for the order.

    Resolves the adapter by payment method (from order.data["payment"]["method"]),
    calls adapter.create_intent(), then saves intent_ref and display data
    in order.data["payment"].

    Métodos sem gateway (``cash``/``external``) não têm adapter: quando a
    coleta é no terminal o intent nasce capturado (``settle_terminal_tenders``);
    fora disso não há intent a criar ainda.

    SYNC — needs the intent/QR data to show to the client.
    """
    payment_data = order.data.get("payment", {})
    method = payment_data.get("method")

    if not method:
        return

    # Idempotent: skip if intent already exists
    if payment_data.get("intent_ref"):
        return

    if settles_without_gateway(method):
        settle_terminal_tenders(order)
        return

    amount_q = order.total_q
    existing_intent = _existing_active_intent(order, method=method, amount_q=amount_q)
    if existing_intent:
        _persist_intent(order, payment_data=payment_data, method=method, amount_q=amount_q, intent=existing_intent)
        logger.info(
            "payment.initiate: reused existing %s intent %s for order %s",
            method,
            existing_intent.intent_ref,
            order.ref,
        )
        return

    adapter = get_adapter("payment", method=method)
    if not adapter:
        logger.warning("payment.initiate: no adapter for method=%s", method)
        _record_initiate_error(
            order,
            payment_data=payment_data,
            method=method,
            amount_q=amount_q,
            error="Método de pagamento indisponível.",
        )
        return

    idempotency_key = _ensure_payment_idempotency_key(
        order,
        payment_data=payment_data,
        method=method,
        amount_q=amount_q,
    )
    adapter_config = _adapter_config(order, method=method)
    adapter_config["idempotency_key"] = idempotency_key
    try:
        intent = adapter.create_intent(
            order_ref=order.ref,
            amount_q=amount_q,
            currency="BRL",
            method=method,
            metadata={"method": method, "idempotency_key": idempotency_key},
            **adapter_config,
        )
    except Exception as exc:
        logger.error(
            "payment.initiate: create_intent failed for order %s method=%s: %s",
            order.ref,
            method,
            exc,
        )
        existing_intent = _existing_active_intent(order, method=method, amount_q=amount_q)
        if existing_intent:
            _persist_intent(order, payment_data=payment_data, method=method, amount_q=amount_q, intent=existing_intent)
            logger.warning(
                "payment.initiate: recovered existing %s intent %s for order %s after adapter error: %s",
                method,
                existing_intent.intent_ref,
                order.ref,
                exc,
            )
            return
        _record_initiate_error(
            order,
            payment_data=payment_data,
            method=method,
            amount_q=amount_q,
            error=str(exc),
        )
        return

    _persist_intent(order, payment_data=payment_data, method=method, amount_q=amount_q, intent=intent)
    logger.info(
        "payment.initiate: %s intent %s for order %s",
        method, intent.intent_ref, order.ref,
    )


def _persist_intent(
    order,
    *,
    payment_data: dict,
    method: str,
    amount_q: int,
    intent: PaymentIntent,
) -> None:
    # Build payment data to save — intent_ref + method + display fields only.
    # Status is NOT stored here; Payman (PaymentService) is the canonical source.
    result = {
        **payment_data,
        "intent_ref": intent.intent_ref,
        "amount_q": amount_q,
        "method": method,
    }
    result.pop("error", None)

    # Extract QR/client_secret data for UI display
    if method == "pix":
        qr_data = _extract_qr_data(intent)
        result["qr_code"] = (
            qr_data.get("imagemQrcode")
            or qr_data.get("qr_image")
            or qr_data.get("qr_code")
            or qr_data.get("qrcode")
        )
        result["copy_paste"] = (
            qr_data.get("brcode")
            or qr_data.get("copy_paste")
            or qr_data.get("qrcode")
        )
        if intent.expires_at:
            result["expires_at"] = intent.expires_at.isoformat()
    elif method == "card":
        # Stripe Checkout (hosted): redirect URL the client clicks to pay.
        checkout_url = (intent.metadata or {}).get("checkout_url")
        if checkout_url:
            result["checkout_url"] = checkout_url

    order.data["payment"] = result
    order.save(update_fields=["data", "updated_at"])
    _ack_payment_failed_alerts(order)
    if intent.expires_at:
        _schedule_payment_timeout(order, intent)


def settle_terminal_tenders(order) -> dict[str, str]:
    """Liquida no Payman o que o terminal recebeu, UM intent por método.

    É o que faz do Payman o livro de pagamentos de todos os métodos: receita
    por método sai daqui, não do JSON do pedido, e a reconciliação enxerga
    dinheiro. Devolve ``{method: intent_ref}`` só dos métodos liquidados aqui.

    Regras:
    - Só quando ``payment.collection == "terminal"``: é o PDV declarando que o
      valor foi recebido no balcão, no ato. Sem ``collection`` (loja online,
      WhatsApp) ou com ``on_delivery`` (COD) o dinheiro ainda não trocou de
      mãos, e o intent nasce no acerto, não aqui.
    - O valor de cada método é a SOMA dos seus tenders recebidos no terminal
      (o que ficou na gaveta depois do troco), nunca o que o cliente entregou
      nem o total do pedido.
    - ``cash``/``external`` liquidam sempre. ``pix``/``card`` só numa venda
      MISTA: ali não há gateway (o operador atestou o recebimento: QR estático,
      maquininha avulsa) e o intent nasce ``asserted_at_terminal``. Numa venda
      só de pix/cartão o caminho continua sendo o gateway (``initiate``).
    - Idempotente por método: repetir devolve o mesmo intent (chave estável
      no Payman + reaproveitamento do capturado quando o ``data`` não gravou).

    Grava ``tenders[i].intent_ref`` em cada linha do método e, quando o pedido
    tem UM método, também ``payment.intent_ref`` (contrato que o restante do
    orquestrador já lê). O ``payment.method`` continua sendo o do pedido.
    """
    payment_data = dict((order.data or {}).get("payment") or {})
    collection = str(payment_data.get("collection") or "").strip().lower()
    if collection != "terminal":
        return {}
    if str(getattr(order, "status", "") or "").lower() in {"cancelled", "returned"}:
        # Venda que morreu no próprio commit (gate de disponibilidade) não
        # recebeu dinheiro: liquidar aqui inventaria captura em pedido cancelado.
        return {}

    by_method = _terminal_amounts_by_method(order, payment_data=payment_data)
    if not by_method:
        return {}
    mixed = len(by_method) > 1

    from shopman.payman import PaymentService

    settled: dict[str, str] = {}
    for method, amount_q in by_method.items():
        gateway_method = not settles_without_gateway(method)
        if gateway_method and not mixed:
            continue  # pix/cartão sozinhos: gateway, via initiate()
        existing_ref = _existing_tender_intent_ref(payment_data, method=method)
        if existing_ref:
            settled[method] = existing_ref
            continue
        existing_intent = _existing_active_intent(order, method=method, amount_q=amount_q)
        if existing_intent and existing_intent.status == "captured":
            settled[method] = existing_intent.intent_ref
            logger.info(
                "payment.settle_terminal_tenders: reused captured %s intent %s for order %s",
                method, existing_intent.intent_ref, order.ref,
            )
            continue
        # Sem o valor na chave. Com ele, um total que mudasse entre duas
        # tentativas (falha parcial + reedição) gerava chave nova e um SEGUNDO
        # intent capturado do mesmo método no mesmo pedido — receita dobrada no
        # Payman com uma gaveta só, e linha imutável que ninguém apaga. Chave
        # estável por (pedido, método) deixa o `_require_idempotent_match` do
        # Payman acusar a divergência de valor, que é para isso que ele existe:
        # o erro sobe, o PDV registra `pos_sale_settlement_failed`, e a venda
        # fica sem intent — falta que a reconciliação diária aponta e um humano
        # conserta, ao contrário do dobro.
        idempotency_key = f"order-payment:{order.ref}:{method}:terminal"
        if method == "account":
            # Em conta: a obrigação nasce reconhecida (authorized), não paga. O
            # cliente já foi validado como elegível antes do commit (close_sale).
            intent = PaymentService.charge_to_account(
                order.ref,
                amount_q,
                customer_ref=str((order.data or {}).get("customer_ref") or ""),
                currency="BRL",
                idempotency_key=idempotency_key,
                gateway_data={"collection": "terminal", "terminal_ref": _terminal_ref(order)},
            )
        else:
            intent = PaymentService.settle(
                order.ref,
                amount_q,
                method,
                currency="BRL",
                idempotency_key=idempotency_key,
                gateway_data={"collection": "terminal", "terminal_ref": _terminal_ref(order)},
                asserted_at_terminal=gateway_method,
            )
        settled[method] = intent.ref
        logger.info(
            "payment.settle_terminal_tenders: %s settled at terminal, intent %s for order %s",
            method, intent.ref, order.ref,
        )

    if settled:
        _persist_tender_intents(order, payment_data=payment_data, settled=settled, single=not mixed)
    return settled


def _terminal_amounts_by_method(order, *, payment_data: dict) -> dict[str, int]:
    """Soma dos tenders recebidos no terminal, por método; sem tenders, o método do pedido pelo total."""
    tenders = [t for t in (payment_data.get("tenders") or []) if isinstance(t, dict)]
    totals: dict[str, int] = {}
    if not tenders:
        method = str(payment_data.get("method") or "").strip().lower()
        total_q = int(order.total_q or 0)
        if method and method != "mixed" and total_q > 0:
            totals[method] = total_q
        return totals
    for tender in tenders:
        method = str(tender.get("method") or "").strip().lower()
        if not method or str(tender.get("collection") or "terminal").strip().lower() != "terminal":
            continue
        try:
            amount_q = int(tender.get("amount_q") or 0)
        except (TypeError, ValueError):
            continue
        if amount_q <= 0:
            continue
        totals[method] = totals.get(method, 0) + amount_q
    return totals


def _existing_tender_intent_ref(payment_data: dict, *, method: str) -> str:
    for tender in payment_data.get("tenders") or []:
        if not isinstance(tender, dict):
            continue
        if str(tender.get("method") or "").strip().lower() == method and tender.get("intent_ref"):
            return str(tender["intent_ref"])
    if len(_methods_of(payment_data)) <= 1 and payment_data.get("intent_ref"):
        return str(payment_data["intent_ref"])
    return ""


def _methods_of(payment_data: dict) -> set[str]:
    tenders = [t for t in (payment_data.get("tenders") or []) if isinstance(t, dict)]
    if tenders:
        return {str(t.get("method") or "").strip().lower() for t in tenders if t.get("method")}
    method = str(payment_data.get("method") or "").strip().lower()
    return {method} if method and method != "mixed" else set()


def _terminal_ref(order) -> str:
    return str(((order.data or {}).get("pos") or {}).get("terminal_ref") or "")


def _persist_tender_intents(order, *, payment_data: dict, settled: dict[str, str], single: bool) -> None:
    """Grava a ref do intent nas linhas de tender do método (e no topo, quando há um método só)."""
    result = dict(payment_data)
    tenders = [dict(t) for t in (result.get("tenders") or []) if isinstance(t, dict)]
    for tender in tenders:
        method = str(tender.get("method") or "").strip().lower()
        if method in settled and str(tender.get("collection") or "terminal").strip().lower() == "terminal":
            tender["intent_ref"] = settled[method]
    if tenders:
        result["tenders"] = tenders
    if single:
        (method, ref), = settled.items()
        result["intent_ref"] = ref
        result["method"] = method
    result.pop("error", None)
    data = dict(order.data or {})
    data["payment"] = result
    order.data = data
    order.save(update_fields=["data", "updated_at"])
    _ack_payment_failed_alerts(order)


def capture(order) -> None:
    """
    Capture a previously authorized payment via adapter.

    Reads intent_ref from order.data["payment"] and calls adapter.capture().
    Uses Payman (PaymentService) as idempotency source.

    SYNC — capture must succeed.
    """
    payment_data = (order.data or {}).get("payment", {})
    intent_ref = payment_data.get("intent_ref")

    if not intent_ref:
        return

    # Idempotency via Payman — skip if already captured
    if _payman_intent_captured(intent_ref):
        return

    method = payment_data.get("method", "pix")
    adapter = get_adapter("payment", method=method)
    if not adapter:
        return

    result = adapter.capture(intent_ref)
    if result.success:
        payment_data["transaction_id"] = result.transaction_id
        order.data["payment"] = payment_data
        order.save(update_fields=["data", "updated_at"])
        _ack_payment_failed_alerts(order)
        cancel_stale_intents(order, keep_intent_ref=intent_ref)

        logger.info("payment.capture: captured %s for order %s", intent_ref, order.ref)


def refund(
    order,
    *,
    amount_q: int | None = None,
    idempotency_key: str | None = None,
    _from_directive: bool = False,
) -> None:
    """
    Refund payment for the order (o estorno que o SISTEMA consegue fazer sozinho).

    Sem intent não há o que estornar (pedido ainda não liquidado, COD por
    acertar, pedido legado): no-op. Com intent de gateway (pix, cartão), o
    gateway devolve e o Payman registra. ``external``/pix atestado no balcão
    não têm gateway: o Payman registra o estorno como fato declarado, como a
    captura foi.

    ⚠️ **Dinheiro NÃO se estorna aqui.** Cancelar não é devolver: às 22h o
    gestor cancela e ninguém abriu gaveta nenhuma. Dizer ``REFUND`` nesse
    instante afirmaria que o dinheiro voltou ao cliente sem ter voltado, e o
    livro-caixa (cashman) ficaria sem a linha, que é exatamente o que a
    reconciliação cruzada acusa. O intent em dinheiro fica ``captured`` e o
    pedido cancelado aparece em ``pending_cash_refunds`` até alguém, com turno
    aberto, entregar o dinheiro e chamar ``refund_cash`` (Payman + linha
    ``refund`` no turno, na mesma transação).
    Uses Payman (PaymentService) as idempotency source.

    ``amount_q`` limita o estorno (devolução PARCIAL); ``None`` estorna o saldo
    reembolsável inteiro. O valor nunca excede o saldo do Payman.

    ``idempotency_key`` torna o estorno idempotente ponta a ponta: o gateway
    reapresenta a MESMA devolução num retry e o Payman deduplica por gateway_id.
    Default: ``order-refund:{order.ref}`` (bom p/ o estorno total do cancel);
    a devolução PARCIAL passa uma chave por-devolução (return:{ref}:{idx}).

    SYNC — direct refund.
    """
    payment_data = (order.data or {}).get("payment", {})

    if idempotency_key is None:
        idempotency_key = f"order-refund:{order.ref}"

    # Todo intent capturado do pedido, não só o ``payment.intent_ref``: a venda
    # mista do terminal tem um intent por método, e o cancel dela devolve todos.
    # A fonte é o Payman (livro), não o JSON: pedido antigo sem tenders com
    # intent_ref cai no mesmo laço.
    # Venda em conta cancelada: a dívida morre com ela (authorized → cancelled).
    # Não é estorno (nada foi pago); é o intent deixando de contar no saldo.
    if _pays_on_account(payment_data):
        _cancel_open_account_intents(order)
    intents = [pair for pair in _refundable_intents(order, payment_data=payment_data) if pair[0] != "cash"]
    remaining_q = amount_q
    for method, intent_ref in intents:
        if remaining_q is not None and remaining_q <= 0:
            return
        refunded_q = _refund_intent(
            order,
            intent_ref=intent_ref,
            method=method,
            amount_q=remaining_q,
            # Um intent só mantém a chave histórica (retries antigos continuam
            # deduplicando); com vários, cada estorno tem a sua.
            idempotency_key=idempotency_key if len(intents) == 1 else f"{idempotency_key}:{intent_ref}",
            _from_directive=_from_directive,
        )
        if remaining_q is not None:
            remaining_q -= refunded_q


def _pays_on_account(payment_data: dict) -> bool:
    if str(payment_data.get("method") or "").lower() == "account":
        return True
    return any(
        str(t.get("method") or "").lower() == "account"
        for t in (payment_data.get("tenders") or [])
        if isinstance(t, dict)
    )


def _cancel_open_account_intents(order) -> None:
    from shopman.payman import PaymentIntent, PaymentService

    for intent in PaymentService.get_by_order(order.ref).filter(
        method=PaymentIntent.Method.ACCOUNT, status=PaymentIntent.Status.AUTHORIZED
    ):
        try:
            PaymentService.cancel(intent.ref, reason="order_cancelled")
        except Exception:
            logger.warning("payment.refund: account intent %s cancel failed order=%s", intent.ref, order.ref, exc_info=True)


def _refundable_intents(order, *, payment_data: dict) -> list[tuple[str, str]]:
    """``[(method, intent_ref)]`` capturados do pedido, dinheiro primeiro.

    Dinheiro primeiro porque uma devolução parcial devolve o que está na mão:
    o operador entrega nota, não estorna cartão pela metade.
    """
    try:
        from shopman.payman import PaymentService

        intents = list(
            PaymentService.get_by_order(order.ref).filter(status__in={"captured", "refunded"}).order_by("id")
        )
    except Exception:
        logger.debug("payment.refund: intent lookup failed order=%s", order.ref, exc_info=True)
        intents = []
    if not intents:
        legacy_ref = payment_data.get("intent_ref")
        return [(str(payment_data.get("method") or "pix"), legacy_ref)] if legacy_ref else []
    return sorted(((i.method, i.ref) for i in intents), key=lambda pair: (pair[0] != "cash", pair[1]))


@dataclass(frozen=True)
class PendingCashRefund:
    """Um pedido cancelado cujo dinheiro ainda não saiu de nenhuma gaveta."""

    order_ref: str
    amount_q: int
    intent_refs: tuple[str, ...]
    cancelled_at: str  # ISO datetime, "" quando o pedido não guarda
    customer_name: str
    channel_ref: str


def pending_cash_refunds(*, channel_ref: str | None = None) -> list[PendingCashRefund]:
    """Pedidos cancelados/devolvidos com dinheiro capturado e ainda não devolvido.

    A pendência NÃO é uma tabela: é derivada de dois fatos que já existem
    (status do pedido no Orderman, saldo capturado − estornado do intent em
    dinheiro no Payman). Inventar estado para ela seria o segundo dono da mesma
    pergunta. Dinheiro só: pix/cartão o gateway já devolveu no cancel.
    """
    from shopman.orderman.models import Order
    from shopman.payman import PaymentService
    from shopman.payman.models import PaymentIntent

    intents = PaymentIntent.objects.filter(
        method="cash", gateway="", status__in={"captured", "refunded"}
    ).order_by("order_ref", "id")
    by_order: dict[str, list] = {}
    for intent in intents:
        by_order.setdefault(intent.order_ref, []).append(intent)
    if not by_order:
        return []
    orders = Order.objects.filter(ref__in=list(by_order), status__in={"cancelled", "returned"})
    if channel_ref:
        orders = orders.filter(channel_ref=channel_ref)
    pending: list[PendingCashRefund] = []
    for order in orders.order_by("updated_at"):
        refs = []
        balance_q = 0
        for intent in by_order.get(order.ref, []):
            captured = PaymentService.captured_total(intent.ref)
            refunded = PaymentService.refunded_total(intent.ref)
            if captured - refunded > 0:
                balance_q += captured - refunded
                refs.append(intent.ref)
        if balance_q <= 0:
            continue
        data = order.data or {}
        pending.append(
            PendingCashRefund(
                order_ref=order.ref,
                amount_q=balance_q,
                intent_refs=tuple(refs),
                cancelled_at=str(data.get("cancelled_at") or ""),
                customer_name=str(data.get("customer_name") or ""),
                channel_ref=order.channel_ref,
            )
        )
    return pending


def refund_cash(order, *, shift, actor, approved_by=None, reason: str = "cancelamento") -> int:
    """Devolve o dinheiro de uma venda: Payman e livro-caixa na MESMA transação.

    É o gesto físico: alguém com turno aberto entrega as notas ao cliente. Por
    isso exige o turno de quem devolve (o dinheiro sai DESTA gaveta, agora) e
    grava os dois livros juntos: ``PaymentTransaction(REFUND)`` nos intents em
    dinheiro do pedido e uma linha ``refund`` (efeito negativo) no turno,
    apontando para a linha ``sale`` original quando é o mesmo livro. Devolve o
    valor devolvido (zero se não havia saldo em dinheiro a devolver).

    Idempotente: o saldo reembolsável do Payman é a fonte; a segunda chamada
    não encontra saldo e não grava linha.
    """
    from django.db import transaction as db_transaction
    from shopman.cashman import Entry
    from shopman.cashman import services as cash_ledger
    from shopman.payman import PaymentService

    if shift is None or not getattr(shift, "is_open", False):
        raise ValueError(f"Abra o caixa para devolver o dinheiro da venda {order.ref}.")

    cash_intents = [
        ref for method, ref in _refundable_intents(order, payment_data=(order.data or {}).get("payment") or {})
        if method == "cash"
    ]
    with db_transaction.atomic():
        refunded_q = 0
        refunded_refs = []
        for intent_ref in cash_intents:
            balance_q = _payman_refundable_amount(intent_ref) or 0
            if balance_q <= 0:
                continue
            PaymentService.refund(
                intent_ref,
                amount_q=balance_q,
                reason="order_cancelled",
                gateway_id=f"cash-refund:{order.ref}:{intent_ref}",
            )
            refunded_q += balance_q
            refunded_refs.append(intent_ref)
        if refunded_q <= 0:
            return 0
        original = Entry.objects.filter(kind=Entry.Kind.SALE, order_ref=order.ref).order_by("id").first()
        cash_ledger.record(
            "refund",
            shift=shift,
            operator=actor,
            approved_by=approved_by,
            amount_q=-refunded_q,
            order_ref=order.ref,
            payment_ref=refunded_refs[0],
            parent=original if original is not None and original.shift_id == shift.pk else None,
            reason=str(reason or "")[:200],
            payload={"intents_refunded": refunded_refs},
        )
    logger.info("payment.refund_cash: refunded %s for order %s in shift %s", refunded_q, order.ref, shift.pk)
    return refunded_q


def _refund_intent(
    order,
    *,
    intent_ref: str,
    method: str,
    amount_q: int | None,
    idempotency_key: str,
    _from_directive: bool,
) -> int:
    """Estorna um intent (gateway ou sem gateway) e devolve quanto pediu para estornar."""
    refundable_q = _payman_refundable_amount(intent_ref)

    # Idempotency via Payman — skip only when the captured balance is fully
    # refunded. Payman status REFUNDED can also mean a partial refund.
    if refundable_q is not None and refundable_q <= 0:
        return 0
    if refundable_q is None and _payman_intent_refunded(intent_ref):
        return 0

    requested_q = refundable_q
    if amount_q is not None:
        requested_q = amount_q if refundable_q is None else min(int(amount_q), refundable_q)
        if requested_q <= 0:
            return 0

    adapter = None
    if not settles_without_gateway(method) and not _asserted_at_terminal(intent_ref):
        adapter = get_adapter("payment", method=method)
        if not adapter:
            return 0

    try:
        if adapter is None:
            result = _refund_without_gateway(
                intent_ref,
                amount_q=requested_q,
                idempotency_key=idempotency_key,
            )
        else:
            result = adapter.refund(
                intent_ref,
                amount_q=requested_q,
                reason="order_cancelled",
                idempotency_key=idempotency_key,
            )
    except Exception as exc:
        # Falha TRANSIENTE (gateway fora/timeout). Estorno é idempotente, então
        # retentamos com backoff em vez de desistir e reter o dinheiro do cliente.
        logger.error("payment.refund: exceção no estorno do pedido %s: %s", order.ref, exc)
        if _from_directive:
            # Deixa a Directive retentar (o handler alerta ao esgotar tentativas).
            from shopman.orderman.exceptions import DirectiveTransientError

            raise DirectiveTransientError(f"refund gateway error: {exc}") from exc
        # Caminho síncrono: enfileira o retry assíncrono (não bloqueia o cancel).
        from shopman.shop import directives

        directives.queue(
            directives.PAYMENT_REFUND,
            order,
            amount_q=requested_q,
            idempotency_key=idempotency_key,
        )
        return int(requested_q or 0)

    if result.success:
        logger.info("payment.refund: refunded %s for order %s", intent_ref, order.ref)
        return int(requested_q or 0)

    # Falha TERMINAL (recusa do gateway): retry não ajuda → alerta já.
    detail = getattr(result, "message", None) or getattr(result, "error_code", None) or "ver logs"
    logger.error("payment.refund: adapter recusou o estorno do pedido %s: %s", order.ref, detail)
    alert_refund_failed(order, intent_ref, requested_q, detail)
    return 0


def _asserted_at_terminal(intent_ref: str) -> bool:
    """Pix/cartão atestados no balcão (venda mista) não têm gateway para estornar."""
    try:
        from shopman.payman import PaymentService

        intent = PaymentService.get(intent_ref)
        return bool(intent and not intent.gateway and (intent.gateway_data or {}).get("asserted_at_terminal"))
    except Exception:
        logger.debug("payment._asserted_at_terminal: lookup failed intent_ref=%s", intent_ref, exc_info=True)
        return False


def _refund_without_gateway(intent_ref: str, *, amount_q: int | None, idempotency_key: str) -> PaymentResult:
    """Estorno de intent sem gateway (dinheiro, cobrança externa): direto no Payman.

    Não há adapter para converter a resposta, então este helper fala o mesmo
    dialeto (``PaymentResult``) para o ``refund`` tratar sucesso, recusa e
    retry por um caminho só. A chave vai no campo próprio
    (``PaymentTransaction.idempotency_key``, com unicidade no banco) e também
    no ``gateway_id``, que é como os adapters reais identificam a devolução: o
    Payman deduplica pelos dois, e sem isso um cancel reapresentado (worker
    morto, at-least-once) devolveria o mesmo dinheiro duas vezes.
    """
    from shopman.payman import PaymentError, PaymentService

    try:
        txn = PaymentService.refund(
            intent_ref,
            amount_q=amount_q,
            reason="order_cancelled",
            gateway_id=idempotency_key,
            idempotency_key=idempotency_key,
        )
    except PaymentError as exc:
        return PaymentResult(success=False, error_code=exc.code, message=exc.message)
    return PaymentResult(success=True, transaction_id=txn.gateway_id, amount_q=txn.amount_q)


def alert_refund_failed(order, intent_ref, amount_q, detail) -> None:
    """Alerta crítico de operador para estorno falho — o dinheiro pode estar retido."""
    from shopman.utils.monetary import format_money

    from shopman.shop.services.observability import create_operator_alert

    try:
        amount_display = format_money(amount_q) if amount_q is not None else "valor a apurar"
    except Exception:
        logger.debug("alert_refund_failed: money format failed for amount_q=%s", amount_q, exc_info=True)
        amount_display = "valor a apurar"

    create_operator_alert(
        type="payment_refund_failed",
        severity="critical",
        message=(
            f"Estorno FALHOU para o pedido {order.ref} (intent {intent_ref}, {amount_display}): "
            f"{detail}. O dinheiro do cliente pode estar retido — conferir no gateway "
            "e reprocessar o estorno."
        ),
        order_ref=order.ref,
        dedupe_key=f"payment_refund_failed:{order.ref}",
    )


def cancel(order, *, reason: str = "order_cancelled") -> None:
    """Cancel an unpaid payment intent.

    Captured payments are not cancelled here; those still go through
    ``refund()`` so Payman remains the canonical payment state.
    """
    payment_data = (order.data or {}).get("payment", {})
    intent_ref = payment_data.get("intent_ref")
    if not intent_ref:
        return

    status = (get_payment_status(order) or "").lower()
    if status in {"captured", "paid", "refunded", "cancelled", "unknown"}:
        return

    method = payment_data.get("method", "pix")
    adapter = get_adapter("payment", method=method)
    if not adapter or not hasattr(adapter, "cancel"):
        return

    try:
        result = adapter.cancel(intent_ref, reason=reason)
        if result.success:
            logger.info("payment.cancel: cancelled %s for order %s", intent_ref, order.ref)
    except Exception as exc:
        logger.warning("payment.cancel: failed for order %s: %s", order.ref, exc)


# ── facades ──

_CANCELLABLE_STATUSES = {"new", "accepted"}
_PAID_STATUSES = {"captured", "paid"}
_UNCERTAIN_STATUSES = {"unknown"}


def cancel_stale_intents(order, *, keep_intent_ref: str) -> int:
    """Cancel same-order pending/authorized intents once one intent wins."""
    if not keep_intent_ref:
        return 0
    try:
        from shopman.payman import PaymentService

        count = 0
        for intent in PaymentService.get_by_order(order.ref):
            if intent.ref == keep_intent_ref:
                continue
            if intent.status not in {"pending", "authorized"}:
                continue
            try:
                PaymentService.cancel(intent.ref, reason="superseded_by_captured_payment")
                count += 1
            except Exception:
                logger.warning(
                    "payment.cancel_stale_intent_failed order=%s intent=%s",
                    order.ref,
                    intent.ref,
                    exc_info=True,
                )
        return count
    except Exception:
        logger.debug("payment.cancel_stale_intents_failed order=%s", order.ref, exc_info=True)
        return 0


def get_payment_status(order) -> str | None:
    """
    Retorna o status canônico de pagamento via Payman.

    Consulta PaymentService pelo intent_ref. Retorna None para pedidos sem
    intent/status (dinheiro ainda não recebido: COD por acertar, loja online
    a pagar no balcão). Venda em dinheiro do PDV tem intent capturado e
    responde ``"captured"`` como qualquer outro método. Se existe intent mas
    Payman não responde, retorna ``"unknown"`` para impedir decisões
    operacionais fail-open.
    """
    payment_data = (order.data or {}).get("payment") or {}
    embedded_status = _embedded_payment_status(payment_data)
    intent_ref = payment_data.get("intent_ref")
    if not intent_ref:
        return embedded_status
    try:
        from shopman.payman import PaymentService
        intent = PaymentService.get(intent_ref)
        return intent.status
    except Exception:
        logger.warning(
            "get_payment_status: unable to read intent for order %s intent=%s",
            order.ref,
            intent_ref,
            exc_info=True,
        )
        return "unknown"


def captured_balance_q(order) -> int | None:
    """Return captured minus refunded amount for the order intent, if readable."""
    payment_data = (order.data or {}).get("payment") or {}
    intent_ref = payment_data.get("intent_ref")
    if not intent_ref:
        return None
    return _payman_captured_balance_q(intent_ref)


def has_sufficient_captured_payment(order) -> bool:
    """True when Payman shows captured funds still covering the order total."""
    payment_data = (order.data or {}).get("payment") or {}
    status = (get_payment_status(order) or "").lower()
    if status not in _PAID_STATUSES | {"refunded"}:
        return False

    intent_ref = payment_data.get("intent_ref")
    if not intent_ref:
        # Compatibility for imported/legacy orders without Payman intent.
        return status in _PAID_STATUSES

    balance_q = _payman_captured_balance_q(intent_ref)
    if balance_q is None:
        return False
    return balance_q >= int(getattr(order, "total_q", 0) or 0)


def can_cancel(order) -> bool:
    """
    True se o pedido pode ser cancelado pelo cliente.

    Requer: status in {new, confirmed} e pagamento comprovadamente não capturado.
    Estados incertos bloqueiam cancelamento para não cancelar um pedido que pode
    já estar pago.
    """
    if order.status not in _CANCELLABLE_STATUSES:
        return False
    status = (get_payment_status(order) or "").lower()
    if status in _UNCERTAIN_STATUSES or has_sufficient_captured_payment(order):
        return False
    return True


def verify_gateway_before_timeout_cancel(order) -> str:
    """Consulta o gateway ANTES de auto-cancelar um PIX por timeout.

    Um webhook perdido deixa o pedido "não pago" localmente com o dinheiro
    capturado na EFI — cancelar seria perda real do cliente. Retorna:

      ``"paid"``          — gateway mostra captura; o Payman foi reconciliado
                            e o caminho de pago (on_paid) foi disparado;
      ``"unpaid"``        — gateway respondeu e não há pagamento (cancelar ok);
      ``"indeterminate"`` — sem resposta confiável (NÃO cancelar nesta rodada).
    """
    payment_data = (order.data or {}).get("payment") or {}
    method = str(payment_data.get("method") or "").lower()
    intent_ref = payment_data.get("intent_ref")
    if method != "pix" or not intent_ref:
        return "unpaid"

    adapter = get_adapter("payment", method="pix")
    if adapter is None:
        return "unpaid"

    # ── A pergunta é de LEITURA, e a resposta não pode ter efeito colateral ──
    #
    # Aqui se perguntava com ``adapter.capture()``, e capture é verbo de escrita.
    # No adapter da Efí ele é "confere no gateway e, se CONCLUIDA, reconcilia" —
    # inofensivo. No ``payment_mock`` ele captura INCONDICIONALMENTE e devolve
    # sucesso. Com o mock configurado (que é o caso do staging), todo PIX que
    # vencia sem ninguém pagar era promovido a "pago" aqui: estoque baixado,
    # cozinha acionada, cliente avisado. E o gatilho não era nem o worker — era o
    # próprio cliente recarregando o acompanhamento, que chama
    # ``resolve_timeouts_if_due`` a cada GET.
    #
    # ``check_gateway_status`` é o verbo de leitura, e o docstring dele no adapter
    # da Efí já dizia para que serve: "safety check before cancelling expired
    # intents". Ele existia e não estava sendo usado.
    check_gateway_status = getattr(adapter, "check_gateway_status", None)
    if check_gateway_status is None:
        # Adapter sem verbo de leitura não autoriza captura por dedução: inventar
        # pagamento é pior do que adiar o cancelamento por mais uma rodada.
        logger.warning(
            "payment.timeout_gateway_check_unsupported order=%s adapter=%s",
            order.ref,
            getattr(adapter, "__name__", adapter),
        )
        return "indeterminate"

    try:
        gateway_state = str(check_gateway_status(intent_ref) or "")
    except Exception:
        logger.warning("payment.timeout_gateway_check_failed order=%s", order.ref, exc_info=True)
        return "indeterminate"

    if gateway_state != "captured":
        # "pending"/"cancelled": o gateway respondeu e não há pagamento.
        # "not_found": o intent nunca existiu, então também não há pagamento —
        # e isto NÃO é incerteza, senão a directive de timeout tenta para sempre
        # um pedido que nunca teve cobrança.
        # Qualquer outra coisa ("error", status novo do provedor) é estado
        # incerto, e incerto espera.
        return (
            "unpaid"
            if gateway_state in {"pending", "cancelled", "not_found"}
            else "indeterminate"
        )

    # Só AQUI, já sabendo que o gateway tem captura, é que se escreve.
    #
    # E antes de escrever, perguntar se já não está escrito: o Payman admite UMA
    # captura por intent, então recapturar um intent já reconciliado devolve
    # ``invalid_transition``. Como o código lia qualquer falha que não fosse
    # "error" como "não pago", um pedido efetivamente PAGO era cancelado quando
    # outro caminho reconciliava primeiro. É a mesma perda de dinheiro do cliente
    # que este módulo existe para impedir, pela porta de trás.
    from shopman.payman import PaymentError, PaymentService

    try:
        already_captured_q = PaymentService.captured_total(intent_ref)
    except PaymentError:
        already_captured_q = 0

    if already_captured_q > 0:
        transaction_id = ""
        captured_amount_q = already_captured_q
    else:
        try:
            result = adapter.capture(intent_ref)
        except Exception:
            logger.warning(
                "payment.timeout_gateway_capture_failed order=%s", order.ref, exc_info=True
            )
            return "indeterminate"

        if not result.success:
            # O gateway disse "captured" e a reconciliação não fechou: divergência
            # real, que não se resolve cancelando o pedido do cliente.
            logger.warning(
                "payment.timeout_gateway_capture_rejected order=%s error=%s",
                order.ref,
                result.error_code,
            )
            return "indeterminate"

        transaction_id = result.transaction_id
        captured_amount_q = result.amount_q

    # Pagou e o webhook se perdeu: promover ao caminho de pago. SOB LOCK +
    # re-check de captured_at — dois resolvers concorrentes (handler do
    # directive + resolve lazy no acesso) não podem despachar on_paid duas
    # vezes. Só quem carimba captured_at primeiro segue para o dispatch.
    from django.db import transaction
    from shopman.orderman.models import Order

    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        locked_payment = dict((locked.data or {}).get("payment") or {})
        if locked_payment.get("captured_at"):
            order.refresh_from_db()
            return "paid"  # outro resolver já promoveu — não duplicar
        locked_payment["transaction_id"] = transaction_id
        locked_payment["captured_at"] = timezone.now().isoformat()
        locked_data = dict(locked.data or {})
        locked_data["payment"] = locked_payment
        locked.data = locked_data
        locked.save(update_fields=["data", "updated_at"])

    order.refresh_from_db()
    cancel_stale_intents(order, keep_intent_ref=intent_ref)
    order.emit_event(
        event_type="payment.captured",
        actor="payment.timeout_gateway_check",
        payload={"method": "pix", "amount_q": captured_amount_q or order.total_q},
    )

    from shopman.shop.lifecycle import dispatch

    dispatch(order, "on_paid")
    return "paid"


def mock_capture_allowed(method: str | None = None) -> bool:
    """A captura simulada está liberada NESTE ambiente, para ESTE método?

    Dono ÚNICO da pergunta — o endpoint (``storefront/api/payment.py``) e a
    projection do acompanhamento (``projections/order_tracking.py``) consultam
    esta função, e não cada um a sua fórmula.

    ⚠️ **Duas perguntas diferentes, dois interruptores.**
    ``SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS`` responde "este ambiente pode rodar com
    gateway simulado?", e existe para o check ``SHOPMAN_E003`` não reprovar o
    deploy de um staging sem credenciais. Ele **não** pode responder também
    "o cliente pode quitar o próprio pedido com um clique?" — enquanto respondia,
    a loja pública de staging (DEBUG=False, ALLOW_MOCK=true) mostrava o botão
    "Simular pagamento" na tela de Pix de qualquer visitante, e um clique
    disparava ``on_paid``: estoque baixado, cozinha acionada, produto entregue.

    Por isso a afordância de teste tem interruptor próprio,
    ``SHOPMAN_EXPOSE_MOCK_CAPTURE``, que nasce desligado. Ligar é decisão
    consciente de quem conduz uma rodada de testes, e desligar fecha a porta sem
    tocar em adapter nem arriscar o deploy.

    ⚠️ **E o método importa.** ``mock_confirm`` captura falando direto com o
    Payman, sem passar pelo adapter — então "simular" um pagamento cujo gateway é
    REAL grava captura local que o gateway não tem. Num ambiente híbrido (PIX no
    mock para o roteiro de teste, cartão no Stripe test para valer), o botão no
    pedido de cartão produziria exatamente essa divergência, destruindo a
    fidelidade que ir para o gateway real existe para comprar.

    Por isso, com ``method``, a resposta exige também que o adapter DAQUELE método
    seja o simulado. A regra deriva da configuração em vez de fixar ``"pix"``: no
    dia em que o PIX apontar para a Efí, o botão some sozinho, sem env nova e sem
    ninguém lembrar de mudar código.
    """
    from django.conf import settings

    if not (settings.DEBUG or getattr(settings, "SHOPMAN_EXPOSE_MOCK_CAPTURE", False)):
        return False
    if method is None:
        return True
    adapters = getattr(settings, "SHOPMAN_PAYMENT_ADAPTERS", {}) or {}
    return "payment_mock" in str(adapters.get(str(method).lower()) or "")


def mock_confirm(order) -> bool:
    """DEV helper: simulate capture for local payment testing.

    Payman remains the canonical status source. This helper simulates the
    gateway side only: authorize/capture the intent, record display metadata,
    and dispatch the same paid lifecycle hook used by production webhooks.
    It must not move ``Order.status`` directly.
    """
    current_status = (get_payment_status(order) or "").lower()
    if current_status == "captured":
        return False
    if current_status == "unknown":
        logger.warning("mock_confirm: refusing unknown payment state for order %s", order.ref)
        return False

    from shopman.payman import PaymentError, PaymentService

    payment_data = dict((order.data or {}).get("payment", {}))
    intent_ref = payment_data.get("intent_ref")
    if not intent_ref:
        logger.warning("mock_confirm: refusing order %s without payment intent", order.ref)
        return False

    try:
        intent = PaymentService.get(intent_ref)
        if intent.status == "pending":
            PaymentService.authorize(intent_ref, gateway_id=f"mock_confirm_{intent_ref}")
            intent = PaymentService.get(intent_ref)
        if intent.status in ("pending", "authorized"):
            PaymentService.capture(intent_ref)
    except PaymentError as exc:
        logger.warning(
            "mock_confirm: payment transition failed: %s",
            exc,
            extra={"intent_ref": intent_ref, "order_ref": order.ref},
        )
        return False

    payment_data["captured_at"] = timezone.now().isoformat()
    data = dict(order.data or {})
    data["payment"] = payment_data
    order.data = data
    order.save(update_fields=["data", "updated_at"])

    method = payment_data.get("method", "pix")
    order.emit_event(
        event_type="payment.captured",
        actor="mock_payment",
        payload={"method": method, "amount_q": payment_data.get("amount_q", order.total_q)},
    )

    from shopman.shop.lifecycle import dispatch

    dispatch(order, "on_paid")

    return True


# ── helpers ──


def _extract_qr_data(intent: PaymentIntent) -> dict:
    """Extract QR code data from intent metadata or client_secret."""
    if intent.metadata:
        return intent.metadata

    if intent.client_secret:
        try:
            return json.loads(intent.client_secret)
        except (json.JSONDecodeError, TypeError):
            pass

    return {}


def _ensure_payment_idempotency_key(
    order,
    *,
    payment_data: dict,
    method: str,
    amount_q: int,
) -> str:
    """Return a stable key for this payment attempt and persist it when possible."""
    existing = str(payment_data.get("idempotency_key") or "").strip()
    if existing and _payment_idempotency_key_reusable(
        existing,
        order=order,
        method=method,
        amount_q=amount_q,
    ):
        return existing

    # Chave DETERMINÍSTICA (sem uuid): dois initiates concorrentes calculam a
    # mesma chave e convergem no MESMO intent via constraint do Payman — o
    # sufixo aleatório criava duas cobranças "irmãs" e o pedido apontava para
    # a que o cliente talvez não pagasse. A geração só avança quando a
    # tentativa anterior morreu (failed/cancelled), preservando o re-attempt.
    generation = _burned_intent_generations(order, method=method)
    key = f"order-payment:{order.ref}:{method}:{amount_q}:g{generation}"
    payment_data["idempotency_key"] = key
    data = dict(order.data or {})
    data["payment"] = payment_data
    order.data = data
    try:
        order.save(update_fields=["data", "updated_at"])
    except Exception:
        logger.warning("payment.idempotency_key_persist_failed order=%s", order.ref, exc_info=True)
    return key


def _burned_intent_generations(order, *, method: str) -> int:
    """Quantas tentativas de pagamento deste pedido/método já morreram."""
    try:
        from shopman.payman import PaymentIntent as PaymanIntent

        return PaymanIntent.objects.filter(
            order_ref=order.ref,
            method=method,
            status__in=[PaymanIntent.Status.FAILED, PaymanIntent.Status.CANCELLED],
        ).count()
    except Exception:
        logger.debug("payment.generation_lookup_failed order=%s", order.ref, exc_info=True)
        return 0


def _payment_idempotency_key_reusable(
    key: str,
    *,
    order,
    method: str,
    amount_q: int,
) -> bool:
    """Return False when a stored key points to a terminal failed attempt."""
    try:
        from shopman.payman import PaymentIntent as PaymanIntent

        intent = PaymanIntent.objects.filter(idempotency_key=key).first()
    except Exception:
        logger.debug("payment.idempotency_key_lookup_failed order=%s", order.ref, exc_info=True)
        return True

    if intent is None:
        return True
    if intent.order_ref != order.ref or intent.method != method or intent.amount_q != amount_q:
        logger.warning(
            "payment.idempotency_key_mismatch order=%s intent=%s key=%s",
            order.ref,
            intent.ref,
            key,
        )
        return False
    if intent.status in {"failed", "cancelled", "refunded"}:
        logger.info(
            "payment.idempotency_key_terminal_retry order=%s intent=%s status=%s",
            order.ref,
            intent.ref,
            intent.status,
        )
        return False
    return True


def _existing_active_intent(order, *, method: str, amount_q: int) -> PaymentIntent | None:
    """Return a reusable Payman intent for this order/method/amount, if any."""
    try:
        from shopman.payman import PaymentService

        now = timezone.now()
        intents = (
            PaymentService.get_by_order(order.ref)
            .filter(method=method, amount_q=amount_q)
            .exclude(status__in={"failed", "cancelled", "refunded"})
            .order_by("-created_at", "-id")
        )
        candidates = list(intents)
        for intent in candidates:
            if intent.status == "captured":
                return _payment_intent_from_payman(intent)
        for intent in candidates:
            if intent.expires_at and intent.expires_at <= now:
                continue
            return _payment_intent_from_payman(intent)
    except Exception:
        logger.debug("payment.existing_intent_lookup_failed order=%s", order.ref, exc_info=True)
    return None


def _payment_intent_from_payman(intent) -> PaymentIntent:
    gateway_data = dict(intent.gateway_data or {})
    client_secret = gateway_data.get("client_secret")
    metadata = dict(gateway_data)
    if client_secret:
        try:
            parsed = json.loads(client_secret)
        except (TypeError, json.JSONDecodeError):
            parsed = {}
        if isinstance(parsed, dict):
            metadata.update(parsed)

    return PaymentIntent(
        intent_ref=intent.ref,
        status=intent.status,
        amount_q=intent.amount_q,
        currency=intent.currency,
        client_secret=client_secret,
        expires_at=intent.expires_at,
        gateway_id=intent.gateway_id,
        metadata=metadata,
    )


def _record_initiate_error(
    order,
    *,
    payment_data: dict,
    method: str,
    amount_q: int,
    error: str,
) -> None:
    error_message = str(error or "Falha ao gerar pagamento.")[:200]
    order.data["payment"] = {
        **payment_data,
        "method": method,
        "amount_q": amount_q,
        "error": error_message,
    }
    order.save(update_fields=["data", "updated_at"])
    _create_payment_failed_alert(order, method=method, error=error_message)
    _notify_payment_failed(order)


def _create_payment_failed_alert(order, *, method: str, error: str) -> None:
    try:
        from shopman.shop.adapters import alert as alert_adapter

        debounce_cutoff = timezone.now() - timedelta(minutes=15)
        if alert_adapter.recent_exists(
            "payment_failed",
            debounce_cutoff,
            order_ref=order.ref,
        ):
            return
        alert_adapter.create(
            "payment_failed",
            "error",
            (
                f"Falha ao gerar pagamento {method.upper()} do pedido {order.ref}. "
                "Cliente mantido na tela de pagamento para tentar novamente. "
                f"Erro: {error}"
            ),
            order_ref=order.ref,
        )
    except Exception:
        logger.warning("payment_failed_alert_create_failed order=%s", order.ref, exc_info=True)


def _notify_payment_failed(order) -> None:
    try:
        from shopman.shop.services import notification

        notification.send(order, "payment_failed")
    except Exception:
        logger.warning("payment_failed_notification_queue_failed order=%s", order.ref, exc_info=True)


def _ack_payment_failed_alerts(order) -> None:
    try:
        from shopman.shop.adapters import alert as alert_adapter

        alert_adapter.acknowledge("payment_failed", order_ref=order.ref)
    except Exception:
        logger.debug("payment_failed_alert_ack_failed order=%s", order.ref, exc_info=True)


def _embedded_payment_status(payment_data: dict) -> str | None:
    status = str(payment_data.get("status") or "").strip().lower()
    return status or None


def _schedule_payment_timeout(order, intent: PaymentIntent) -> None:
    """Queue cancellation for unpaid digital payments at the gateway deadline."""
    try:
        from shopman.orderman.models import Directive

        from shopman.shop.directives import PAYMENT_TIMEOUT

        dedupe_key = f"{PAYMENT_TIMEOUT}:{order.ref}:{intent.intent_ref}"
        payload = {
            "order_ref": order.ref,
            "intent_ref": intent.intent_ref,
            "expires_at": intent.expires_at.isoformat(),
        }
        existing = Directive.objects.filter(
            topic=PAYMENT_TIMEOUT,
            dedupe_key=dedupe_key,
            status__in=[Directive.Status.QUEUED, Directive.Status.RUNNING],
        ).first()
        if existing:
            existing.payload = payload
            existing.available_at = intent.expires_at
            existing.save(update_fields=["payload", "available_at", "updated_at"])
            return

        from shopman.shop.directives import create_deduped

        create_deduped(
            PAYMENT_TIMEOUT,
            payload=payload,
            available_at=intent.expires_at,
            dedupe_key=dedupe_key,
        )
    except Exception:
        logger.warning("payment.timeout_schedule_failed order=%s", order.ref, exc_info=True)


def _adapter_config(order, *, method: str) -> dict:
    try:
        from shopman.shop.config import ChannelConfig

        cfg = ChannelConfig.for_channel(order.channel_ref)
    except Exception:
        logger.debug("payment.adapter_config_failed order=%s", order.ref, exc_info=True)
        return {}

    config: dict = {}
    if method == "pix":
        config["pix_timeout_minutes"] = cfg.payment.timeout_minutes
        if getattr(settings, "SHOPMAN_MOCK_PIX_AUTO_CONFIRM", False):
            config["mock_pix_auto_confirm"] = True
            config["mock_pix_confirm_delay_seconds"] = getattr(
                settings,
                "SHOPMAN_MOCK_PIX_CONFIRM_DELAY_SECONDS",
                10,
            )
    if method == "card":
        stripe_config = getattr(settings, "SHOPMAN_STRIPE", {}) or {}
        capture_method = str(stripe_config.get("capture_method") or "manual").strip().lower()
        config["capture_method"] = capture_method if capture_method in {"automatic", "manual"} else "manual"
    return config


def _payman_intent_captured(intent_ref: str) -> bool:
    """Return True if the Payman intent is already captured. Fails silently."""
    try:
        from shopman.payman import PaymentService
        intent = PaymentService.get(intent_ref)
        return intent.status in ("captured", "paid", "refunded")
    except Exception:
        logger.exception("payment._payman_intent_captured: error checking intent_ref=%s", intent_ref)
        return False


def _payman_captured_balance_q(intent_ref: str) -> int | None:
    """Return captured minus refunded amount for a Payman intent."""
    try:
        from shopman.payman import PaymentService

        return PaymentService.captured_total(intent_ref) - PaymentService.refunded_total(intent_ref)
    except Exception:
        logger.exception("payment._payman_captured_balance_q: error checking intent_ref=%s", intent_ref)
        return None


def _payman_refundable_amount(intent_ref: str) -> int | None:
    """Return remaining refundable captured balance, or None if unreadable."""
    balance_q = _payman_captured_balance_q(intent_ref)
    if balance_q is None:
        return None
    return max(0, balance_q)


def _payman_intent_refunded(intent_ref: str) -> bool:
    """Return True only if the Payman intent is fully refunded."""
    refundable_q = _payman_refundable_amount(intent_ref)
    if refundable_q is None:
        return False
    return refundable_q <= 0
