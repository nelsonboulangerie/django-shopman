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
    """Recusa da resposta do operador; ``field`` aponta a entrada (dialeto de erro)."""

    def __init__(self, message, *, field=""):
        super().__init__(message)
        self.field = field


# Contraproposta (Plataforma de Negociação): o iFood oferece as alternativas no
# HANDSHAKE_DISPUTE (``alternatives: [{id, type, metadata}]``) e a loja responde uma
# delas em ``disputes/{id}/alternatives/{alternativeId}``. Só estes três tipos têm
# corpo conhecido; tipo novo é recusado, nunca adivinhado.
MONEY_ALTERNATIVES = ("REFUND", "BENEFIT")
TIME_ALTERNATIVE = "ADDITIONAL_TIME"
ALTERNATIVE_TYPES = (*MONEY_ALTERNATIVES, TIME_ALTERNATIVE)


def _records(order):
    return (order.data or {}).get("ifood", {}).get("handshakes", {})


def _save(order, records):
    data = deepcopy(order.data or {})
    data.setdefault("ifood", {})["handshakes"] = records
    data["ifood"]["handshake_pending"] = any(r.get("state") != "settled" for r in records.values())
    order.data = data
    order.save(update_fields=["data", "updated_at"])
    # Toda mudança de estado passa por aqui; o aviso do Gestor acompanha depois do
    # commit (chegou, o operador respondeu, o iFood decidiu, venceu).
    order_ref = order.ref
    transaction.on_commit(lambda: sync_alert(order_ref), robust=True)


ALERT_TYPE = "ifood_negotiation_open"
_TIMEOUT_LABELS = {
    "ACCEPT_CANCELLATION": "o iFood cancela",
    "REJECT_CANCELLATION": "o pedido segue",
}


def _alert_text(order, raw, expires):
    # O detalhe da janela (dono, 08/10/2026): a origem ("iFood") e o assunto
    # ("Cliente pediu cancelamento") vêm de ``alert_specs``; o prazo e o horário, da
    # linha que conta ao vivo. Aqui só o pedido, o que muda (parcial) e a consequência.
    from shopman.shop.services.operator_orders import short_ref

    outcome = _TIMEOUT_LABELS.get(raw.get("timeoutAction"), "o iFood decide sozinho")
    partial = " · cancelamento parcial" if raw.get("action") == "PARTIAL_CANCELLATION" else ""
    return f"Pedido {short_ref(order.ref)}{partial} · sem resposta, {outcome}."


def sync_alert(order_ref):
    """Um aviso com prazo por negociação aberta; nenhum quando não há o que responder.

    O aviso é a interrupção do Gestor: sem Visto, a tela abre o modal; depois do
    Visto, lembra até a causa acabar. A causa acaba quando ninguém mais pode
    responder (o operador respondeu, o iFood decidiu, o prazo venceu)."""
    from shopman.shop.adapters import alert as alert_adapter
    from shopman.shop.services.observability import create_operator_alert

    order = Order.objects.filter(ref=order_ref, channel_ref="ifood").first()
    if order is None:
        return
    open_records = [(dispute_id, record) for dispute_id, record in _records(order).items() if _open(record)]
    if not open_records:
        alert_adapter.resolve(ALERT_TYPE, order_ref=order.ref, actor="ifood_handshake")
        return
    for _dispute_id, record in open_records:
        raw = record.get("raw") or {}
        expires = _expiry(raw)
        create_operator_alert(
            type=ALERT_TYPE,
            severity="error",
            message=_alert_text(order, raw, expires),
            order_ref=order.ref,
            respond_by=expires,
        )


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
                label += f", {amount.get('currency', '')} {major}.{minor:02d}"
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


def _cents(value):
    """``"500"`` ou ``500`` em centavos; ``None`` para o resto (bool, decimal, vazio)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value if value is not None else "")
    return int(text) if text.isascii() and text.isdigit() and len(text) < 15 else None


def alternatives(raw):
    """As contrapropostas que o Gestor sabe enviar, normalizadas.

    ``[{id, type, max_amount_q?, minutes?, reasons?}]``. Entrada malformada (sem id,
    teto que não é inteiro positivo, lista de minutos vazia) e tipo desconhecido
    ficam de fora: a tela não oferece o que o envio recusaria."""
    rows = []
    for entry in (raw or {}).get("alternatives") or []:
        if not isinstance(entry, dict) or not entry.get("id") or entry.get("type") not in ALTERNATIVE_TYPES:
            continue
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        row = {"id": str(entry["id"]), "type": entry["type"]}
        if entry["type"] in MONEY_ALTERNATIVES:
            ceiling = metadata.get("maxAmount")
            max_q = _cents(ceiling.get("value")) if isinstance(ceiling, dict) else None
            if not max_q or max_q <= 0:
                continue
            row["max_amount_q"] = max_q
        else:
            minutes = [m for m in metadata.get("allowedsAdditionalTimeInMinutes") or []
                       if isinstance(m, int) and not isinstance(m, bool) and m > 0]
            reasons = [r for r in metadata.get("allowedsAdditionalTimeReasons") or [] if isinstance(r, str) and r]
            if not minutes or not reasons:
                continue
            row.update(minutes=minutes, reasons=reasons)
        rows.append(row)
    return rows


def alternative_summary(kind, metadata):
    """``"reembolso de R$ 5,00"`` / ``"mais 15 minutos"``; ``""`` quando não dá para dizer."""
    from shopman.utils.monetary import format_money

    metadata = metadata if isinstance(metadata, dict) else {}
    if kind in MONEY_ALTERNATIVES:
        amount = metadata.get("amount")
        value = _cents(amount.get("value")) if isinstance(amount, dict) else None
        if value is None:
            return ""
        noun = "reembolso" if kind == "REFUND" else "benefício"
        return f"{noun} de R$ {format_money(value)}"
    if kind == TIME_ALTERNATIVE:
        minutes = metadata.get("additionalTimeInMinutes")
        if isinstance(minutes, int) and not isinstance(minutes, bool) and minutes > 0:
            return f"mais {minutes} minutos"
    return ""


def _selected_alternative(settlements):
    for item in reversed(list(settlements)):
        selected = item.get("selectedDisputeAlternative")
        if isinstance(selected, dict):
            summary = alternative_summary(selected.get("type"), selected.get("metadata"))
            if summary:
                return summary
    return ""


def _sent_alternative(record):
    response = record.get("response") or {}
    if response.get("decision") != "alternative":
        return ""
    body = response.get("body") or {}
    return alternative_summary(body.get("type"), body.get("metadata"))


def _notice(record):
    if record.get("state") == "settled":
        labels = {"ACCEPTED": "Solicitação aceita pelo iFood.", "REJECTED": "Solicitação recusada pelo iFood.", "EXPIRED": "Negociação encerrada por prazo no iFood."}
        outcomes = [item.get("status") for item in record.get("settlements", {}).values() if item.get("status") in labels]
        if outcomes:
            selected = _selected_alternative(record.get("settlements", {}).values())
            if selected and outcomes[-1] == "ACCEPTED":
                return f"O cliente aceitou a contraproposta: {selected}. O estado do pedido é atualizado pelos eventos oficiais do pedido."
            return labels[outcomes[-1]] + " O estado do pedido é atualizado pelos eventos oficiais do pedido."
    if _open(record):
        return ""
    sent = _sent_alternative(record)
    if sent and record.get("state") in {"sent", "awaiting_customer"}:
        return f"Contraproposta enviada ({sent}); aguardando a decisão do cliente no iFood."
    return {
        "queued": "Resposta do operador aguardando envio ao iFood.",
        "sending": "Envio iniciado; aguarde a confirmação do iFood. Não repita a decisão.",
        "sent": "Resposta enviada; aguardando o resultado da negociação no iFood.",
        "awaiting_customer": "Contraproposta registrada; aguardando a decisão final no iFood.",
        "unknown": "Envio sem confirmação. Consulte a negociação no iFood antes de qualquer nova decisão.",
        "settled": "Resultado registrado pelo iFood. O cancelamento do pedido depende do evento de cancelamento.",
        "expired": "Prazo encerrado antes do envio; aguarde o resultado do iFood.",
    }.get(record.get("state"), "Negociação vencida ou cenário não suportado; consulte o iFood.")


def open_deadline(order):
    """A negociação aberta de prazo mais curto: ``(recebida, prazo)`` ou ``None``.

    É o que a Fila do Gestor ordena: o pedido espera uma resposta ao iFood."""
    windows = []
    for record in _records(order).values():
        if not _open(record):
            continue
        expires = _expiry(record.get("raw") or {})
        received = parse_datetime(str(record.get("received_at") or "")) or expires
        windows.append((received, expires))
    return min(windows, key=lambda window: window[1]) if windows else None


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
            "reject_reasons": list(REJECT_REASONS), "alternatives": alternatives(raw),
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
        # Quando a loja ficou sabendo: o relógio da Fila conta daqui até o prazo.
        record["received_at"] = timezone.now().isoformat()
    record["last_event_id"] = str(event["id"])
    _save(order, records)
    return True


def _alternative_body(raw, *, alternative_id, amount_q, minutes, reason):
    """O corpo da contraproposta, validado contra as alternativas gravadas do iFood."""
    from shopman.utils.monetary import format_money

    offered = [entry for entry in (raw.get("alternatives") or [])
               if isinstance(entry, dict) and str(entry.get("id") or "") == alternative_id and alternative_id]
    if not offered:
        raise HandshakeValidationError("Escolha uma contraproposta oferecida pelo iFood nesta negociação.", field="alternative_id")
    kind = offered[0].get("type")
    if kind not in ALTERNATIVE_TYPES:
        raise HandshakeValidationError(
            f"O Gestor não sabe enviar a contraproposta do tipo {kind or 'sem tipo'}. Responda esta no portal do iFood.",
            field="alternative_id",
        )
    normalized = next((row for row in alternatives(raw) if row["id"] == alternative_id), None)
    if normalized is None:
        raise HandshakeValidationError("A contraproposta veio incompleta do iFood. Responda esta no portal do iFood.", field="alternative_id")
    if kind in MONEY_ALTERNATIVES:
        if minutes is not None or reason:
            raise HandshakeValidationError("Contraproposta de valor não leva tempo nem motivo.", field="minutes")
        ceiling = normalized["max_amount_q"]
        if not isinstance(amount_q, int) or isinstance(amount_q, bool) or not 0 < amount_q <= ceiling:
            raise HandshakeValidationError(f"Informe um valor de R$ 0,01 até R$ {format_money(ceiling)}.", field="amount_q")
        return {"type": kind, "metadata": {"amount": {"value": str(amount_q), "currency": "BRL"}}}
    if amount_q is not None:
        raise HandshakeValidationError("Contraproposta de tempo não leva valor.", field="amount_q")
    if minutes not in normalized["minutes"] or isinstance(minutes, bool):
        raise HandshakeValidationError("Escolha um dos tempos oferecidos pelo iFood.", field="minutes")
    if reason not in normalized["reasons"]:
        raise HandshakeValidationError("Escolha um dos motivos oferecidos pelo iFood.", field="reason")
    return {"type": kind, "metadata": {"additionalTimeInMinutes": minutes, "additionalTimeReason": reason}}


@transaction.atomic
def enqueue_response(order, *, dispute_id, decision, reason="", detail_reason="", alternative_id="",
                     amount_q=None, minutes=None, actor, expected_revision=None):
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
    if decision not in {"accept", "reject", "alternative"}:
        raise HandshakeValidationError("Escolha aceitar, recusar ou fazer uma contraproposta.", field="decision")
    if not isinstance(reason, str) or not isinstance(detail_reason, str) or len(detail_reason) > 250:
        raise HandshakeValidationError("Motivo inválido; detalhe limitado a 250 caracteres.", field="reason")
    if decision == "alternative":
        if detail_reason:
            raise HandshakeValidationError("Detalhamento disponível somente no aceite.", field="detail_reason")
        body = _alternative_body(record["raw"], alternative_id=str(alternative_id or ""), amount_q=amount_q,
                                 minutes=minutes, reason=reason)
        path = f"alternatives/{quote(str(alternative_id), safe='')}"
    else:
        if alternative_id or amount_q is not None or minutes is not None:
            raise HandshakeValidationError("Valor e tempo só valem numa contraproposta.", field="alternative_id")
        allowed = (_extra(record["raw"], "acceptCancellationReasons", []) or []) if decision == "accept" else REJECT_REASONS
        if (allowed and reason not in allowed) or (not allowed and reason):
            raise HandshakeValidationError("Escolha um motivo permitido pelo iFood.", field="reason")
        if decision == "reject" and detail_reason:
            raise HandshakeValidationError("Detalhamento disponível somente no aceite.", field="detail_reason")
        body = {"reason": reason} if reason else {}
        if detail_reason:
            body["detailReason"] = detail_reason
        path = decision
    request_id = uuid4().hex
    record.update(state="queued", response={"id": request_id, "decision": decision, "path": path, "body": body,
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
        headers, auth_reason = ifood_auth.headers_with_reason()
        if headers:
            cfg = getattr(settings, "SHOPMAN_IFOOD", {}) or {}
            base = str(cfg.get("api_base") or "https://merchant-api.ifood.com.br").rstrip("/")
            # ``path`` foi montado e validado sob o lock do enqueue: ``accept``,
            # ``reject`` ou ``alternatives/<id>`` (contraproposta).
            url = f"{base}/order/v1.0/disputes/{quote(payload['dispute_id'], safe='')}/{response['path']}"
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
            # A razão importa: falta de credencial se resolve no ambiente, recusa
            # do edge se resolve com retry, e as duas devolviam a mesma linha.
            logger.error(
                "ifood_handshake: %s — disputa %s, resposta não enviada",
                ifood_auth.failure_message(auth_reason),
                payload["dispute_id"],
            )
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
