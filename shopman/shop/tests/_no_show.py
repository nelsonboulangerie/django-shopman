"""O mundo mínimo dos testes do "Não retirado" (WP-G11).

Uma loja com expediente das 7h às 19h todos os dias, o canal ``web`` com a régua
que deixa pronto virar cancelado, produtos com estoque em LOTE na vitrine e um
pedido de retirada pronto, com a reserva já baixada (como ele chega a ``ready``).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone
from shopman.orderman.models import Order, OrderItem

OPEN_EVERY_DAY = {
    day: {"open": "07:00", "close": "19:00"}
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
}

#: O ciclo padrão do Orderman com UMA diferença: pronto pode virar cancelado.
TRANSITIONS = {
    "new": ["accepted", "cancelled"],
    "accepted": ["preparing", "ready", "cancelled"],
    "preparing": ["ready", "cancelled"],
    "ready": ["preparing", "dispatched", "completed", "cancelled"],
    "dispatched": ["delivered", "returned"],
    "delivered": ["completed", "returned"],
    "completed": ["returned"],
    "cancelled": [],
    "returned": [],
}


def at(hour: int, minute: int = 0, *, days: int = 0) -> datetime:
    """``hour:minute`` de hoje (ou de ``days`` dias adiante), na hora da loja.

    "Hoje" é o dia do relógio de verdade, não o de ``timezone.now``: quem crava o
    relógio com esta função não pode depender do relógio que está cravando.
    """
    day = timezone.localtime(datetime.now(tz=UTC)).date() + timedelta(days=days)
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


#: A regra de retenção da loja de teste: a mesma que o dono decidiu (24/11/2026).
RETENTION = {"percent": 40, "decided_at": "2026-11-24", "provisional": True}


def make_shop(**fields):
    from shopman.shop.models import Shop

    fields.setdefault("opening_hours", OPEN_EVERY_DAY)
    # A regra de retenção entra junto com os padrões que o teste passa, sem apagá-los.
    defaults = dict(fields.pop("defaults", None) or {})
    defaults["no_show"] = {"retention": dict(RETENTION), **(defaults.get("no_show") or {})}
    fields["defaults"] = defaults
    return Shop.objects.create(name="Padaria de teste", **fields)


def produced(sku: str):
    """Ficha ativa para ``sku``: a casa produz, e a perda dele tem retenção."""
    from shopman.craftsman.models import Recipe

    return Recipe.objects.create(ref=f"ficha-{sku.lower()}", name=f"Ficha {sku}", output_sku=sku, batch_size=1)


def vitrine():
    from shopman.stockman import PositionKind
    from shopman.stockman.models import Position

    position, _ = Position.objects.get_or_create(
        ref="vitrine", defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return position


def product(sku: str, *, price_q: int = 1000, shelf_life_days: int | None = None):
    from shopman.offerman.models import Product

    return Product.objects.create(
        sku=sku, name=sku.title(), base_price_q=price_q, is_published=True, is_sellable=True,
        shelf_life_days=shelf_life_days,
    )


def lot(sku: str, *, qty: int = 10, produced: date | None = None, expires: date | None = None):
    """Estoque de ``sku`` na vitrine, num lote com nome e validade. Devolve o ``Quant``."""
    from shopman.stockman.models import Batch
    from shopman.stockman.services.movements import StockMovements

    produced = produced or timezone.localdate()
    ref = f"{sku}-{produced:%Y%m%d}"
    Batch.objects.get_or_create(ref=ref, defaults={"sku": sku, "production_date": produced, "expiry_date": expires})
    return StockMovements.receive(quantity=Decimal(qty), sku=sku, position=vitrine(), batch=ref, reason="Fornada")


def fulfilled_hold(sku: str, qty, *, order_ref: str) -> dict:
    """Reserva ``qty`` de ``sku`` e baixa: a entrada de ``order.data["hold_ids"]`` de um pedido pronto."""
    from shopman.shop.adapters import get_adapter

    adapter = get_adapter("stock")
    result = adapter.create_hold(sku=sku, qty=Decimal(str(qty)), reference=f"order:{order_ref}")
    assert result["success"], result
    done = adapter.fulfill_hold(result["hold_id"])
    assert done["success"], done
    return {"sku": sku, "hold_id": result["hold_id"], "qty": float(qty)}


def ready_order(
    ref: str,
    lines: list[tuple[str, int, int]],
    *,
    channel_ref: str = "web",
    payment: dict | None = None,
    data: dict | None = None,
    ready_at: datetime | None = None,
    held: bool = True,
) -> Order:
    """Pedido de retirada pronto. ``lines``: ``(sku, qty, unit_price_q)``.

    ``held=True`` reserva e baixa cada linha (o caminho normal até ``ready``);
    ``held=False`` deixa o pedido sem reserva nenhuma.
    """
    total_q = sum(qty * price for _sku, qty, price in lines)
    order = Order.objects.create(
        ref=ref, channel_ref=channel_ref, session_key=f"sk-{ref}", status=Order.Status.READY, total_q=total_q,
        data={"fulfillment_type": "pickup", "payment": payment or {"method": "cash"}, **(data or {})},
        snapshot={
            "lifecycle": {"transitions": TRANSITIONS},
            "items": [{"line_id": f"L{n}", "sku": sku, "qty": qty} for n, (sku, qty, _price) in enumerate(lines, 1)],
        },
    )
    for n, (sku, qty, price) in enumerate(lines, 1):
        OrderItem.objects.create(
            order=order, line_id=f"L{n}", sku=sku, name=sku.title(), qty=qty,
            unit_price_q=price, line_total_q=qty * price,
        )
    if held:
        order.data["hold_ids"] = [fulfilled_hold(sku, qty, order_ref=ref) for sku, qty, _price in lines]
        order.save(update_fields=["data", "updated_at"])
    Order.objects.filter(pk=order.pk).update(ready_at=ready_at or timezone.now())
    order.refresh_from_db()
    return order


def pay(order: Order, method: str, amount_q: int | None = None) -> str:
    """Captura ``amount_q`` (o total, por padrão) no Payman pela forma dada. Devolve o ``intent_ref``.

    ``pix``/``card`` entram pelo gateway de teste; o resto (dinheiro, maquininha) é
    liquidado sem gateway, como o balcão faz.
    """
    from shopman.payman import PaymentService

    amount_q = order.total_q if amount_q is None else amount_q
    intent_ref = f"PAY-{order.ref}-{method}"
    if method in ("pix", "card"):
        PaymentService.create_intent(order.ref, amount_q, method, gateway="mock", ref=intent_ref)
        PaymentService.authorize(intent_ref, gateway_id=f"gw-{intent_ref}")
        PaymentService.capture(intent_ref)
    else:
        PaymentService.settle(order.ref, amount_q, method, ref=intent_ref)
    payment = dict((order.data or {}).get("payment") or {})
    payment.update({"method": method, "intent_ref": intent_ref})
    order.data["payment"] = payment
    order.save(update_fields=["data", "updated_at"])
    return intent_ref


def refunded_q(order_ref: str) -> int:
    from shopman.payman.models import PaymentTransaction

    return sum(
        PaymentTransaction.objects.filter(intent__order_ref=order_ref, type="refund").values_list("amount_q", flat=True)
    )
