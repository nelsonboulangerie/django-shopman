"""
iFood order ingest — canonical entry point for marketplace orders.

A single function, :func:`ingest`, turns an iFood canonical payload into a
real ``Order`` in the iFood channel and emits the ``order_changed`` signal
so ``lifecycle.dispatch(order, "on_commit")`` runs the normal marketplace
flow (stock hold, customer.ensure with iFood strategy, etc.).

Used by:

- **Real iFood webhook** (when wired) — delegates here after authenticating
  the callback.
- **Dev simulation** — the checkout "Simular pedido iFood" button and the
  "Injetar pedido iFood simulado" admin action both build a payload with
  :func:`shopman.shop.services.ifood_simulation.session_to_ifood_payload`
  and call this service. The order runs through the exact same path a
  real callback would take.

Payload shape (canonical)
-------------------------

::

    {
        "order_code": "IFOOD-ABC123",   # required — external id
        "merchant_id": "mock-merchant", # optional — from channel config
        "created_at": "2026-04-15T...", # optional — defaults to now()
        "customer": {
            "name": "Cliente iFood",
            "phone": "",
        },
        "delivery": {
            "type": "DELIVERY",          # DELIVERY | TAKEOUT
            "address": "Rua X, 123",     # free-text
            "complement": "Apto 42",     # optional — apartment/block/back door
            "reference": "portão azul",  # optional — landmark the customer typed
            "postal_code": "86020-000",  # optional
            "delivered_by": "MERCHANT",  # optional — MERCHANT | IFOOD
        },
        "items": [
            {
                "sku": "PAO-001",
                "name": "Pão francês",
                "qty": 2,
                "unit_price_q": 500,
            },
            ...
        ],
        "notes": "sem cebola",
    }
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from django.db import transaction
from shopman.orderman.ids import generate_order_ref
from shopman.orderman.models import Order, OrderItem
from shopman.orderman.signals import order_changed
from shopman.utils.monetary import monetary_mult

logger = logging.getLogger(__name__)

IFOOD_CHANNEL_REF = "ifood"


class IFoodIngestError(Exception):
    """Raised when an iFood payload cannot be ingested."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def session_key_for_order(merchant_id: str, order_code: str) -> str:
    """Stable KDS identity for an external order, assigned before Order sealing."""
    identity = json.dumps(["ifood", merchant_id or "", order_code], separators=(",", ":"))
    return f"ifood:{uuid5(NAMESPACE_URL, identity).hex}"


def ingest(payload: dict, *, channel_ref: str = IFOOD_CHANNEL_REF) -> Order:
    """Ingest a canonical iFood payload and return the created ``Order``.

    The order is created in status ``NEW``; ``lifecycle.dispatch`` (triggered
    by ``order_changed``) advances it according to the channel's
    ``ChannelConfig``. Marketplace channels typically have
    ``payment.timing="external"`` and ``confirmation.mode="manual"`` — the
    order waits for the operator to accept or reject via the admin.
    """
    from shopman.shop.models import Channel

    _validate_payload(payload)

    try:
        Channel.objects.get(ref=channel_ref)
    except Channel.DoesNotExist as e:
        raise IFoodIngestError(
            "channel_missing",
            f"Canal iFood '{channel_ref}' não encontrado. Rode o seed ou crie o canal no admin.",
        ) from e

    items = _normalize_items(payload["items"])
    items_subtotal_q = sum(int(item["line_total_q"]) for item in items)
    # Marketplace orders are pre-priced by iFood: the authoritative total is the
    # grand total (orderAmount = subtotal + delivery fee + service fees − benefits).
    # Fall back to the items subtotal when totals are absent (dev simulation).
    order_amount_q = int((payload.get("totals") or {}).get("order_amount_q") or 0)
    total_q = order_amount_q or items_subtotal_q

    order_code = payload["order_code"]
    delivery = payload.get("delivery") or {}
    fulfillment_type = _fulfillment_type(payload)

    order_data = {
        "origin_channel": channel_ref,
        "external_order_code": order_code,
        "merchant_id": payload.get("merchant_id", ""),
        "customer": payload.get("customer") or {},
        "delivery_address": delivery.get("address", ""),
        "fulfillment_type": fulfillment_type,
        "order_notes": payload.get("notes", ""),
        "payment": {
            "method": "external",
            "gateway": "ifood",
            "status": payment_status_from_payload(payload.get("payments") or {}, total_q),
            **_collection_on_delivery(payload, delivery, fulfillment_type),
        },
        "ifood": {
            "order_code": order_code,
            "merchant_id": payload.get("merchant_id", ""),
            "created_at": payload.get("created_at"),
            "display_id": payload.get("display_id", ""),
            "is_test": bool(payload.get("is_test", False)),
            "order_timing": payload.get("order_timing", ""),
            "schedule": payload.get("schedule") or {},
            "totals": payload.get("totals") or {},
            "payments": payload.get("payments") or {},
            "benefits": payload.get("benefits") or [],
            "delivered_by": delivery.get("delivered_by", ""),
            "pickup_code": delivery.get("pickup_code", ""),
        },
    }

    structured = _delivery_address_structured(delivery)
    if structured:
        order_data["delivery_address_structured"] = structured

    # iFood's optional customer.documentNumber is supplied for this order's
    # tax document, unlike a document fetched from our CRM. Bridge it to the
    # existing fiscal request contract; the fiscal adapter retains validation.
    # Explicit foreign IDs are preserved in customer, never relabelled CPF/CNPJ.
    customer = order_data["customer"]
    document = str(customer.get("document") or "").strip()
    document_type = str(customer.get("document_type") or "").strip().upper()
    if document and document_type in {"", "CPF", "CNPJ"}:
        order_data["fiscal"] = {"tax_id": document}

    if str(payload.get("order_timing") or "").upper() == "SCHEDULED":
        from shopman.shop.services.ifood_schedule import delivery_date_from_payload

        delivery_date = delivery_date_from_payload(payload.get("schedule") or {})
        if delivery_date is not None:
            order_data["delivery_date"] = delivery_date.isoformat()

    # Prazo do marketplace, gravado no pedido em vez de recalculado: é fato da
    # ingestão (quando ELE nasceu lá, com o SLA que valia então), não config de hoje.
    confirm_by = _external_confirm_deadline(channel_ref, payload.get("created_at"))
    if confirm_by:
        order_data["ifood"]["confirm_by"] = confirm_by

    # O pedido já tem um número no iFood, e é esse que o cliente, o portal e o suporte
    # falam. Adotá-lo como sufixo do ref (IFOOD-260919-4994) evita a tradução que o
    # operador tinha de fazer de cabeça; ocupado ou ausente, cai no sorteio de sempre.
    display_id = str(payload.get("display_id") or "").strip()
    ref = generate_order_ref(channel_ref=channel_ref, preferred_suffix=display_id)
    order_data["ifood"]["ref_from_display_id"] = bool(
        display_id and ref.endswith(f"-{display_id.upper()}")
    )

    with transaction.atomic():
        order = Order.objects.create(
            ref=ref,
            channel_ref=channel_ref,
            session_key=session_key_for_order(payload.get("merchant_id", ""), order_code),
            external_ref=order_code,
            handle_type="ifood_order",
            handle_ref=order_code,
            status=Order.Status.NEW,
            snapshot={
                "items": items,
                "data": dict(order_data),
                "pricing": {},
                "rev": 1,
                "commitment": {},
                "lifecycle": {},
                "source": "ifood.ingest",
            },
            data=order_data,
            total_q=total_q,
        )

        for item in items:
            OrderItem.objects.create(
                order=order,
                line_id=item["line_id"],
                sku=item["sku"],
                name=item.get("name", ""),
                qty=Decimal(str(item["qty"])),
                unit_price_q=int(item.get("unit_price_q", 0)),
                line_total_q=int(item["line_total_q"]),
                meta=item.get("meta", {}),
            )

        order.emit_event(
            event_type="created",
            actor="ifood.ingest",
            payload={"order_code": order_code},
        )

    order_changed.send(
        sender=Order,
        order=order,
        event_type="created",
        actor="ifood.ingest",
    )

    logger.info(
        "ifood_ingest: created order %s from external code %s",
        order.ref, order_code,
    )
    return order


# ── helpers ───────────────────────────────────────────────────────────


def _external_confirm_deadline(channel_ref: str, created_at) -> str:
    """Quando o MARKETPLACE cancela o pedido se ninguém confirmar (ISO), ou "".

    Lido do canal (``confirmation.external_sla_minutes``) e contado a partir do
    ``createdAt`` do iFood, não da nossa ingestão: o relógio deles já estava correndo
    antes de o evento chegar no polling.
    """
    from django.utils.dateparse import parse_datetime

    from shopman.shop.config import ChannelConfig

    try:
        minutes = int(ChannelConfig.for_channel(channel_ref).confirmation.external_sla_minutes or 0)
    except Exception:  # canal ausente ou config inválida não impede ingerir o pedido
        logger.warning("ifood_ingest: SLA externo indisponível para %s — card fica sem contagem", channel_ref)
        return ""
    if minutes <= 0 or not created_at:
        return ""
    placed = parse_datetime(str(created_at))
    if placed is None:
        return ""
    return (placed + timedelta(minutes=minutes)).isoformat()


def payment_status_from_payload(payments: dict, total_q: int) -> str:
    """Report iFood's settlement evidence without initiating a local charge.

    Delivery responsibility is not proof of payment: both merchant and iFood
    delivery can carry amounts still to collect. Keep those orders pending,
    including mixed payments, and do not label missing/partial evidence paid.
    """
    prepaid_q = int(payments.get("prepaid_q") or 0)
    pending_q = int(payments.get("pending_q") or 0)
    methods = payments.get("methods") or []
    if pending_q > 0 or any(
        int(method.get("value_q") or 0) > 0
        and (method.get("type") == "OFFLINE" or method.get("prepaid") is False)
        for method in methods
    ):
        return "pending"
    if pending_q == 0 and total_q > 0 and prepaid_q >= total_q:
        return "paid"
    return "unknown"


def _delivery_address_structured(delivery: dict) -> dict:
    """O que o entregador precisa e o endereço formatado não carrega.

    O ``formattedAddress`` do iFood é rua, número e bairro. O complemento
    (apto, bloco, fundos), o ponto de referência que o cliente digitou e o CEP
    vêm em campos SEPARADOS — e eram descartados aqui, embora o mapper já os
    trouxesse. O entregador saía sem saber em que andar tocar.

    Grava na chave que as duas superfícies de despacho JÁ leem:
    ``delivery_address_structured``, a mesma do checkout da loja
    (``backstage.projections.order_queue._delivery_address`` e
    ``backstage.services.receipt_escpos._delivery_lines``). O ponto de
    referência entra como ``delivery_instructions`` porque é ele que as duas
    imprimem sob "Referência:".

    O endereço formatado NÃO é repetido aqui: ele já é ``delivery_address``, e
    dois donos do mesmo texto é divergência esperando acontecer.

    Os COMPONENTES (logradouro, número, bairro, município, UF) entram pelo
    vocabulário canônico da casa — o mesmo que o checkout da loja grava e que o
    adapter fiscal lê. Não é repetir o texto formatado com outro nome: o
    destinatário da NFC-e de entrega a domicílio é montado de componente, e sem
    eles o pedido iFood de entrega era recusado antes do HTTP, por "confira
    logradouro, número, bairro, município, UF" — ou seja, não emitia nota
    nenhuma. Quem imprime a comanda continua lendo ``delivery_address`` e o
    complemento, e não vê diferença.
    """
    fields = {
        "complement": delivery.get("complement", ""),
        "delivery_instructions": delivery.get("reference", ""),
        "postal_code": delivery.get("postal_code", ""),
        "route": delivery.get("street", ""),
        "street_number": delivery.get("number", ""),
        "neighborhood": delivery.get("neighborhood", ""),
        "city": delivery.get("city", ""),
        "state_code": delivery.get("state", ""),
    }
    return {key: str(value).strip() for key, value in fields.items() if str(value or "").strip()}


#: Formas de pagamento do iFood → refs da casa. Só as que a casa sabe NOMEAR em
#: português na tela e no papel: fora daqui, a comanda imprimiria o vocabulário
#: cru do marketplace ("meal_voucher") num papel de balcão.
_IFOOD_PAYMENT_METHOD_REFS = {
    "CASH": "cash",
    "CREDIT": "credit",
    "DEBIT": "debit",
    "PIX": "pix",
}


def _collection_on_delivery(payload: dict, delivery: dict, fulfillment_type: str) -> dict:
    """Marca de "o dinheiro entra na porta" para o pedido iFood com saldo em aberto.

    O ingest já distinguia pagamento pendente (``payment_status_from_payload``),
    mas ninguém dizia ONDE ele seria recebido — e ``collection`` é justamente a
    marca canônica que o Gestor e a comanda leem para oferecer o acerto, imprimir
    "COBRAR NA ENTREGA" e o troco (``docs/reference/data-schemas.md``). Sem ela a
    filipeta saía só com "PAGAMENTO PENDENTE": sem valor a cobrar e sem troco.

    Três portas, todas fechando por falta de prova, nunca por suposição:

    1. **Só entrega.** Na retirada o dinheiro entra no balcão, e a marca de
       balcão (``terminal``) significa *já recebido* — que não é o caso.
    2. **Só quando o iFood diz que a LOJA entrega.** Com entregador do iFood
       quem recebe é o iFood, e o repasse vem no acerto deles; carimbar
       ``on_delivery`` ali mandaria a casa cobrar de novo e abriria acerto de
       dinheiro que nunca passou pela gaveta. ``delivered_by`` ausente é
       desconhecido, e desconhecido não autoriza cobrança.
    3. **Só com a forma de pagamento nomeada.** Um valor em aberto sem método
       reconhecido continua saindo como "PAGAMENTO PENDENTE" — o Gestor já
       detalha o caso em ``backstage.projections.ifood.payment_summary``.
    """
    if fulfillment_type != "delivery":
        return {}
    if str(delivery.get("delivered_by") or "").upper() != "MERCHANT":
        return {}

    tenders: list[dict] = []
    change_for_q = 0
    for method in (payload.get("payments") or {}).get("methods") or []:
        if not isinstance(method, dict):
            continue
        amount_q = int(method.get("value_q") or 0)
        # ``prepaid is None`` é ausência de informação (o iFood não mandou a
        # flag): não é prova de que falta receber.
        if amount_q <= 0 or method.get("prepaid") is not False:
            continue
        ref = _IFOOD_PAYMENT_METHOD_REFS.get(str(method.get("method") or "").upper())
        if ref is None:
            return {}
        tenders.append({
            "method": ref,
            "amount_q": amount_q,
            "collection": "on_delivery",
            "status": "pending",
        })
        if ref == "cash":
            change_for_q = max(change_for_q, int(method.get("change_for_q") or 0))

    if not tenders:
        return {}
    collection = {"collection": "on_delivery", "tenders": tenders}
    if change_for_q:
        collection["change_for_q"] = change_for_q
    return collection


def _validate_payload(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise IFoodIngestError("invalid_payload", "Payload deve ser um dict")
    if not payload.get("order_code"):
        raise IFoodIngestError("missing_order_code", "order_code é obrigatório")
    items = payload.get("items")
    if not items or not isinstance(items, list):
        raise IFoodIngestError("missing_items", "items (lista não vazia) é obrigatório")


def _normalize_items(raw_items: list[dict]) -> list[dict]:
    """Ensure every item has line_id / line_total_q computed."""
    normalized: list[dict] = []
    for idx, raw in enumerate(raw_items, start=1):
        if not raw.get("sku"):
            raise IFoodIngestError("item_missing_sku", f"item #{idx} sem sku")
        qty = Decimal(str(raw.get("qty", 0)))
        if qty <= 0:
            raise IFoodIngestError("item_invalid_qty", f"item {raw.get('sku')} com qty inválido")
        unit_price_q = int(raw.get("unit_price_q", 0))
        line_total_q = int(raw.get("line_total_q") or monetary_mult(qty, unit_price_q))
        normalized.append({
            "line_id": raw.get("line_id") or f"ifood-{idx}",
            "sku": raw["sku"],
            "name": raw.get("name", raw["sku"]),
            "qty": str(qty),
            "unit_price_q": unit_price_q,
            "line_total_q": line_total_q,
            "meta": raw.get("meta", {}),
        })
    return normalized


def _fulfillment_type(payload: dict) -> str:
    delivery = payload.get("delivery") or {}
    kind = str(delivery.get("type", "DELIVERY")).upper()
    return "delivery" if kind == "DELIVERY" else "pickup"


__all__ = ["ingest", "IFoodIngestError", "IFOOD_CHANNEL_REF"]
