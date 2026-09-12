"""Modo comercial do PDV e requisitos antes de lançar itens."""

from __future__ import annotations

from datetime import date

from django.utils import timezone

from shopman.shop.services.pos_intent import PosIntentError


def sales_mode(data: dict) -> str:
    """Lê o modo explícito; para registro antigo, infere pelo combinado."""
    stored = data.get("sales_mode") or (data.get("pos") or {}).get("sales_mode")
    if stored in ("counter", "order"):
        return stored
    return "order" if (
        data.get("fulfillment_type") == "delivery" or data.get("delivery_date") or data.get("delivery_time_slot")
    ) else "counter"


def validate_sales_mode(payload: dict, *, require_ready: bool) -> None:
    """Rascunho vazio pode completar o funil; itens exigem combinado completo."""
    mode = payload.get("sales_mode")
    if mode is None:
        return  # payload anterior ao rollout, sem modo persistido
    if mode not in ("counter", "order"):
        raise PosIntentError("invalid_sales_mode", "Escolha Balcão ou Encomendas.", field="sales_mode", focus="fulfillment")
    fulfillment = payload.get("fulfillment_type")
    if mode == "counter":
        if fulfillment not in (None, "", "pickup") or payload.get("delivery_date") or payload.get("delivery_time_slot"):
            raise PosIntentError(
                "counter_requires_immediate_pickup", "Balcão é para levar agora. Use Encomendas para agendar ou entregar.",
                field="sales_mode", focus="fulfillment",
            )
        return
    if not require_ready:
        return
    if not str(payload.get("customer_ref") or "").strip():
        raise PosIntentError(
            "order_customer_required", "Selecione ou cadastre o cliente antes de adicionar produtos.",
            field="customer_ref", focus="customer",
        )
    if fulfillment not in ("pickup", "delivery"):
        raise PosIntentError(
            "order_fulfillment_required", "Escolha Entrega ou Retirada antes de adicionar produtos.",
            field="fulfillment_type", focus="fulfillment",
        )
    try:
        day = date.fromisoformat(str(payload.get("delivery_date") or ""))
    except ValueError:
        day = None
    if day is None or day < timezone.localdate():
        raise PosIntentError(
            "order_date_required", "Informe a data da encomenda antes de adicionar produtos.",
            field="delivery_date", focus="schedule",
        )
    from shopman.guestman.models import Customer

    if not Customer.objects.filter(ref=str(payload["customer_ref"]).strip(), is_active=True).exists():
        raise PosIntentError(
            "order_customer_invalid", "Selecione um cliente ativo para esta encomenda.",
            field="customer_ref", focus="customer",
        )


def session_sales_payload(session) -> dict:
    data = session.data or {}
    return {
        **data,
        "sales_mode": (data.get("pos") or {}).get("sales_mode"),
        "customer_ref": (data.get("customer") or {}).get("ref") or data.get("customer_ref"),
    }
