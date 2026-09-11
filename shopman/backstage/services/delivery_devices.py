"""Exclusive physical reader custody; order lock precedes device lock everywhere."""
from uuid import UUID

from django.db import transaction
from shopman.orderman.models import Order

from shopman.backstage.models import DeliveryDevice

PREFIX = "card_machine:"


def needs_card_machine(order):
    payment = (order.data or {}).get("payment") or {}
    return payment.get("collection") == "on_delivery" and not payment.get("cod_settled_at") and (
        payment.get("method") in {"credit", "debit"}
        or any(t.get("method") in {"credit", "debit"} for t in payment.get("tenders") or [])
    )


def has_available(order):
    devices = getattr(order, "_delivery_devices", None)
    return (any(device.active and device.current_order_id is None for device in devices)
            if devices is not None else DeliveryDevice.objects.filter(active=True, current_order__isnull=True).exists())


def allocate(order, equipment, *, allowed):
    """Called inside advance_order's transaction after its fresh order lock."""
    from shopman.shop.services.operator_orders import OrderStateConflict

    selected = [ref for ref in equipment if ref.startswith(PREFIX)]
    if len(selected) > 1:
        raise ValueError("Escolha uma maquininha para esta entrega.")
    if not selected:
        if needs_card_machine(order) or "card_machine" in equipment:
            raise ValueError("Selecione a maquininha disponível no despacho do Gestor; se não houver, aguarde a devolução.")
        return None
    if "card_machine" not in allowed:
        raise ValueError("Este canal não permite levar maquininha.")
    try:
        ref = UUID(selected[0][len(PREFIX):])
    except ValueError:
        raise ValueError("Maquininha inválida. Atualize os aparelhos disponíveis.") from None
    device = DeliveryDevice.objects.select_for_update().filter(ref=ref).first()
    if device is None or not device.active or device.current_order_id is not None:
        raise OrderStateConflict("Esta maquininha não está disponível. Escolha outra ou aguarde a devolução.")
    device.current_order = order
    device.save(update_fields=("current_order",))
    return device


def release(order):
    """Release only this order's device; legacy generic custody stays generic."""
    from shopman.shop.services.operator_orders import OrderStateConflict

    ref = (order.data or {}).get("dispatch", {}).get("device_ref")
    if not ref:
        return
    device = DeliveryDevice.objects.select_for_update().filter(ref=ref, current_order=order).first()
    if device is None:
        raise OrderStateConflict("O vínculo da maquininha mudou. Confira a entrega antes de devolver.")
    device.current_order = None
    device.save(update_fields=("current_order",))


def guard_dispatch(sender, instance, raw=False, **kwargs):
    """All ORM order/fulfillment dispatch entries require prior physical allocation."""
    if raw or not instance.pk or instance.status != "dispatched":
        return
    if sender.objects.filter(pk=instance.pk, status="dispatched").exists():
        return
    order = instance if sender is Order else instance.order
    if not needs_card_machine(order) and not (order.data or {}).get("dispatch", {}).get("device_ref"):
        return
    # No implicit selection/reservation from courier or KDS. The authorized
    # operator chooses at dispatch; alternative entries explain that next action.
    with transaction.atomic():
        if not DeliveryDevice.objects.select_for_update().filter(current_order=order, active=True).exists():
            raise ValueError("Confirme a maquininha no despacho do Gestor antes de liberar esta entrega.")
