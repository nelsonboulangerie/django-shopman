"""Operator-only FOOD disputes. Contract: official FOOD handshake-platform guide.

HSS records a negotiation outcome; only CAN changes order cancellation state.
Ambiguous delivery never retries a financial decision automatically.
"""
import logging
from copy import deepcopy
from urllib.parse import quote, urlparse
from uuid import uuid4

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from shopman.orderman.models import Order

from shopman.shop.directives import IFOOD_HANDSHAKE_RESPONSE, create_deduped
from shopman.shop.services import ifood_auth

logger = logging.getLogger(__name__)

REJECT_REASONS = (
    "HIGH_STORE_DEMAND", "UNKNOWN_ISSUE", "CUSTOMER_SATISFACTION", "INVENTORY_CHECK",
    "SYSTEM_ISSUE", "WRONG_ORDER", "PRODUCT_QUALITY", "LATE_DELIVERY", "CUSTOMER_REQUEST",
)
SCENARIOS = {
    ("AFTER_DELIVERY", "CANCELLATION"), ("PREPARATION_TIME", "CANCELLATION"),
    ("DELAY", "CANCELLATION"), ("AFTER_DELIVERY_PARTIALLY", "PARTIAL_CANCELLATION"),
}


class HandshakeValidationError(ValueError):
    pass


def _records(order):
    return (order.data or {}).get("ifood", {}).get("handshakes", {})


def _save(order, records):
    data = deepcopy(order.data or {})
    data.setdefault("ifood", {})["handshakes"] = records
    data["ifood"]["handshake_pending"] = any(r.get("state") != "settled" for r in records.values())
    order.data = data
    order.save(update_fields=["data", "updated_at"])


def _extra(raw, key, default=None):
    nested = raw.get("metadata")
    return raw.get(key, nested.get(key, default) if isinstance(nested, dict) else default)


def _expiry(raw):
    try:
        return parse_datetime(str(raw.get("expiresAt") or ""))
    except (ValueError, TypeError):
        return None


def _open(record):
    raw = record.get("raw") or {}
    expires = _expiry(raw)
    return bool(record.get("state") == "open" and expires and timezone.is_aware(expires)
                and expires > timezone.now() and (raw.get("handshakeType"), raw.get("action")) in SCENARIOS)


def _items(raw):
    items = _extra(raw, "items", _extra(raw, "item", [])) or []
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        items = []
    garnish = _extra(raw, "garnishItems", []) or []
    rows = []
    for item in items + (garnish if isinstance(garnish, list) else []):
        if not isinstance(item, dict):
            continue
        label = f"{item.get('quantity', '')} × {item.get('name') or item.get('externalCode') or item.get('id', '')}"
        amount = item.get("amount")
        if isinstance(amount, dict):
            value = str(amount.get("value", ""))
            if value.isascii() and value.isdigit() and len(value) < 15:
                major, minor = divmod(int(value), 100)
                label += f" — {amount.get('currency', '')} {major}.{minor:02d}"
        if item.get("reason"):
            label += f" ({item['reason']})"
        rows.append(label)
    return rows


def _evidence_urls(raw):
    urls = []
    for evidence in (_extra(raw, "evidences", []) or []):
        value = evidence.get("url") if isinstance(evidence, dict) else None
        if isinstance(value, str):
            try:
                parsed = urlparse(value)
                if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
                    urls.append(value)
            except ValueError:  # silêncio-deliberado: URL malformada é excluída do filtro, sem expor seu conteúdo
                pass
    return urls


def _notice(record):
    if record.get("state") == "settled":
        labels = {"ACCEPTED": "Solicitação aceita pelo iFood.", "REJECTED": "Solicitação recusada pelo iFood.", "EXPIRED": "Negociação encerrada por prazo no iFood."}
        outcomes = [item.get("status") for item in record.get("settlements", {}).values() if item.get("status") in labels]
        if outcomes:
            return labels[outcomes[-1]] + " O estado do pedido é atualizado pelos eventos oficiais do pedido."
    if _open(record):
        return ""
    return {
        "queued": "Resposta do operador aguardando envio ao iFood.",
        "sending": "Envio iniciado; aguarde a confirmação do iFood. Não repita a decisão.",
        "sent": "Resposta enviada; aguardando o resultado da negociação no iFood.",
        "awaiting_customer": "Contraproposta registrada; aguardando a decisão final no iFood.",
        "unknown": "Envio sem confirmação. Consulte a negociação no iFood antes de qualquer nova decisão.",
        "settled": "Resultado registrado pelo iFood. O cancelamento do pedido depende do evento de cancelamento.",
        "expired": "Prazo encerrado antes do envio; aguarde o resultado do iFood.",
    }.get(record.get("state"), "Negociação vencida ou cenário não suportado; consulte o iFood.")


def projection(order):
    rows = []
    for dispute_id, record in _records(order).items():
        raw = record.get("raw") or {}
        rows.append({
            "id": dispute_id, "type": raw.get("handshakeType", ""), "action": raw.get("action", ""),
            "message": raw.get("message", ""), "expires_at": raw.get("expiresAt", ""),
            "timeout_action": raw.get("timeoutAction", ""), "state": record.get("state"),
            "items": _items(raw),
            "evidence_urls": _evidence_urls(raw),
            "accept_reasons": _extra(raw, "acceptCancellationReasons", []) or [],
            "reject_reasons": list(REJECT_REASONS), "alternatives": raw.get("alternatives", []),
            "alternatives_available": bool(raw.get("alternatives")),
            "can_respond": _open(record),
            "response_notice": _notice(record),
        })
    return rows


def persist_event(order, event, *, settlement):
    """Caller owns the row lock and commits this with the event replay receipt."""
    raw = event.get("metadata")
    if not isinstance(raw, dict):
        raise HandshakeValidationError("Evento sem metadata.")
    identifier = str(raw.get("id") or (event.get("id") if settlement else "") or "")
    dispute_id = str(raw.get("disputeId") or "") if settlement else identifier
    if not identifier or not dispute_id:
        raise HandshakeValidationError("Evento sem identificação da negociação.")
    records = deepcopy(_records(order))
    record = records.setdefault(dispute_id, {"state": "open", "settlements": {}})
    if settlement:
        if raw.get("status") not in {"ACCEPTED", "REJECTED", "EXPIRED", "ALTERNATIVE_REPLIED"}:
            raise HandshakeValidationError("Resultado de negociação inválido.")
        if identifier in record["settlements"]:
            return False
        record["settlements"][identifier] = deepcopy(raw)
        if raw["status"] != "ALTERNATIVE_REPLIED":
            record["state"] = "settled"
        elif record.get("state") != "settled":
            record["state"] = "awaiting_customer"
    else:
        reasons = _extra(raw, "acceptCancellationReasons", [])
        if not isinstance(reasons, list) or any(not isinstance(reason, str) or not reason for reason in reasons):
            raise HandshakeValidationError("Opções de motivo inválidas.")
        if record.get("raw"):
            if record["raw"] != raw:
                raise HandshakeValidationError("Disputa repetida com conteúdo divergente.")
            return False
        record["raw"] = deepcopy(raw)
    record["last_event_id"] = str(event["id"])
    _save(order, records)
    return True


@transaction.atomic
def enqueue_response(order, *, dispute_id, decision, reason="", detail_reason="", actor, expected_revision=None):
    from shopman.shop.services.operator_orders import operational_revision

    locked = Order.objects.select_for_update().get(pk=order.pk)
    if locked.channel_ref != "ifood" or not actor:
        raise HandshakeValidationError("Operador e pedido iFood são obrigatórios.")
    if expected_revision is not None and operational_revision(locked) != expected_revision:
        raise HandshakeValidationError("Pedido atualizado. Recarregue antes de responder.")
    records = deepcopy(_records(locked))
    record = records.get(dispute_id)
    if not record or not _open(record):
        raise HandshakeValidationError("Negociação encerrada, vencida, não suportada ou já respondida.")
    if decision not in {"accept", "reject"}:
        raise HandshakeValidationError("Escolha aceitar ou rejeitar.")
    if not isinstance(reason, str) or not isinstance(detail_reason, str) or len(detail_reason) > 250:
        raise HandshakeValidationError("Motivo inválido; detalhe limitado a 250 caracteres.")
    allowed = (_extra(record["raw"], "acceptCancellationReasons", []) or []) if decision == "accept" else REJECT_REASONS
    if (allowed and reason not in allowed) or (not allowed and reason):
        raise HandshakeValidationError("Escolha um motivo permitido pelo iFood.")
    if decision == "reject" and detail_reason:
        raise HandshakeValidationError("Detalhamento disponível somente no aceite.")
    body = {"reason": reason} if reason else {}
    if detail_reason:
        body["detailReason"] = detail_reason
    request_id = uuid4().hex
    record.update(state="queued", response={"id": request_id, "decision": decision, "body": body,
                                          "actor": str(actor), "requested_at": timezone.now().isoformat()})
    _save(locked, records)
    create_deduped(IFOOD_HANDSHAKE_RESPONSE, payload={"order_ref": locked.ref, "dispute_id": dispute_id,
                   "request_id": request_id}, dedupe_key=f"{IFOOD_HANDSHAKE_RESPONSE}:{request_id}")
    order.data = locked.data
    order.updated_at = locked.updated_at
    return deepcopy(record)


def deliver_response(payload):
    """Worker boundary. Persist sending before HTTP; retries cannot resend it."""
    with transaction.atomic():
        order = Order.objects.select_for_update().get(ref=payload["order_ref"], channel_ref="ifood")
        records = deepcopy(_records(order))
        record = records.get(payload["dispute_id"], {})
        response = record.get("response", {})
        if record.get("state") != "queued" or response.get("id") != payload["request_id"]:
            return
        raw = record.get("raw", {})
        expiry = _expiry(raw)
        if not expiry or not timezone.is_aware(expiry) or expiry <= timezone.now():
            record["state"] = "expired"
            _save(order, records)
            return
        record["state"] = "sending"
        _save(order, records)
    state = "unknown"
    result = None
    try:
        headers = ifood_auth.authorized_headers()
        if headers:
            cfg = getattr(settings, "SHOPMAN_IFOOD", {}) or {}
            base = str(cfg.get("api_base") or "https://merchant-api.ifood.com.br").rstrip("/")
            url = f"{base}/order/v1.0/disputes/{quote(payload['dispute_id'], safe='')}/{response['decision']}"
            http = requests.post(url, headers=headers, json=response["body"], timeout=int(cfg.get("timeout") or 30))
            if http.status_code == 201:
                state = "sent"
                try:
                    result = http.json()
                except ValueError:
                    logger.error("ifood_handshake: HTTP 201 com JSON inválido; aguardando HSS para disputa %s", payload["dispute_id"])
            else:
                logger.error("ifood_handshake: HTTP %s na disputa %s; resultado incerto, sem reenvio automático", http.status_code, payload["dispute_id"])
        else:
            logger.error("ifood_handshake: autorização indisponível para disputa %s; resposta não enviada", payload["dispute_id"])
    except requests.RequestException:
        logger.error("ifood_handshake: falha de transporte na disputa %s; resultado incerto, sem reenvio automático", payload["dispute_id"])
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        records = deepcopy(_records(order))
        record = records[payload["dispute_id"]]
        # An HSS may arrive while the POST is in flight; never reopen it.
        if record.get("state") == "sending" and record.get("response", {}).get("id") == payload["request_id"]:
            record["state"] = state
            record["response"].update(result=result, sent_at=timezone.now().isoformat())
            _save(order, records)
