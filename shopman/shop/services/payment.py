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
from importlib import import_module

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from shopman.shop.adapters import get_adapter
from shopman.shop.adapters.payment_types import PaymentIntent, PaymentResult
from shopman.shop.services import order_composition, payment_deadline

logger = logging.getLogger(__name__)


#: Formas que passam por GATEWAY REMOTO: a cobrança nasce numa rede que não é a
#: nossa, e a verdade volta por webhook. Fora daqui estão as formas do BALCÃO —
#: dinheiro, crédito e débito na maquininha física —, onde o operador atesta o
#: que aconteceu e não há webhook para esperar.
_GATEWAY_METHODS = frozenset({"pix", "card", "link"})

#: Das de gateway, as que vivem numa SESSÃO HOSPEDADA (Stripe Checkout): o
#: cliente abre uma URL e paga lá. O Pix fica de fora — a prova dele é o QR, e a
#: cobrança expira sozinha. São estas que têm `checkout_url` para mostrar e que a
#: reconciliação tardia sabe reconsultar.
#:
#: Público de propósito: o webhook do Stripe, o `reconcile_payments` e o
#: acompanhamento do cliente perguntam "é sessão hospedada?" a ESTE conjunto.
#: Enquanto cada um tinha o seu literal `"card"`, o `link` ficava de fora dos
#: três — pago no gateway e nunca capturado, sem rede contra webhook perdido e
#: sem botão de pagar para quem voltava ao pedido.
HOSTED_CHECKOUT_METHODS = frozenset({"card", "link"})

# Provider operations are routed by the gateway persisted on the Payman intent,
# not by today's shop setting.  A config flip must not send an old mock intent
# to Efí, nor an old Efí intent to the mock after rollback.
_PAYMENT_GATEWAY_ADAPTER_PATHS = {
    "efi": "shopman.shop.adapters.payment_efi",
    "mock": "shopman.shop.adapters.payment_mock",
    "stripe": "shopman.shop.adapters.payment_stripe",
}


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

    if settles_without_gateway(method):
        if payment_data.get("intent_ref"):
            return
        settle_terminal_tenders(order)
        return

    # O total que vale AGORA: pedido editado enquanto novo (concierge, Gestor)
    # tem o total no ajuste, e o ``total_q`` selado é o de nascimento. Cobrar o
    # selado mandava ao cliente um Pix com o valor antigo (P0-6).
    amount_q = order_composition.effective_total_q(order)
    adapter = get_adapter("payment", method=method)
    route_by_persisted_gateway = str(method).lower() == "pix"
    expected_gateway = (
        (_gateway_for_adapter(adapter) or "__unresolved__")
        if route_by_persisted_gateway
        else None
    )
    resume_creation = False

    # Idempotent only inside the same provider route.  On a config flip, an old
    # pending/authorized mock charge is kept for explicit reconciliation; it is
    # neither adopted by Efí nor silently cancelled/replaced.  Captured remains
    # a payment fact and is never charged again.
    if (intent_ref := payment_data.get("intent_ref")) and not _retire_intent_with_old_amount(
        order, payment_data=payment_data, method=method, amount_q=amount_q, intent_ref=intent_ref,
    ):
        return
    if intent_ref := payment_data.get("intent_ref"):
        persisted = _payman_intent(intent_ref)
        if (
            route_by_persisted_gateway
            and persisted is not None
            and persisted.status != "captured"
            and persisted.gateway != expected_gateway
        ):
            expected_label = (
                expected_gateway
                if expected_gateway != "__unresolved__"
                else "um adapter sem rota de gateway reconhecida"
            )
            _record_initiate_error(
                order,
                payment_data=payment_data,
                method=method,
                amount_q=amount_q,
                error=(
                    f"A cobrança pendente pertence ao gateway {persisted.gateway or 'local'}, "
                    f"mas Pix agora usa {expected_label}. Reconcilie a cobrança anterior antes de gerar outra."
                ),
            )
            return
        if (
            route_by_persisted_gateway
            and persisted is not None
            and persisted.gateway == "efi"
            and not _efi_intent_environment_matches_runtime(persisted)
        ):
            return
        if not _pix_intent_needs_creation_resume(persisted, expected_gateway=expected_gateway):
            if (
                route_by_persisted_gateway
                and persisted is not None
                and persisted.gateway == "efi"
                and (persisted.gateway_data or {}).get("client_secret")
                and not (payment_data.get("copy_paste") or payment_data.get("qr_code"))
            ):
                _persist_intent(
                    order,
                    payment_data=payment_data,
                    method=method,
                    amount_q=amount_q,
                    intent=_payment_intent_from_payman(persisted),
                )
            return
        # A Efí já pode ter aceitado o PUT e falhado apenas ao buscar o QR. O
        # adapter tem um cursor durável (txid + loc) e sabe retomar no MESMO
        # intent. Reusar exatamente a chave original é o que impede outro PUT
        # e outra cobrança irmã.
        persisted_key = str(getattr(persisted, "idempotency_key", "") or "").strip()
        if not persisted_key:
            _record_initiate_error(
                order,
                payment_data=payment_data,
                method=method,
                amount_q=amount_q,
                error=(
                    "A cobrança Pix ficou sem QR e não possui chave segura para retomada. "
                    "Reconcilie a cobrança antes de tentar novamente."
                ),
            )
            return
        payment_data["idempotency_key"] = persisted_key
        resume_creation = True

    if not resume_creation:
        existing_intent = _existing_active_intent(
            order, method=method, amount_q=amount_q, gateway=expected_gateway,
        )
        if existing_intent:
            _persist_intent(order, payment_data=payment_data, method=method, amount_q=amount_q, intent=existing_intent)
            logger.info(
                "payment.initiate: reused existing %s intent %s for order %s",
                method,
                existing_intent.intent_ref,
                order.ref,
            )
            return

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

    try:
        idempotency_key = _ensure_payment_idempotency_key(
            order,
            payment_data=payment_data,
            method=method,
            amount_q=amount_q,
        )
    except PaymentAttemptLookupUnavailable:
        # Sem conseguir ler as tentativas anteriores no Payman, qualquer chave
        # é um chute: a guardada pode estar envenenada por uma falha terminal
        # (o gateway repete a falha e o cliente não consegue pagar) e uma nova
        # pode ser irmã de uma cobrança viva. Não cobramos no escuro.
        _record_initiate_error(
            order,
            payment_data=payment_data,
            method=method,
            amount_q=amount_q,
            error="Não conseguimos conferir a cobrança anterior. Tente de novo em instantes.",
        )
        return
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
        existing_intent = _existing_active_intent(
            order, method=method, amount_q=amount_q, gateway=expected_gateway,
        )
        if existing_intent:
            _persist_intent(order, payment_data=payment_data, method=method, amount_q=amount_q, intent=existing_intent)
            if method == "pix" and not existing_intent.client_secret:
                _record_initiate_error(
                    order,
                    payment_data=dict((order.data or {}).get("payment") or {}),
                    method=method,
                    amount_q=amount_q,
                    error=str(exc),
                )
                return
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
        method,
        intent.intent_ref,
        order.ref,
    )


_INTENT_PRESENTATION_KEYS = ("intent_ref", "idempotency_key", "qr_code", "copy_paste", "expires_at", "checkout_url")


def _retire_intent_with_old_amount(order, *, payment_data: dict, method: str, amount_q: int, intent_ref: str) -> bool:
    """A cobrança viva do pedido tem o valor de antes da edição? Cancela e libera a nova.

    O cliente nunca pode ter na mão um QR com o valor errado: a cobrança
    pendente (ou autorizada) com valor diferente do total efetivo é cancelada no
    provedor (``cancel_stale_intents``, que só dá baixa local depois do sim do
    gateway) e o ``order.data["payment"]`` perde os dados dela, para o
    ``initiate`` abrir a cobrança com o valor novo.

    Devolve ``False`` quando a cobrança velha não pôde ser cancelada: o erro fica
    gravado no pedido e nada novo é criado (dois QR vivos com valores diferentes
    é pior do que nenhum). Cobrança capturada é fato e não se toca aqui.
    """
    persisted = _payman_intent(intent_ref)
    if persisted is None or persisted.status not in {"pending", "authorized"}:
        return True
    if int(persisted.amount_q or 0) == int(amount_q):
        return True
    cancel_stale_intents(order, keep_intent_ref="", reason="superseded_by_order_edit")
    refreshed = _payman_intent(intent_ref)
    if refreshed is None or refreshed.status in {"pending", "authorized"}:
        _record_initiate_error(
            order,
            payment_data=payment_data,
            method=method,
            amount_q=amount_q,
            error=(
                "A cobrança anterior tem o valor de antes da alteração e não pôde ser cancelada. "
                "Cancele essa cobrança antes de gerar outra."
            ),
        )
        return False
    logger.info(
        "payment.initiate: retired %s intent %s (amount %s) for order %s, new total %s",
        method, intent_ref, persisted.amount_q, order.ref, amount_q,
    )
    for key in _INTENT_PRESENTATION_KEYS:
        payment_data.pop(key, None)
    data = dict(order.data or {})
    data["payment"] = payment_data
    order.data = data
    order.save(update_fields=["data", "updated_at"])
    return True


def restore_existing_intent(order) -> bool:
    """Restore a persisted Payman intent to Order data without contacting a provider."""
    payment_data = dict((order.data or {}).get("payment") or {})
    method = payment_data.get("method")
    amount_q = order_composition.effective_total_q(order)
    route_by_persisted_gateway = str(method or "").lower() == "pix"
    expected_gateway = (
        _gateway_for_adapter(get_adapter("payment", method=method)) or "__unresolved__"
        if route_by_persisted_gateway
        else None
    )
    if payment_data.get("intent_ref"):
        from shopman.payman import PaymentService

        try:
            intent = PaymentService.get(payment_data["intent_ref"])
        except Exception:
            logger.warning("payment.restore_existing_intent_failed order=%s", order.ref)
            return False
        return (
            intent.order_ref == order.ref
            and intent.method == method
            and intent.amount_q == amount_q
            and (
                not route_by_persisted_gateway
                or intent.status == "captured"
                or intent.gateway == expected_gateway
            )
        )
    existing = _existing_active_intent(
        order, method=method, amount_q=amount_q, gateway=expected_gateway,
    )
    if existing is None:
        return False
    _persist_intent(order, payment_data=payment_data, method=method, amount_q=amount_q, intent=existing)
    return True


def _persist_intent(
    order,
    *,
    payment_data: dict,
    method: str,
    amount_q: int,
    intent: PaymentIntent,
) -> None:
    from django.db import transaction
    from shopman.orderman.models import Order

    from shopman.shop.services.payment_provenance import confirmation_provenance

    # Financial provenance belongs to the persisted charge, not to a later
    # webhook payload.  Copy it as soon as the Efí intent exists so even a
    # pending sandbox order cannot appear as real revenue in Order-based BI.
    persisted_intent = _payman_intent(intent.intent_ref)
    provenance = confirmation_provenance(persisted_intent or intent)

    def persist_into(target) -> dict:
        locked_data = dict(target.data or {})
        current_payment = dict(locked_data.get("payment") or {})
        # Build payment data to save — intent_ref + method + display fields only.
        # Status is NOT stored here; Payman (PaymentService) is the canonical source.
        result = {
            **payment_data,
            **current_payment,
            "intent_ref": intent.intent_ref,
            "amount_q": amount_q,
            "method": method,
            **provenance,
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
                qr_data.get("brcode") or qr_data.get("copy_paste") or qr_data.get("qrcode")
            )
        elif method in HOSTED_CHECKOUT_METHODS:
            # Sessão hospedada (Stripe Checkout): a URL que o cliente abre para pagar.
            checkout_url = (intent.metadata or {}).get("checkout_url")
            if checkout_url:
                result["checkout_url"] = checkout_url
        # O prazo é de quem TEM prazo, não de um método: o QR do Pix e o link de
        # pagamento vencem, e os dois precisam dizer isso ao cliente ("vale até …")
        # e ao `payment.timeout` (logo abaixo). Enquanto a chave só era gravada no
        # ramo do Pix, o link nascia com prazo no Payman e sem prazo no pedido.
        if intent.expires_at:
            result["expires_at"] = intent.expires_at.isoformat()

        locked_data["payment"] = result
        target.data = locked_data
        target.save(update_fields=["data", "updated_at"])
        return locked_data

    # A confirmação pode chegar entre o PUT da cobrança e a busca/persistência
    # do QR. Leia o JSON canônico sob lock: recibos, e2e, captured_at e
    # provenance escritos pelo webhook vencem o snapshot anterior do initiate;
    # somente os artefatos de apresentação acima são atualizados por nós.
    if isinstance(order, Order) and getattr(order, "pk", None) is not None:
        with transaction.atomic():
            locked = Order.objects.select_for_update().get(pk=order.pk)
            persisted_data = persist_into(locked)
    else:
        # Adapter/service unit tests intentionally use lightweight Order
        # protocols. Preserve that supported seam without attempting a DB lock.
        persisted_data = persist_into(order)

    order.data = persisted_data
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
        existing_intent = _existing_active_intent(
            order, method=method, amount_q=amount_q, gateway="",
        )
        if existing_intent and existing_intent.status == "captured":
            settled[method] = existing_intent.intent_ref
            logger.info(
                "payment.settle_terminal_tenders: reused captured %s intent %s for order %s",
                method,
                existing_intent.intent_ref,
                order.ref,
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
            gateway_data = {"collection": "terminal", "terminal_ref": _terminal_ref(order)}
            if method == "pix":
                # Quem atestou o Pix que o provedor não viu (gesto "Recebi o Pix").
                gateway_data.update(_pix_confirmation(payment_data))
            intent = PaymentService.settle(
                order.ref,
                amount_q,
                method,
                currency="BRL",
                idempotency_key=idempotency_key,
                gateway_data=gateway_data,
                asserted_at_terminal=gateway_method,
            )
        settled[method] = intent.ref
        logger.info(
            "payment.settle_terminal_tenders: %s settled at terminal, intent %s for order %s",
            method,
            intent.ref,
            order.ref,
        )

    if settled:
        _persist_tender_intents(order, payment_data=payment_data, settled=settled, single=not mixed)
    return settled


def _pix_confirmation(payment_data: dict) -> dict:
    """``{pix_confirmed_by, pix_confirmed_at}`` da linha de Pix atestada, ou ``{}``."""
    for tender in payment_data.get("tenders") or []:
        if not isinstance(tender, dict) or str(tender.get("method") or "").strip().lower() != "pix":
            continue
        if tender.get("pix_confirmed_by"):
            return {
                "pix_confirmed_by": str(tender["pix_confirmed_by"]),
                "pix_confirmed_at": str(tender.get("pix_confirmed_at") or ""),
            }
    return {}


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
        ((method, ref),) = settled.items()
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
    from django.db import transaction
    from shopman.orderman.models import Order

    if not isinstance(order, Order):
        # Unit-level adapters also use a lightweight Order protocol. The real
        # orchestration path below always receives the persisted model.
        _capture_once(order)
        return

    # Serialize the final Payman check and adapter call by the canonical order.
    # This keeps two lifecycle workers from both issuing a capture. A process
    # crash after provider acceptance still requires provider reconciliation;
    # the row lock does not claim otherwise.
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        _capture_once(locked)
        order.data = locked.data


def _capture_once(order) -> None:
    """Capture after the caller has acquired the canonical Order lock."""
    data = dict(order.data or {})
    payment_data = dict(data.get("payment") or {})
    intent_ref = payment_data.get("intent_ref")

    if not intent_ref or payment_data.get("transaction_id"):
        return

    # Payman is authoritative, and persisted callers make this check under lock.
    if _payman_intent_captured(intent_ref):
        return

    method = payment_data.get("method", "pix")
    adapter = _adapter_for_persisted_intent(intent_ref, method=method)
    if not adapter:
        return

    result = adapter.capture(intent_ref)
    if result.success:
        payment_data["transaction_id"] = result.transaction_id
        if isinstance(getattr(result, "card_funding", None), str):
            payment_data["card_funding"] = result.card_funding
        data["payment"] = payment_data
        order.data = data
        order.save(update_fields=["data", "updated_at"])
        _ack_payment_failed_alerts(order)
        cancel_stale_intents(order, keep_intent_ref=intent_ref)

        logger.info("payment.capture: captured %s for order %s", intent_ref, order.ref)
        return

    # A captura recusada fica observável e continua recuperável.
    logger.error(
        "payment.capture_failed order=%s intent=%s method=%s code=%s",
        order.ref,
        intent_ref,
        method,
        result.error_code,
    )
    _alert_capture_failed(order, intent_ref=intent_ref, method=method, result=result)


def _alert_capture_failed(order, *, intent_ref: str, method: str, result) -> None:
    """Alerta no Gestor para captura recusada pelo gateway.

    Reusa o tipo ``payment_failed`` de propósito: o modelo o define como
    "cobrança que não passou", e é exatamente o que é. Ganha de graça o
    fechamento automático — ``_ack_payment_failed_alerts`` roda na captura
    bem-sucedida, então a rodada da reconciliação que finalmente conseguir
    apaga o alerta sozinha, sem ninguém ter de reconhecer à mão o que já se
    resolveu.
    """
    from shopman.shop.services.observability import create_operator_alert

    detail = str(getattr(result, "message", "") or getattr(result, "error_code", "") or "")[:200]
    create_operator_alert(
        type="payment_failed",
        severity="error",
        message=(
            f"Não foi possível capturar o pagamento {method.upper()} do pedido "
            f"{order.ref} ({intent_ref}). O cliente autorizou e o dinheiro NÃO "
            "entrou; o pedido segue barrado em 'Aguardando pagamento'. Confira "
            f"no painel do gateway antes de entregar. Erro: {detail}"
        ),
        order_ref=order.ref,
        dedupe_key=f"payment_capture_failed:{order.ref}:{intent_ref}",
    )


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

    ⚠️ **Maquininha também NÃO se estorna aqui** (crédito, débito, cobrança
    externa, pix/cartão atestados no balcão). A captura foi atestada pelo
    operador, e o estorno só existe depois que alguém o faz NA maquininha, no
    cartão do cliente. Gravar ``REFUND`` no cancel dizia "estornado" com o
    cliente ainda cobrado (P0-2, 13/10/2026). O intent fica ``captured`` e o
    pedido aparece em ``pending_card_machine_refunds`` (PDV) e num aviso no
    Gestor até o "Estornei na maquininha" (:func:`record_card_machine_refund`).

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
    from shopman.shop.services.order_edit import CARD_MACHINE_METHODS

    intents = [
        (method, ref)
        for method, ref in _refundable_intents(order, payment_data=payment_data)
        if method != "cash" and method not in CARD_MACHINE_METHODS and not _asserted_at_terminal(ref)
    ]
    try:
        _refund_gateway_intents(
            order, intents, amount_q=amount_q, idempotency_key=idempotency_key, _from_directive=_from_directive,
        )
    finally:
        announce_card_machine_refund(order)


def _refund_gateway_intents(order, intents, *, amount_q, idempotency_key, _from_directive) -> None:
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
            logger.warning(
                "payment.refund: account intent %s cancel failed order=%s", intent.ref, order.ref, exc_info=True
            )


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
    # O fallback abaixo devolve UM intent legado; um pedido com mais de uma
    # cobrança capturada perde as demais e a devolução sai pela metade.
    except Exception:
        logger.warning("payment.refund: intent lookup failed order=%s", order.ref, exc_info=True)
        intents = []
    if not intents:
        legacy_ref = payment_data.get("intent_ref")
        return [(str(payment_data.get("method") or "pix"), legacy_ref)] if legacy_ref else []
    return sorted(((i.method, i.ref) for i in intents), key=lambda pair: (pair[0] != "cash", pair[1]))


@dataclass(frozen=True)
class PendingCashRefund:
    """Dinheiro que ainda não saiu de nenhuma gaveta: venda cancelada ou devolvida, ou encomenda reduzida."""

    order_ref: str
    amount_q: int
    intent_refs: tuple[str, ...]
    cancelled_at: str  # ISO datetime, "" quando o pedido não guarda (ou não foi cancelado)
    customer_name: str
    channel_ref: str
    #: Por que o dinheiro volta (:func:`refund_reason`): ``cancelled`` e
    #: ``returned`` devolvem tudo; ``partial_return`` (devolução de parte da venda)
    #: e ``reduced`` (encomenda editada que ficou mais barata) devolvem a diferença.
    reason: str = "cancelled"


#: Status em que o pedido devolve TUDO o que entrou (a venda deixou de existir).
_REFUND_ALL_STATUSES = frozenset({"cancelled", "returned"})


def _returned_q(order) -> int:
    """Quanto as devoluções PARCIAIS já registradas tiram do que o pedido vale."""
    return sum(
        int(record.get("refund_total_q") or 0)
        for record in (order.data or {}).get("returns") or []
        if isinstance(record, dict)
    )


def refund_reason(order) -> str:
    """Por que o dinheiro do pedido volta ao cliente.

    ``cancelled`` · ``returned`` (devolução total) · ``partial_return``
    (devolução de parte da venda) · ``reduced`` (encomenda que ficou mais barata).
    """
    status = str(order.status)
    if status in _REFUND_ALL_STATUSES:
        return "returned" if status == "returned" else "cancelled"
    return "partial_return" if (order.data or {}).get("returns") else "reduced"


def overpaid_q(order, *, payment_reads=None) -> int:
    """Quanto entrou A MAIS do que o pedido vale agora — o que falta devolver.

    O pedido vivo vale o total efetivo (``order_composition``, a encomenda
    editada) menos as devoluções PARCIAIS registradas (``returns``). O que foi
    capturado acima disso volta ao cliente. Venda cancelada/devolvida inteira
    não passa por aqui — ela devolve tudo. ``0`` quando não há o que devolver ou
    o Payman não respondeu.
    """
    from shopman.shop.services import order_composition

    if str(order.status) in _REFUND_ALL_STATUSES:
        return 0
    captured = captured_balance_q(order, payment_reads=payment_reads)
    if captured is None:
        return 0
    kept_q = max(0, order_composition.effective_total_q(order) - _returned_q(order))
    return max(0, captured - kept_q)


def _held_refund_balance(intents) -> tuple[int, list[str]]:
    from shopman.payman import PaymentService

    refs = []
    balance_q = 0
    for intent in intents:
        net = PaymentService.captured_total(intent.ref) - PaymentService.refunded_total(intent.ref)
        if net > 0:
            balance_q += net
            refs.append(intent.ref)
    return balance_q, refs


def _customer_name(data: dict) -> str:
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    return str(data.get("customer_name") or customer.get("name") or "")


def pending_cash_refunds(*, channel_ref: str | None = None) -> list[PendingCashRefund]:
    """Pedidos com dinheiro capturado que ainda precisa voltar para o cliente.

    Três casos, os três derivados de fatos que já existem — nunca uma tabela:

    - **venda cancelada/devolvida inteira**: status do pedido no Orderman +
      saldo capturado − devolvido do intent em dinheiro no Payman. Devolve tudo.
    - **devolução de parte da venda** (``returns``): o pedido segue vivo e vale
      menos o que voltou ao balcão (:func:`overpaid_q`). Devolve só isso.
    - **encomenda reduzida** (``order_edit``): o pedido segue vivo, editado, e
      o dinheiro capturado passou do total efetivo (:func:`overpaid_q`).
      Devolve só a diferença, e só do dinheiro.

    Inventar estado para ela seria o segundo dono da mesma pergunta. Dinheiro
    só: pix/cartão o gateway devolve sozinho, e a maquininha tem a sua lista
    (:func:`pending_card_machine_refunds`).
    """
    from django.db.models import Q
    from shopman.orderman.models import Order
    from shopman.payman.models import PaymentIntent

    from shopman.shop.services import order_composition

    intents = PaymentIntent.objects.filter(method="cash", gateway="", status__in={"captured", "refunded"}).order_by(
        "order_ref", "id"
    )
    by_order: dict[str, list] = {}
    for intent in intents:
        by_order.setdefault(intent.order_ref, []).append(intent)
    if not by_order:
        return []
    orders = Order.objects.filter(ref__in=list(by_order)).filter(
        Q(status__in=_REFUND_ALL_STATUSES)
        | Q(data__has_key=order_composition.KEY)
        | Q(data__has_key="returns")
    )
    if channel_ref:
        orders = orders.filter(channel_ref=channel_ref)
    pending: list[PendingCashRefund] = []
    for order in orders.order_by("updated_at"):
        balance_q, refs = _held_refund_balance(by_order.get(order.ref, []))
        reason = refund_reason(order)
        if str(order.status) not in _REFUND_ALL_STATUSES:
            balance_q = min(balance_q, overpaid_q(order))
        if balance_q <= 0:
            continue
        data = order.data or {}
        pending.append(
            PendingCashRefund(
                order_ref=order.ref,
                amount_q=balance_q,
                intent_refs=tuple(refs),
                cancelled_at=str(data.get("cancelled_at") or ""),
                customer_name=_customer_name(data),
                channel_ref=order.channel_ref,
                reason=reason,
            )
        )
    return pending


@dataclass(frozen=True)
class PendingCardMachineRefund:
    """Dinheiro que entrou pela maquininha e precisa voltar NELA, ao cartão do cliente.

    A maquininha é física e o sistema só atesta (``METHODS_WITHOUT_GATEWAY``):
    a captura foi declarada pelo operador, e o estorno também é. A pendência
    fica no *Precisa de você* do PDV (e num aviso no Gestor) até alguém estornar
    na maquininha e registrar (:func:`record_card_machine_refund`).
    """

    order_ref: str
    amount_q: int
    method: str  # "credit" · "debit" · "external" · "pix"/"card" atestados no balcão
    intent_refs: tuple[str, ...]
    customer_name: str
    channel_ref: str
    #: Por que o dinheiro volta (chave de :data:`REFUND_REASON_LABELS`).
    reason: str = "reduced"
    #: O caixa em que a venda passou na maquininha ("" quando o intent não guarda).
    terminal_ref: str = ""
    #: Quando a maquininha aprovou (ISO): é como se acha a transação para estornar.
    paid_at: str = ""
    #: NSU e autorização da maquininha, quando a captura os trouxe (TEF).
    nsu: str = ""
    authorization: str = ""


#: Os motivos de :func:`refund_reason`, como rótulo de tela (PDV, gaveta e maquininha).
REFUND_REASON_LABELS = {
    "cancelled": "Venda cancelada",
    "returned": "Venda devolvida",
    "partial_return": "Devolução de parte da venda",
    "reduced": "Encomenda ficou mais barata",
}

#: A forma, em minúscula para meio de frase ("no crédito").
CARD_MACHINE_METHOD_WORDS = {"credit": "crédito", "debit": "débito", "pix": "Pix"}

CARD_MACHINE_REFUND_ALERT = "card_machine_refund_due"


def _card_machine_intents(order_refs):
    from shopman.payman.models import PaymentIntent

    from shopman.shop.services.order_edit import ROUTE_CARD_MACHINE, refund_route

    rows = (
        PaymentIntent.objects.filter(order_ref__in=order_refs, status__in={"captured", "refunded"})
        .exclude(method__in={"cash", "account"})
        .order_by("order_ref", "id")
    )
    return [intent for intent in rows if refund_route(intent) == ROUTE_CARD_MACHINE]


def card_machine_refund_due(order, *, intents=None) -> tuple[int, list[str]]:
    """``(valor, intents)`` que ainda falta estornar NA maquininha para este pedido.

    Derivado, nunca gravado: o saldo da maquininha no Payman (capturado −
    estornado) limitado ao que passou do que o pedido ainda vale.

    - venda cancelada ou devolvida inteira: o pedido não vale nada, volta tudo
      o que entrou pela maquininha;
    - pedido vivo: vale o total efetivo (``order_composition``, a encomenda
      editada) menos as devoluções parciais. O que entrou acima disso volta.
      O que o gateway (Pix, cartão online) já devolveu saiu do capturado, e o
      que a gaveta vai devolver em dinheiro vem primeiro (o operador entrega
      nota, não estorna cartão pela metade), então a maquininha só fica com a
      parte que é dela.
    """
    if intents is None:
        intents = _card_machine_intents([order.ref])
    if not intents:
        return 0, []
    held_q, refs = _held_refund_balance(intents)
    if held_q <= 0:
        return 0, []
    if str(order.status) in _REFUND_ALL_STATUSES:
        return held_q, refs
    due_q = overpaid_q(order)
    if due_q <= 0:
        return 0, []
    from shopman.payman.models import PaymentIntent

    cash_q, _ = _held_refund_balance(
        PaymentIntent.objects.filter(order_ref=order.ref, method="cash", status__in={"captured", "refunded"})
    )
    return min(held_q, max(0, due_q - cash_q)), refs


def _intent_detail(intent) -> dict:
    data = intent.gateway_data or {}
    return {
        "terminal_ref": str(data.get("terminal_ref") or ""),
        "paid_at": intent.captured_at.isoformat() if intent.captured_at else "",
        "nsu": str(data.get("nsu") or ""),
        "authorization": str(data.get("authorization_code") or data.get("authorization") or ""),
    }


def _pending_card_machine_refund(order, intents) -> PendingCardMachineRefund | None:
    amount_q, refs = card_machine_refund_due(order, intents=intents)
    if amount_q <= 0:
        return None
    last = intents[-1]
    return PendingCardMachineRefund(
        order_ref=order.ref,
        amount_q=amount_q,
        method=str(last.method or ""),
        intent_refs=tuple(refs),
        customer_name=_customer_name(order.data or {}),
        channel_ref=order.channel_ref,
        reason=refund_reason(order),
        **_intent_detail(last),
    )


def pending_card_machine_refunds(*, channel_ref: str | None = None) -> list[PendingCardMachineRefund]:
    """Pedidos cujo dinheiro volta pela maquininha e ainda não voltou.

    Derivada como a do dinheiro, dos fatos que já existem: venda cancelada ou
    devolvida, devolução parcial ou encomenda editada que ficou mais barata,
    paga na maquininha, com saldo no Payman (:func:`card_machine_refund_due`).

    ``channel_ref`` filtra pelo canal do pedido; o PDV NÃO filtra, porque a
    maquininha não é a gaveta: a entrega cobrada no cartão também se estorna no
    balcão.
    """
    from django.db.models import Q
    from shopman.orderman.models import Order

    from shopman.shop.services import order_composition

    candidates = Order.objects.filter(
        Q(status__in=_REFUND_ALL_STATUSES)
        | Q(data__has_key=order_composition.KEY)
        | Q(data__has_key="returns")
    )
    if channel_ref:
        candidates = candidates.filter(channel_ref=channel_ref)
    by_order: dict[str, list] = {}
    for intent in _card_machine_intents(candidates.values("ref")):
        by_order.setdefault(intent.order_ref, []).append(intent)
    if not by_order:
        return []
    pending: list[PendingCardMachineRefund] = []
    for order in Order.objects.filter(ref__in=list(by_order)).order_by("updated_at"):
        item = _pending_card_machine_refund(order, by_order[order.ref])
        if item is not None:
            pending.append(item)
    return pending


def card_machine_refund_message(pending: PendingCardMachineRefund) -> str:
    """A instrução inteira, para quem não está vendo o pedido: o quê, quanto, onde, como achar."""
    from shopman.utils.monetary import format_money

    method = CARD_MACHINE_METHOD_WORDS.get(pending.method, "cartão")
    reason = REFUND_REASON_LABELS.get(pending.reason, "Venda cancelada").lower()
    clues = [f"pedido {pending.order_ref}", reason]
    paid_at = parse_datetime(pending.paid_at) if pending.paid_at else None
    if paid_at is not None:
        clues.append(f"aprovado em {timezone.localtime(paid_at).strftime('%d/%m às %H:%M')}")
    if pending.nsu:
        clues.append(f"NSU {pending.nsu}")
    if pending.authorization:
        clues.append(f"autorização {pending.authorization}")
    return (
        f"Estorne R$ {format_money(pending.amount_q)} no {method}, na maquininha ({', '.join(clues)}). "
        "O cliente só recebe de volta depois desse estorno. Feito o estorno, toque em "
        "Estornei na maquininha, na Sessão de caixa do PDV."
    )


def announce_card_machine_refund(order) -> None:
    """Avisa o Gestor que há estorno a fazer na maquininha. Nunca levanta.

    O PDV já enxerga a pendência (derivada); o aviso é para quem cancelou longe
    do balcão saber que o dinheiro do cliente ainda não voltou, e leva à Sessão
    de caixa do PDV, onde o gesto mora. Resolve sozinho no "Estornei".
    """
    try:
        intents = _card_machine_intents([order.ref])
        pending = _pending_card_machine_refund(order, intents) if intents else None
        if pending is None:
            return
        from shopman.shop.services.observability import create_operator_alert

        create_operator_alert(
            type=CARD_MACHINE_REFUND_ALERT,
            severity="error",
            message=card_machine_refund_message(pending),
            order_ref=order.ref,
            dedupe_key=f"{CARD_MACHINE_REFUND_ALERT}:{order.ref}:{pending.amount_q}",
        )
    except Exception:
        logger.warning("payment.card_machine_refund_alert_failed order=%s", order.ref, exc_info=True)


def record_card_machine_refund(order, *, actor, approved_by=None) -> int:
    """O operador estornou na maquininha: o Payman registra o estorno declarado.

    Mesmo dialeto da captura (atestada no balcão): não há gateway a chamar, o
    fato é o papel da maquininha. Devolve o valor registrado (zero quando não
    havia o que estornar). A pendência é derivada do saldo, então a segunda
    chamada não encontra o que registrar. Quem e quando ficam no evento
    ``card_machine_refund_recorded`` do pedido (``actor``, hora do evento e
    quem autorizou), e o aviso do Gestor se resolve.
    """
    from django.db import transaction as db_transaction
    from shopman.payman.models import PaymentTransaction

    from shopman.shop.handlers.alert_resolution import resolve_on_commit

    intents = _card_machine_intents([order.ref])
    remaining, _ = card_machine_refund_due(order, intents=intents)
    if remaining <= 0:
        return 0
    reason = refund_reason(order)
    recorded = 0
    with db_transaction.atomic():
        for intent in reversed(intents):
            if remaining <= 0:
                break
            take = min(_payman_refundable_amount(intent.ref) or 0, remaining)
            if take <= 0:
                continue
            count = PaymentTransaction.objects.filter(intent__ref=intent.ref, type="refund").count()
            key = f"card-machine-refund:{order.ref}:{intent.ref}:{count + 1}"
            result = _refund_without_gateway(intent.ref, amount_q=take, idempotency_key=key)
            if not result.success:
                raise ValueError(result.message or "Não deu para registrar o estorno.")
            recorded += take
            remaining -= take
        if recorded:
            order.emit_event(
                event_type="card_machine_refund_recorded",
                actor=str(actor),
                payload={
                    "amount_q": recorded,
                    "reason": reason,
                    "approved_by": approved_by.get_username() if hasattr(approved_by, "get_username") else "",
                },
            )
            resolve_on_commit(order.ref, (CARD_MACHINE_REFUND_ALERT,), actor=f"card-machine-refund:{actor}")
    logger.info("payment.record_card_machine_refund: %s for order %s", recorded, order.ref)
    return recorded


#: O motivo como o Payman o grava (``PaymentTransaction``), por :func:`refund_reason`.
_PAYMAN_REFUND_REASONS = {
    "cancelled": "order_cancelled",
    "returned": "order_returned",
    "partial_return": "order_returned",
    "reduced": "order_edited",
}


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

    É o gesto "Devolvi em dinheiro": o pedido guarda quem devolveu (``actor`` do
    evento ``cash_refund_recorded``), quando (a hora do evento), quem autorizou,
    o motivo e o turno de onde o dinheiro saiu.
    """
    from django.db import transaction as db_transaction
    from shopman.cashman import Entry
    from shopman.cashman import services as cash_ledger
    from shopman.payman import PaymentService
    from shopman.payman.models import PaymentTransaction

    if shift is None or not getattr(shift, "is_open", False):
        raise ValueError(f"Abra o caixa para devolver o dinheiro da venda {order.ref}.")

    cash_intents = [
        ref
        for method, ref in _refundable_intents(order, payment_data=(order.data or {}).get("payment") or {})
        if method == "cash"
    ]
    # Venda cancelada devolve tudo; encomenda viva (editada, mais barata)
    # devolve só o que passou do total — nunca o dinheiro do que ela ainda vale.
    limit_q = None if str(order.status) in _REFUND_ALL_STATUSES else overpaid_q(order)
    with db_transaction.atomic():
        refunded_q = 0
        refunded_refs = []
        for intent_ref in cash_intents:
            balance_q = _payman_refundable_amount(intent_ref) or 0
            if limit_q is not None:
                balance_q = min(balance_q, limit_q - refunded_q)
            if balance_q <= 0:
                continue
            # A chave é por DEVOLUÇÃO: a encomenda reduzida devolve a diferença e,
            # se depois for cancelada, devolve o resto — a mesma chave para as
            # duas calaria a segunda. A primeira mantém a chave histórica.
            prior = PaymentTransaction.objects.filter(intent__ref=intent_ref, type="refund").count()
            gateway_id = f"cash-refund:{order.ref}:{intent_ref}" + (f":{prior + 1}" if prior else "")
            PaymentService.refund(
                intent_ref,
                amount_q=balance_q,
                reason=_PAYMAN_REFUND_REASONS.get(refund_reason(order), "order_cancelled"),
                gateway_id=gateway_id,
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
        order.emit_event(
            event_type="cash_refund_recorded",
            actor=actor.get_username() if hasattr(actor, "get_username") else str(actor),
            payload={
                "amount_q": refunded_q,
                "reason": refund_reason(order),
                "approved_by": approved_by.get_username() if hasattr(approved_by, "get_username") else "",
                "shift_id": shift.pk,
            },
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
        adapter = _adapter_for_persisted_intent(intent_ref, method=method)
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
        if adapter is not None:
            _notify_refund(
                order,
                method=method,
                amount_q=int(getattr(result, "amount_q", None) or requested_q or 0),
                idempotency_key=idempotency_key,
            )
        return int(requested_q or 0)

    # Falha TERMINAL (recusa do gateway): retry não ajuda → alerta já.
    detail = getattr(result, "message", None) or getattr(result, "error_code", None) or "ver logs"
    logger.error("payment.refund: adapter recusou o estorno do pedido %s: %s", order.ref, detail)
    alert_refund_failed(order, intent_ref, requested_q, detail)
    return 0


def _notify_refund(order, *, method: str, amount_q: int, idempotency_key: str) -> None:
    """Avisa o cliente de que o GATEWAY devolveu o dinheiro (``payment_refunded``).

    Só o estorno que o sistema fez de fato: o sem gateway (maquininha, cobrança
    externa, Pix atestado no balcão) é devolvido por gente, e avisar daqui seria
    afirmar que o dinheiro voltou sem ter voltado. Um aviso por estorno: a chave de
    idempotência do estorno é a ocorrência do aviso, então o retry do mesmo estorno
    não manda dois, e duas devoluções parciais mandam dois, cada um com o seu valor.
    Falha no aviso não desfaz o estorno (o dinheiro já saiu).
    """
    from shopman.shop.services import notification

    try:
        notification.send(
            order,
            "payment_refunded",
            occurrence=idempotency_key,
            refund_amount_q=amount_q,
            refund_method=method,
            status_note=notification.refund_arrival_note(method),
        )
    except Exception:
        logger.warning("payment.refund: aviso do estorno não enfileirado order=%s", order.ref, exc_info=True)


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
        amount_display = f"R$ {format_money(amount_q)}" if amount_q is not None else "valor a apurar"
    except Exception:
        logger.debug("alert_refund_failed: money format failed for amount_q=%s", amount_q, exc_info=True)
        amount_display = "valor a apurar"

    create_operator_alert(
        type="payment_refund_failed",
        severity="critical",
        message=(
            f"O estorno do pedido {order.ref} ({amount_display}) não saiu: {detail}. O dinheiro "
            "do cliente pode estar retido. O suporte recebeu este aviso por e-mail e resolve no "
            "Pix ou no cartão; se o cliente perguntar, diga que o estorno está sendo feito. "
            f"Referência do pagamento: {intent_ref}."
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
    adapter = _adapter_for_persisted_intent(intent_ref, method=method)
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


def cancel_stale_intents(
    order, *, keep_intent_ref: str, reason: str = "superseded_by_captured_payment",
) -> int:
    """Cancel same-order pending/authorized intents once one intent wins.

    A stale Pix QR remains payable at its provider. For Efí/mock intents the
    provider-origin adapter must therefore cancel first; only a successful
    provider result authorizes the local Payman transition. Other methods keep
    the established local cleanup behavior.
    """
    if not keep_intent_ref and reason == "superseded_by_captured_payment":
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
                if str(intent.method or "").lower() == "pix" and str(intent.gateway or "").lower() in {
                    "efi",
                    "mock",
                }:
                    adapter = _adapter_for_persisted_intent(intent.ref, method="pix")
                    if adapter is None or not hasattr(adapter, "cancel"):
                        _alert_stale_intent_cancel_failed(
                            order,
                            intent_ref=intent.ref,
                            gateway=str(intent.gateway or ""),
                            error="Adapter de origem indisponível.",
                        )
                        continue
                    result = adapter.cancel(intent.ref, reason=reason)
                    if not getattr(result, "success", False):
                        _alert_stale_intent_cancel_failed(
                            order,
                            intent_ref=intent.ref,
                            gateway=str(intent.gateway or ""),
                            error=(
                                getattr(result, "message", "")
                                or getattr(result, "error_code", "")
                                or "Cancelamento recusado pelo gateway."
                            ),
                        )
                        continue
                    # Adapters can own the Payman write (Efí/mock do). Re-read
                    # and complete it only after provider success so a remote
                    # failure can never be disguised as cancelled locally.
                    refreshed = PaymentService.get(intent.ref)
                    if refreshed.status not in {"cancelled", "failed"}:
                        PaymentService.cancel(
                            intent.ref,
                            reason=reason,
                        )
                    count += 1
                    continue
                PaymentService.cancel(intent.ref, reason=reason)
                count += 1
            except Exception as exc:
                logger.warning(
                    "payment.cancel_stale_intent_failed order=%s intent=%s",
                    order.ref,
                    intent.ref,
                    exc_info=True,
                )
                if str(intent.method or "").lower() == "pix":
                    _alert_stale_intent_cancel_failed(
                        order,
                        intent_ref=intent.ref,
                        gateway=str(intent.gateway or ""),
                        error=str(exc),
                    )
        return count
    # O laço interno já gritava por intent; o `except` de fora ficou mudo — e é
    # ele que pega a falha que impede o laço INTEIRO de rodar. Sem esta faxina,
    # todo QR antigo do pedido continua pagável depois de um já ter sido pago:
    # o cliente paga duas vezes e a loja descobre pela reclamação.
    except Exception:
        logger.warning("payment.cancel_stale_intents_failed order=%s", order.ref, exc_info=True)
        return 0


def _alert_stale_intent_cancel_failed(order, *, intent_ref: str, gateway: str, error: str) -> None:
    """Make an old, still-payable Pix visible without claiming it was cancelled."""
    logger.error(
        "payment.stale_pix_cancel_failed order=%s intent=%s gateway=%s error=%s",
        order.ref,
        intent_ref,
        gateway or "-",
        error,
    )
    try:
        from shopman.shop.services.observability import create_operator_alert

        create_operator_alert(
            type="payment_reconciliation_failed",
            severity="critical",
            message=(
                f"A cobrança Pix antiga {intent_ref} do pedido {order.ref} continua potencialmente "
                f"pagável no gateway {gateway or 'desconhecido'}. O cancelamento remoto falhou; "
                "não foi feita baixa local. Concilie antes de reenviar uma cobrança."
            ),
            order_ref=order.ref,
            dedupe_key=f"stale-pix-cancel:{intent_ref}",
            intent_ref=intent_ref,
            gateway=gateway,
            error=str(error)[:200],
        )
    except Exception:
        logger.warning(
            "payment.stale_pix_cancel_alert_failed order=%s intent=%s",
            order.ref,
            intent_ref,
            exc_info=True,
        )


def read_payments_for(orders):
    """Batch observation for projections only; no model attributes or shared cache.

    Lê o intent do pedido E os intents de cada tender: venda mista do terminal
    liquida um intent por método e só grava ``payment.intent_ref`` quando há um
    método só (``settle_terminal_tenders``). Quem soma o que entrou precisa dos
    dois (:func:`captured_balance_q` com ``payment_reads``).
    """
    from shopman.payman import PaymentService

    refs: set[str] = set()
    for order in orders:
        refs.update(order_intent_refs(order))
    try:
        return PaymentService.read_many(ref for ref in refs if ref)
    except Exception:
        logger.warning("payment.batch_read_failed", exc_info=True)
        return {}  # Every referenced intent becomes unknown, never embedded paid.


def order_intent_refs(order) -> list[str]:
    """Os intents do pedido, sem repetição: o do pedido e os de cada tender."""
    payment_data = (order.data or {}).get("payment") or {}
    refs: list[str] = []
    for ref in [payment_data.get("intent_ref"), *(
        tender.get("intent_ref") for tender in payment_data.get("tenders") or [] if isinstance(tender, dict)
    )]:
        ref = str(ref or "").strip()
        if ref and ref not in refs:
            refs.append(ref)
    return refs


def get_payment_status(order, *, payment_reads=None) -> str | None:
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
    if payment_reads is not None:
        observed = payment_reads.get(intent_ref)
        return observed.status if observed is not None else "unknown"
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


def lock_order_payment(order) -> None:
    """Hold the payment rows used by a local Order guard until its caller commits.

    Call only after locking Order in an existing atomic block. No provider I/O.
    Payman capture/refund/cancel use these same intent locks.
    """
    from django.db.models import Q
    from shopman.payman.models import PaymentIntent

    intent_ref = str(((order.data or {}).get("payment") or {}).get("intent_ref") or "")
    list(PaymentIntent.objects.select_for_update().filter(Q(order_ref=order.ref) | Q(ref=intent_ref)).order_by("pk"))


def captured_balance_q(order, *, payment_reads=None) -> int | None:
    """O que entrou e continua na casa, somando TODOS os intents do pedido.

    Capturado menos devolvido e contestado, em cada intent do pedido E de cada
    tender: a venda mista do terminal liquida um intent por método e só grava
    ``payment.intent_ref`` quando há um método só, então ler apenas aquele
    intent dizia "zero pago" para uma venda mista paga.

    - ``payment_reads`` (de :func:`read_payments_for`) serve a leitura em lote,
      sem consulta por pedido; sem ele, cada intent é lido no Payman.
    - ``None`` quando algum intent não pôde ser lido — "não sei" nunca vira
      "zero", porque zero pago num pedido pago faria o balcão cobrar de novo.
    - Pedido sem intent nenhum devolve ``0``: nada foi recebido pelo Payman.
    """
    total = 0
    for ref in order_intent_refs(order):
        if payment_reads is not None:
            observed = payment_reads.get(ref)
            balance_q = (
                int(observed.captured_q) - int(observed.refunded_q) - int(observed.chargeback_q)
                if observed is not None else None
            )
        else:
            balance_q = _payman_captured_balance_q(ref)
        if balance_q is None:
            return None
        total += balance_q
    return total


def on_account_q(order) -> int:
    """Quanto do pedido foi para a CONTA DA CASA (tender ``account``).

    É obrigação do cliente já reconhecida: não é dinheiro recebido, e também não
    é saldo a cobrar no balcão — cobrá-lo de novo seria cobrar duas vezes.
    """
    from shopman.shop.services import order_composition

    payment_data = (order.data or {}).get("payment") or {}
    tenders = [t for t in payment_data.get("tenders") or [] if isinstance(t, dict)]
    if tenders:
        return sum(int(t.get("amount_q") or 0) for t in tenders if t.get("method") == "account")
    return order_composition.effective_total_q(order) if payment_data.get("method") == "account" else 0


def balance_due_q(order, *, payment_reads=None) -> int | None:
    """O que falta receber: total EFETIVO menos o que entrou e o que foi para a conta.

    O total é o de :func:`order_composition.effective_total_q` (o pedido ajustado
    vale pelo total novo, não pelo selado). Nunca negativo — pagamento a mais não
    vira saldo. ``None`` quando o Payman não respondeu por algum intent.

    **iFood** é a exceção: a prova é o payload do iFood (``payments``), não o
    Payman — a casa não cobra o pedido do marketplace. Pré-pago é saldo zero;
    pendente é o ``pending_q`` que ainda se cobra na porta; sem evidência, ``None``.
    """
    from shopman.shop.services import order_composition

    if order.channel_ref == "ifood":
        return _ifood_balance_due_q(order, order_composition.effective_total_q(order))

    captured = captured_balance_q(order, payment_reads=payment_reads)
    if captured is None:
        return None
    return max(0, order_composition.effective_total_q(order) - captured - on_account_q(order))


def _ifood_balance_due_q(order, total_q: int) -> int | None:
    from shopman.shop.services.ifood_ingest import payment_status_from_payload

    payments = ((order.data or {}).get("ifood") or {}).get("payments") or {}
    # O total EFETIVO, não o selado: o pedido que o cliente alterou no iFood é
    # pago pelo total novo (``ifood.payments`` é relido no ORDER_PATCHED).
    status = payment_status_from_payload(payments, int(total_q or 0))
    if status == "paid":
        return 0
    if status == "pending":
        pending_q = int(payments.get("pending_q") or 0)
        return max(0, min(total_q, pending_q) if pending_q > 0 else total_q)
    return None


def has_sufficient_captured_payment(order, *, payment_reads=None) -> bool:
    """O Payman mostra dinheiro capturado cobrindo o total EFETIVO do pedido?

    Soma todos os intents do pedido (:func:`captured_balance_q`) e compara com
    :func:`order_composition.effective_total_q` — o pedido ajustado (iFood
    alterado depois de confirmado) vale pelo total novo, não pelo selado. Quando
    o pedido tem ``payment.intent_ref``, o estado daquele intent ainda precisa
    ser de dinheiro capturado (ou devolvido em parte).
    """
    from shopman.shop.services import order_composition

    payment_data = (order.data or {}).get("payment") or {}
    if not order_intent_refs(order):
        # Pedido importado/antigo, sem intent no Payman: vale o estado gravado.
        return (_embedded_payment_status(payment_data) or "") in _PAID_STATUSES

    if payment_data.get("intent_ref"):
        status = (get_payment_status(order, payment_reads=payment_reads) or "").lower()
        if status not in _PAID_STATUSES | {"refunded"}:
            return False

    balance_q = captured_balance_q(order, payment_reads=payment_reads)
    if balance_q is None:
        return False
    return balance_q >= order_composition.effective_total_q(order)


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


def _record_gateway_authorization(order, *, intent_ref: str) -> str:
    """Grava no Payman a autorização que o gateway confirma. Retorna o estado.

    Devolve ``"authorized"`` (nem pago nem não-pago): para o timeout isso é
    "não cancele", e para o acompanhamento é "mostre o degrau de autorizado".
    """
    from shopman.payman import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
    except PaymentError:
        return "indeterminate"

    if str(intent.status or "").lower() == "authorized":
        return "authorized"

    try:
        PaymentService.authorize(intent_ref, gateway_id=intent.gateway_id or intent_ref)
    except PaymentError as exc:
        logger.warning(
            "payment.gateway_authorize_rejected order=%s intent=%s code=%s",
            order.ref,
            intent_ref,
            getattr(exc, "code", ""),
        )
        return "indeterminate"

    order.emit_event(
        event_type="payment.authorized",
        actor="payment.gateway_reconcile",
        payload={"intent_ref": intent_ref},
    )
    logger.info("payment.gateway_authorization_recovered order=%s intent=%s", order.ref, intent_ref)

    # Pedido já aceito com autorização recém-descoberta: quem captura é a mesma
    # regra do lifecycle (``_on_accepted``), que aqui já passou e não voltará.
    from shopman.orderman.models import Order

    if order.status == Order.Status.ACCEPTED:
        capture(order)
        order.refresh_from_db()
        if has_sufficient_captured_payment(order) is True:
            from shopman.shop.lifecycle import dispatch

            dispatch(order, "on_paid")
            return "paid"
    if order.status == Order.Status.NEW:
        # O webhook perdido também não pode deixar a autorização sem vigia.
        from shopman.shop.services import card_authorization

        card_authorization.watch(order)
    return "authorized"


def settle_from_gateway(order) -> str:
    """Pergunta ao gateway se este pedido já foi pago e, se foi, liquida.

    É a rede contra webhook perdido, e serve dois chamadores com necessidades
    opostas: o timeout, que precisa saber se pode cancelar, e o acompanhamento,
    que precisa mostrar a verdade quando o cliente volta do gateway. Os dois
    fazem a mesma pergunta e querem a mesma escrita, então há uma implementação
    só. Retorna:

      ``"paid"``          — gateway mostra captura; o Payman foi reconciliado
                            e o caminho de pago (on_paid) foi disparado;
      ``"authorized"``    — cartão em ``requires_capture``: dinheiro reservado,
                            autorização gravada no Payman, captura é do
                            lifecycle. NÃO cancelar;
      ``"unpaid"``        — gateway respondeu e não há pagamento (cancelar ok);
      ``"indeterminate"`` — sem resposta confiável (NÃO cancelar nesta rodada).

    ⚠️ **Vale para PIX e para CARTÃO.** Enquanto a primeira linha era
    ``if method != "pix": return "unpaid"``, um pedido de cartão pago no Stripe
    era declarado "não pago" sem que ninguém perguntasse a ninguém — o guard que
    existe para não cancelar pedido pago autorizava justamente isso. A porta
    verdadeira nunca foi o método: é o adapter ter ``check_gateway_status``, e
    agora os três (efí, stripe, mock) têm.
    """
    payment_data = (order.data or {}).get("payment") or {}
    method = str(payment_data.get("method") or "").lower()
    intent_ref = payment_data.get("intent_ref")
    # Só o que passou por GATEWAY volta dele. Crédito e débito do balcão não têm
    # webhook para conciliar: a maquininha é física e a prova é o papel dela.
    if method not in _GATEWAY_METHODS or not intent_ref:
        return "unpaid"

    adapter = _adapter_for_persisted_intent(intent_ref, method=method)
    if adapter is None:
        # An intent exists but its persisted provider route cannot be loaded.
        # That is uncertainty, never evidence that the customer did not pay.
        return "indeterminate"

    # ── A pergunta é de LEITURA, e a resposta não pode ter efeito colateral ──
    #
    # Aqui se perguntava com ``adapter.capture()``, e capture é verbo de escrita.
    # No adapter da Efí ele é "confere no gateway e, se CONCLUIDA, reconcilia" —
    # inofensivo. No ``payment_mock`` ele captura INCONDICIONALMENTE e devolve
    # sucesso. Com o mock configurado (que é o caso do staging), todo PIX que
    # vencia sem ninguém pagar era promovido a "pago" aqui: estoque baixado,
    # cozinha acionada, cliente avisado. E o gatilho não era nem o worker: era o
    # próprio cliente recarregando o acompanhamento, que chamava
    # ``resolve_timeouts_if_due`` a cada GET (hoje o GET só lê).
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

    if gateway_state == "authorized":
        # Cartão em ``requires_capture``: o cliente fez a parte dele e o dinheiro
        # está reservado para a loja, mas ainda NÃO entrou. Aqui só se registra a
        # autorização — capturar é decisão do lifecycle (``_on_accepted``), que
        # cobra quando a loja aceita. Reconciliar não pode virar atalho para
        # cobrar antes do aceite: é exatamente a linha que o caso do pedido E54
        # ensinou a não cruzar.
        #
        # Registrar já muda tudo o que o cliente lê: sem isto o Payman segue em
        # ``pending``, o degrau da cascata continua sendo "Pagar com cartão", e
        # quem acabou de pagar no Stripe volta para uma tela que pede pagamento.
        return _record_gateway_authorization(order, intent_ref=intent_ref)
    if gateway_state != "captured":
        # "pending"/"cancelled": o gateway respondeu e não há pagamento.
        # "not_found": o intent nunca existiu, então também não há pagamento —
        # e isto NÃO é incerteza, senão a directive de timeout tenta para sempre
        # um pedido que nunca teve cobrança.
        # Qualquer outra coisa ("error", status novo do provedor) é estado
        # incerto, e incerto espera.
        return "unpaid" if gateway_state in {"pending", "cancelled", "not_found"} else "indeterminate"

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

    card_funding = None
    if already_captured_q > 0:
        transaction_id = ""
        captured_amount_q = already_captured_q
    else:
        try:
            result = adapter.capture(intent_ref)
        except Exception:
            logger.warning("payment.timeout_gateway_capture_failed order=%s", order.ref, exc_info=True)
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
        card_funding = result.card_funding if isinstance(getattr(result, "card_funding", None), str) else None

    # Read classification from the durable Payman intent after reconciliation.
    # A gateway status/result is not allowed to declare its own financial mode.
    from shopman.shop.services.payment_provenance import confirmation_provenance

    provenance = confirmation_provenance(_payman_intent(intent_ref))

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
        if card_funding:
            locked_payment["card_funding"] = card_funding
        locked_payment.update(provenance)
        locked_data = dict(locked.data or {})
        locked_data["payment"] = locked_payment
        locked.data = locked_data
        locked.save(update_fields=["data", "updated_at"])

    order.refresh_from_db()
    cancel_stale_intents(order, keep_intent_ref=intent_ref)
    order.emit_event(
        event_type="payment.captured",
        actor="payment.timeout_gateway_check",
        payload={"method": method, "amount_q": captured_amount_q or order.total_q},
    )

    from shopman.shop.lifecycle import dispatch

    dispatch(order, "on_paid")
    return "paid"


# Intervalo mínimo entre duas perguntas ao gateway pelo MESMO pedido. Existe para
# o acompanhamento poder pedir a conferência (POST ``payment/check/``) a cada volta
# à aba sem transformar cada uma numa chamada de rede ao provedor. Curto de propósito: quem volta do
# checkout do Stripe tem que ver a verdade no primeiro carregamento, e a última
# pergunta desse pedido foi lá atrás, na criação do intent.
GATEWAY_RECHECK_SECONDS = 20


def _gateway_recheck_is_due(order) -> bool:
    payment = (order.data or {}).get("payment") or {}
    raw = payment.get("gateway_checked_at")
    if not raw:
        return True
    checked_at = parse_datetime(str(raw))
    if checked_at is None:
        return True
    if timezone.is_naive(checked_at):
        checked_at = timezone.make_aware(checked_at, timezone.get_current_timezone())
    return (timezone.now() - checked_at).total_seconds() >= GATEWAY_RECHECK_SECONDS


def _stamp_gateway_check(order) -> None:
    """Carimba a hora da pergunta, para o throttle. Best-effort por desenho.

    Falhar aqui não pode impedir a liquidação: o pior que acontece sem o carimbo
    é perguntar de novo cedo demais.
    """
    try:
        from shopman.shop.services.order_helpers import merge_order_data

        merge_order_data(order, {"gateway_checked_at": timezone.now().isoformat()}, block="payment")
    # O carimbo é só o throttle da pergunta ao gateway, e a liquidação não pode
    # parar por causa dele.
    # silêncio-deliberado: sem o carimbo, o pior que acontece é perguntar cedo demais.
    except Exception:
        logger.debug("payment.gateway_check_stamp degraded", exc_info=True)


def reconcile_with_gateway_if_due(order) -> bool:
    """Volta do gateway: perguntar se pagou, e liquidar se pagou. Retorna se mudou.

    ⚠️ **Isto é o que faltava para a volta do Stripe fazer sentido.** O
    ``success_url`` devolve o cliente para o acompanhamento, e o acompanhamento
    lia só o Payman — que só sabe o que o webhook contou. Webhook atrasado é
    corrida (o cliente chega antes); webhook quebrado é dano permanente
    (endpoint errado no painel, segredo de outro ambiente, 400 na assinatura).
    Nos dois casos o cliente pagava e continuava lendo "Pagar com cartão".

    A conferência do acompanhamento (o POST ``orders/<ref>/payment/check/``, que
    a tela pede ao abrir) e o ``reconcile_payments`` do worker fecham esse
    buraco: pedido de cartão aberto e não capturado pergunta ao gateway, no máximo a cada
    ``GATEWAY_RECHECK_SECONDS``. Não substitui o webhook (que é quem responde
    rápido e sem cliente na tela) — é o piso por baixo dele.

    **Só cartão, de propósito.** O PIX já tem rede: o cliente não sai do site, o
    webhook empurra por SSE, e no vencimento ``settle_from_gateway`` pergunta à
    Efí antes de cancelar. Estender a pergunta preguiçosa ao PIX poria uma
    chamada à Efí a cada 20s enquanto alguém encara o QR code, para cobrir um
    caso que já está coberto. O cartão é que não tinha rede nenhuma: o cliente
    SAI do site, e ao voltar não há sinal nenhum além desta conferência.
    """
    from shopman.orderman.models import Order

    payment = (order.data or {}).get("payment") or {}
    method = str(payment.get("method") or "").lower()
    if method not in HOSTED_CHECKOUT_METHODS or not payment.get("intent_ref"):
        return False
    if order.status not in {Order.Status.NEW, Order.Status.ACCEPTED}:
        return False
    if has_sufficient_captured_payment(order) is True:
        return False
    if not _gateway_recheck_is_due(order):
        return False

    _stamp_gateway_check(order)
    try:
        state = settle_from_gateway(order)
    except Exception:
        logger.warning("payment.gateway_reconcile_failed order=%s", order.ref, exc_info=True)
        return False
    if state in {"paid", "authorized"}:
        order.refresh_from_db()
        return True
    return False


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

    Por isso, com ``method``, a resposta exige também que o adapter EFETIVO
    daquele método seja o simulado. ``get_adapter`` inclui a precedência de
    ``Shop.integrations`` sobre settings; ler só a env aqui poderia expor o botão
    sobre uma intent Efí quando o banco sobrescrevesse a configuração do deploy.
    """
    from django.conf import settings

    if not (settings.DEBUG or getattr(settings, "SHOPMAN_EXPOSE_MOCK_CAPTURE", False)):
        return False
    if method is None:
        return True
    adapter = get_adapter("payment", method=str(method).lower())
    return _gateway_for_adapter(adapter) == "mock"


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
        # Só o Pix chega aqui (ver `_persist_intent`), e para o Pix este JSON é
        # o QR. Voltar `{}` calado deixa o cliente na tela de pagamento sem
        # código para copiar e sem imagem para ler — a cobrança existe no
        # gateway e não há como pagá-la.
        try:
            return json.loads(intent.client_secret)
        except (json.JSONDecodeError, TypeError):
            logger.warning("payment.qr_data_unreadable intent=%s", intent.intent_ref, exc_info=True)

    return {}


class PaymentAttemptLookupUnavailable(Exception):
    """As tentativas anteriores de pagamento do pedido não puderam ser lidas."""


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
    except Exception as exc:
        logger.warning("payment.generation_lookup_failed order=%s", order.ref, exc_info=True)
        # Devolver 0 aqui recalculava a chave da PRIMEIRA tentativa, que pode ser
        # justamente a que morreu: a mesma chave envenenada do item 17.
        raise PaymentAttemptLookupUnavailable(order.ref) from exc


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
    except Exception as exc:
        logger.warning("payment.idempotency_key_lookup_failed order=%s", order.ref, exc_info=True)
        # Isto devolvia True ("reusa a chave guardada") quando a busca falhava.
        # Se o intent daquela chave foi uma falha terminal, o retry reusava a
        # chave envenenada e o gateway repetia a falha guardada. Sem a busca, não
        # há como decidir: quem chama recusa a tentativa em vez de chutar.
        raise PaymentAttemptLookupUnavailable(order.ref) from exc

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


def _payman_intent(intent_ref: str):
    try:
        from shopman.payman import PaymentService

        return PaymentService.get(intent_ref)
    except Exception:
        logger.warning("payment.intent_route_lookup_failed intent=%s", intent_ref, exc_info=True)
        return None


def _gateway_for_adapter(adapter) -> str | None:
    raw_declared = getattr(adapter, "PAYMENT_GATEWAY", "")
    declared = raw_declared.strip().lower() if isinstance(raw_declared, str) else ""
    if declared:
        return declared
    path = str(getattr(adapter, "__name__", "") or "")
    for gateway, adapter_path in _PAYMENT_GATEWAY_ADAPTER_PATHS.items():
        if path == adapter_path:
            return gateway
    return None


def _pix_intent_needs_creation_resume(intent, *, expected_gateway: str | None) -> bool:
    """True only for an Efí Pix attempt whose payable artifact is incomplete.

    The adapter persists the intent, txid and Efí location before fetching the
    QR. A failed GET must therefore re-enter that adapter with the original
    idempotency key; merely attaching the pending row to the order strands a
    live charge with no way for the customer to pay it.
    """
    if intent is None or expected_gateway != "efi":
        return False
    if str(getattr(intent, "method", "") or "").lower() != "pix":
        return False
    if str(getattr(intent, "gateway", "") or "").lower() != "efi":
        return False
    if str(getattr(intent, "status", "") or "").lower() != "pending":
        return False
    return not bool((getattr(intent, "gateway_data", None) or {}).get("client_secret"))


def _adapter_for_persisted_intent(intent_ref: str, *, method: str):
    """Route money operations by the intent's persisted gateway.

    A missing Payman row or unknown gateway is an uncertain money state, not
    permission to send an orphan reference to whichever provider happens to be
    configured today.  The persisted route always wins across flips/rollbacks.
    """
    # Persisted-provider routing is a Pix migration safety rule. Stripe/link
    # and custom methods keep their established registry semantics; forcing
    # them through the small Pix gateway map would disable valid adapters.
    if str(method or "").strip().lower() != "pix":
        return get_adapter("payment", method=method)

    intent = _payman_intent(intent_ref)
    if intent is None:
        return None
    gateway = str(intent.gateway or "").strip().lower()
    if not gateway:
        # A late Pix received on an already-dead charge is booked as a new local
        # intent (the old unique ``gateway/gateway_id`` pair is occupied), but
        # refund still belongs to the provider of the persisted superseded
        # charge.  Follow that explicit ledger link; never infer from settings.
        gateway_data = intent.gateway_data or {}
        superseded_ref = str(gateway_data.get("superseded_intent_ref") or "")
        if (
            gateway_data.get("booked_by") == "pix_confirmation"
            and superseded_ref
            and superseded_ref != intent_ref
        ):
            return _adapter_for_persisted_intent(superseded_ref, method=method)
        return None
    if gateway == "efi" and not _efi_intent_environment_matches_runtime(intent):
        return None
    configured = get_adapter("payment", method=method)
    if _gateway_for_adapter(configured) == gateway:
        return configured
    adapter_path = _PAYMENT_GATEWAY_ADAPTER_PATHS.get(gateway)
    if not adapter_path:
        logger.error(
            "payment.intent_gateway_unknown intent=%s gateway=%s method=%s",
            intent_ref,
            gateway,
            method,
        )
        return None
    return import_module(adapter_path)


def _efi_intent_environment_matches_runtime(intent) -> bool:
    from django.conf import settings

    persisted = str((intent.gateway_data or {}).get("provider_environment") or "").strip().lower()
    current = "sandbox" if (getattr(settings, "SHOPMAN_EFI", {}) or {}).get("sandbox", True) else "production"
    if persisted == current:
        return True

    # An unmarked legacy Efí intent is not evidence that today's credentials
    # point at its origin. Financial verbs must wait for manual reconciliation
    # instead of guessing an environment and potentially touching another Cob.
    persisted_label = persisted or "desconhecido"

    logger.error(
        "payment.efi_environment_mismatch intent=%s order=%s persisted=%s current=%s",
        intent.ref,
        intent.order_ref,
        persisted_label,
        current,
    )
    try:
        from shopman.shop.services.observability import create_operator_alert

        create_operator_alert(
            type="payment_reconciliation_failed",
            severity="critical",
            message=(
                f"A cobrança Pix {intent.ref} do pedido {intent.order_ref} pertence ao ambiente Efí "
                f"{persisted_label}, mas a aplicação está em {current}. Nenhuma operação foi enviada; "
                "concilie no ambiente de origem."
            ),
            order_ref=intent.order_ref,
            dedupe_key=f"efi-environment-mismatch:{intent.ref}:{persisted_label}:{current}",
            intent_ref=intent.ref,
            persisted_environment=persisted_label,
            current_environment=current,
        )
    except Exception:
        logger.warning(
            "payment.efi_environment_mismatch_alert_failed intent=%s",
            intent.ref,
            exc_info=True,
        )
    return False


def _existing_active_intent(
    order,
    *,
    method: str,
    amount_q: int,
    gateway: str | None = None,
) -> PaymentIntent | None:
    """Return a reusable intent without crossing provider routes.

    A captured intent is a payment fact and remains reusable across a config
    change.  Pending/authorized intents are reusable only on the gateway that
    will receive the next operation.
    """
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
            if gateway is not None and intent.gateway != gateway:
                continue
            if intent.expires_at and intent.expires_at <= now:
                continue
            return _payment_intent_from_payman(intent)
    # Não é degradação barata: quem chama usa este retorno para decidir entre
    # REAPROVEITAR a cobrança viva do pedido ou abrir uma nova. Vazio por falha
    # de leitura vira segunda cobrança do mesmo pedido — e o cliente com dois
    # QR na mão pode pagar os dois. Em `logger.debug` isso não saía do processo.
    except Exception:
        logger.warning("payment.existing_intent_lookup_failed order=%s", order.ref, exc_info=True)
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
    from django.db import transaction
    from shopman.orderman.models import Order

    error_message = str(error or "Falha ao gerar pagamento.")[:200]

    def persist_into(target) -> bool:
        data = dict(target.data or {})
        current_payment = dict(data.get("payment") or {})
        intent_ref = str(current_payment.get("intent_ref") or payment_data.get("intent_ref") or "")
        try:
            paid_amount_q = int(current_payment.get("paid_amount_q") or 0)
        except (TypeError, ValueError):
            paid_amount_q = 0
        receipt_proves_payment = bool(current_payment.get("captured_at")) or (
            paid_amount_q >= int(amount_q or 0) > 0
        )
        if receipt_proves_payment or (intent_ref and _payman_intent_captured(intent_ref)):
            # Webhook won the race. An adapter exception from the older create
            # snapshot is no longer a payment failure. The Order receipt is
            # sufficient even in the narrow window before Payman capture.
            current_payment.pop("error", None)
            data["payment"] = current_payment
            target.data = data
            target.save(update_fields=["data", "updated_at"])
            return False
        data["payment"] = {
            **payment_data,
            **current_payment,
            "method": method,
            "amount_q": amount_q,
            "error": error_message,
        }
        target.data = data
        target.save(update_fields=["data", "updated_at"])
        return True

    if isinstance(order, Order) and getattr(order, "pk", None) is not None:
        with transaction.atomic():
            locked = Order.objects.select_for_update().get(pk=order.pk)
            recorded = persist_into(locked)
            order.data = locked.data
    else:
        recorded = persist_into(order)
    if not recorded:
        _ack_payment_failed_alerts(order)
        return
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

        # Os dois irmãos acima (`_create_payment_failed_alert`,
        # `_notify_payment_failed`) já gritavam. Resolver pelo serviço auditado
        # evita o operador perseguir um pagamento que já entrou.
        alert_adapter.resolve(
            "payment_failed",
            order_ref=order.ref,
            actor="system:payment",
        )
    except Exception:
        logger.warning("payment_failed_alert_ack_failed order=%s", order.ref, exc_info=True)


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
    from shopman.shop.config import ChannelConfig

    cfg = ChannelConfig.for_channel(order.channel_ref)

    config: dict = {}
    if method == "pix":
        config["pix_timeout_minutes"] = cfg.payment.timeout_minutes
        if _is_pos_remote_order(order):
            # Pix de ENCOMENDA anotada no PDV: o cliente paga depois, de casa, e
            # o pedido pode ser para a semana que vem. O prazo do Pix de balcão
            # (minutos, cliente na frente do caixa) cancelava a encomenda antes
            # de ele abrir o celular. A cobrança remota da encomenda já tem prazo
            # decidido, o do LINK: ``min(agora + janela do canal, corte do
            # atendimento)``. O Pix segue o mesmo relógio (P2-26).
            config["pix_timeout_minutes"] = _link_deadline_minutes(order, cfg)
        # Constraint: o botão "Simular pagamento" (SHOPMAN_EXPOSE_MOCK_CAPTURE)
        # e o auto-confirm se contradizem — o timer de segundos sempre ganha a
        # corrida do dedo e anula a afordância manual em silêncio. Com o botão
        # exposto, quem confirma o Pix mock é a pessoa, nunca o relógio.
        if getattr(settings, "SHOPMAN_MOCK_PIX_AUTO_CONFIRM", False) and not getattr(
            settings, "SHOPMAN_EXPOSE_MOCK_CAPTURE", False
        ):
            config["mock_pix_auto_confirm"] = True
            config["mock_pix_confirm_delay_seconds"] = getattr(
                settings,
                "SHOPMAN_MOCK_PIX_CONFIRM_DELAY_SECONDS",
                10,
            )
    if method == "link":
        # ⚠️ O LINK CAPTURA SOZINHO, sempre. Não é botão de env: é a natureza da
        # forma. A venda do balcão já fechou quando a URL nasce — não existe um
        # "aceite" posterior da loja para justificar segurar a autorização, que
        # é o que o `manual` do cartão da loja online compra. Enquanto o link
        # herdava o `capture_method` do bloco `SHOPMAN_STRIPE` (`manual` por
        # padrão), o cliente pagava, o intent ficava `authorized`, a autorização
        # vencia no Stripe em ~7 dias e a padaria NUNCA recebia.
        config["capture_method"] = "automatic"
        # O prazo do link segue o CICLO DO ATENDIMENTO, não uma env: a janela é
        # do canal (`payment.link_timeout_minutes`) e o corte é o que a casa já
        # sabe do pedido — o início da janela combinada ou o fechamento da loja
        # no dia do compromisso. O adapter recebe os dois prontos e faz
        # `min(agora + janela, corte)` preso à régua do Stripe; ele não precisa
        # conhecer pedido nem calendário (`adapters/_payment_link`).
        config["link_timeout_minutes"] = cfg.payment.link_timeout_minutes
        cutoff = payment_deadline.service_cutoff(order)
        if cutoff is not None:
            config["link_expires_by"] = cutoff.isoformat()
    elif method in HOSTED_CHECKOUT_METHODS:
        # Cartão da loja online: a captura é decisão do lifecycle (`_on_accepted`
        # cobra quando a loja aceita), e o `manual` é o que permite recusar o
        # pedido sem ter cobrado.
        stripe_config = getattr(settings, "SHOPMAN_STRIPE", {}) or {}
        capture_method = str(stripe_config.get("capture_method") or "manual").strip().lower()
        config["capture_method"] = capture_method if capture_method in {"automatic", "manual"} else "manual"
    return config


def _is_pos_remote_order(order) -> bool:
    """Pedido do PDV que o cliente NÃO leva agora: encomenda, entrega, data futura."""
    from shopman.shop.services.order_helpers import is_counter_takeaway

    data = getattr(order, "data", None) or {}
    return data.get("origin_channel") == "pos" and not is_counter_takeaway(order)


def _link_deadline_minutes(order, cfg) -> int:
    """O prazo do link deste pedido, em minutos inteiros contados de agora.

    Arredonda para BAIXO: o Pix nunca vence depois do corte do atendimento.
    """
    from shopman.shop.adapters._payment_link import link_expires_at

    now = timezone.now()
    expires_at = link_expires_at(
        now,
        timeout_minutes=cfg.payment.link_timeout_minutes,
        expires_by=payment_deadline.service_cutoff(order, now=now),
    )
    return max(1, int((expires_at - now).total_seconds() // 60))


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
    """Return captured funds still held, using Payman refund/chargeback books."""
    try:
        from shopman.payman import PaymentService

        return PaymentService.captured_total(intent_ref) - PaymentService.refunded_total(intent_ref) - PaymentService.chargeback_total(intent_ref)
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
