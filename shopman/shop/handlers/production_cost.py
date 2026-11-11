"""Custo congelado da fornada (ADR-023 §3): grava no ``finish``, nunca depois.

Escuta o ``production_changed`` (``action="finished"``), o anúncio que o
Craftsman já faz depois de commitar o ledger da ordem, e grava
``WorkOrder.meta["cost_snapshot"]`` com o custo de cada insumo consumido
naquele instante (:func:`shopman.shop.adapters.cost.work_order_cost_snapshot`).
Anunciar sem esperar retorno é sinal (ADR-001): o Craftsman não sabe que custo
existe, e o Buyman não sabe que houve fornada.

**Congela uma vez.** Com a chave presente, nada se reescreve: nem um segundo
``finished`` (correção de qualidade, replay), nem uma mudança de preço no Compras.
O precedente é o ``Batch.nonconformity_percent`` (ADR-017).

**Não-crítico, mas não calado.** Blindado como o resto da cauda do sinal (a
fornada já está commitada e não pode virar 500 por causa do custo); a falha vai
ao log com traceback. Lacuna de custo não é falha: fica escrita no próprio
snapshot (``gaps``, ``total_q = None``) e no log em WARNING.
"""

from __future__ import annotations

import logging

from django.db import transaction

from shopman.shop.handlers._resilient import resilient_receiver

logger = logging.getLogger(__name__)


def connect() -> None:
    from shopman.craftsman.signals import production_changed

    production_changed.connect(
        on_production_changed,
        dispatch_uid="shopman.shop.handlers.production_cost.on_production_changed",
        weak=False,
    )


@resilient_receiver
def on_production_changed(sender, product_ref, date, action=None, work_order=None, **kwargs):
    if action != "finished" or work_order is None:
        return
    freeze_work_order_cost(work_order)


def freeze_work_order_cost(work_order) -> dict | None:
    """Grava o custo congelado da ordem, se ainda não houver. Devolve o snapshot novo."""
    from shopman.craftsman.models import WorkOrder

    from shopman.shop.adapters.cost import SNAPSHOT_KEY, work_order_cost_snapshot

    with transaction.atomic():
        locked = WorkOrder.objects.select_for_update().get(pk=work_order.pk)
        if locked.status != WorkOrder.Status.FINISHED:
            return None
        meta = dict(locked.meta or {})
        if SNAPSHOT_KEY in meta:
            return None
        snapshot = work_order_cost_snapshot(locked)
        meta[SNAPSHOT_KEY] = snapshot
        WorkOrder.objects.filter(pk=locked.pk).update(meta=meta)
    work_order.meta = meta
    if snapshot["gaps"]:
        logger.warning(
            "production_cost.frozen_with_gaps wo=%s gaps=%s",
            locked.ref,
            "; ".join(snapshot["gaps"]),
        )
    return snapshot
