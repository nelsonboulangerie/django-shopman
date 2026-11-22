"""Plano que cresce prende primeiro a demanda sem fornada da data (#2701).

A encomenda acima do plano prende o que a fornada da data cobre, e o resto vira
DEMANDA: reserva sem saldo (``Hold.quant`` nulo), que não desconta o livre de
ninguém (#2685). Quando a Produção planeja mais para a data (o aviso "Planeje mais
N" existe para isso), as unidades novas entravam livres na leitura, prometíveis a
qualquer outro pedido, até a fornada sair (o ``realize`` materializa presas e
flutuantes juntas). A encomenda que pediu o aumento podia perdê-lo.

Aqui, depois que o plano da data cresce, a demanda daquela data se prende às
unidades novas, na ordem de atendimento da produção (``_service_order``: pedido
antes de sacola, a mais antiga primeiro), até onde o plano cobre. O que não cabe
continua demanda. O resto do livre fica livre.

Sem mexer no Core: a troca usa as portas que a reserva da encomenda já usa
(``create_holds_up_to`` prende o que cabe, ``create_hold(allow_demand=True)``
registra o resto) e solta a reserva de demanda antiga, numa transação, com o
saldo travado antes da reserva (a ordem do Stockman).
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction

from shopman.shop.adapters import get_adapter

logger = logging.getLogger(__name__)

#: A referência que a reserva da encomenda carrega (``stock.hold``).
_ORDER_REFERENCE_PREFIX = "order:"


def anchor_demand(sku: str, target_date) -> list[str]:
    """Prende ao plano da data a demanda sem fornada de ``sku``. Devolve os pedidos tocados."""
    from shopman.orderman.models import Order
    from shopman.stockman.models import Hold, Quant
    from shopman.stockman.services.planning import _service_order

    from shopman.shop.services import stock as stock_service

    if not sku or target_date is None:
        return []
    adapter = get_adapter("stock")
    touched: list[str] = []
    with transaction.atomic():
        # Quant antes de Hold, como em ``hold``, ``fulfill`` e ``realize``.
        list(Quant.objects.select_for_update().filter(sku=sku, target_date=target_date).order_by("pk"))
        floating = list(
            Hold.objects.select_for_update()
            .filter(sku=sku, target_date=target_date, quant__isnull=True)
            .active()
        )
        for hold in _service_order(floating):
            reference = str((hold.metadata or {}).get("reference") or "")
            if not reference.startswith(_ORDER_REFERENCE_PREFIX):
                continue
            order = Order.objects.select_for_update().filter(ref=reference[len(_ORDER_REFERENCE_PREFIX):]).first()
            if order is None or order.status in Order.TERMINAL_STATUSES:
                continue
            kwargs = {
                "target_date": target_date,
                "reference": reference,
                "channel_ref": order.channel_ref,
                "ttl_minutes": stock_service._order_hold_ttl_minutes(target_date),
                "apply_safety_margin": False,
                "priority": (hold.metadata or {}).get("priority", stock_service._ORDER_HOLD_PRIORITY),
            }
            parts = adapter.create_holds_up_to(sku=sku, qty=hold.quantity, **kwargs)
            anchored = sum((Decimal(str(qty)) for _hold_id, qty in parts), Decimal("0"))
            if anchored <= 0:
                # O plano não tem mais nada livre: as próximas da fila também não cabem.
                break
            entries = [{"sku": sku, "hold_id": hold_id, "qty": float(qty)} for hold_id, qty in parts]
            remainder = Decimal(str(hold.quantity)) - anchored
            if remainder > 0:
                rest = adapter.create_hold(sku=sku, qty=remainder, allow_demand=True, **kwargs)
                if not rest.get("success"):
                    # Sem registrar o resto, a demanda do pedido sumiria: desfaz tudo.
                    raise RuntimeError(f"demand_anchor: o resto da demanda não foi registrado: {rest!r}")
                entries.append({"sku": sku, "hold_id": rest["hold_id"], "qty": float(remainder)})
            adapter.release_holds([hold.hold_id])
            data = dict(order.data or {})
            data["hold_ids"] = [
                entry
                for entry in data.get("hold_ids") or []
                if not (isinstance(entry, dict) and entry.get("hold_id") == hold.hold_id)
            ] + entries
            order.data = data
            order.save(update_fields=["data", "updated_at"])
            touched.append(order.ref)
            logger.info(
                "demand_anchor: order=%s sku=%s target=%s anchored=%s remainder=%s",
                order.ref, sku, target_date, anchored, remainder,
            )
        for ref in dict.fromkeys(touched):
            _resolve_over_plan_alert(ref)
    return list(dict.fromkeys(touched))


def _resolve_over_plan_alert(order_ref: str) -> None:
    """O aviso "Planeje mais N" se resolve quando o pedido não tem mais demanda sem fornada."""
    from shopman.orderman.models import Order

    from shopman.shop.adapters import alert as alert_adapter
    from shopman.shop.services import stock as stock_service

    order = Order.objects.get(ref=order_ref)
    if any(held["demand"] > 0 for held in stock_service.held_supply_by_sku(order).values()):
        return
    alert_adapter.resolve(stock_service.DEMAND_OVER_PLAN_ALERT, order_ref=order_ref, actor="system:demand-anchor")


def on_production_changed(sender, product_ref, date, action, **kwargs):
    """Plano novo ou aumentado: depois do commit, a demanda da data se prende a ele.

    Depois do commit, e não no meio: a ponte de produção (``craftsman.contrib.
    stockman``) escreve o saldo planejado no mesmo sinal, e a ordem dos receivers
    não é contrato.
    """
    if action not in ("planned", "adjusted") or not product_ref or date is None:
        return

    def _anchor():
        try:
            anchor_demand(product_ref, date)
        except Exception:
            logger.exception("demand_anchor failed sku=%s date=%s", product_ref, date)

    transaction.on_commit(_anchor)


def connect() -> None:
    from shopman.craftsman.signals import production_changed

    production_changed.connect(
        on_production_changed,
        dispatch_uid="shopman.shop.services.demand_anchor.on_production_changed",
        weak=False,
    )
