"""Observa quando um produto deixa (e volta) de estar disponível para oferecer.

Quem responde "posso oferecer este SKU neste canal?" continua sendo o stockman
(``availability_for_skus`` + o escopo do canal). Aqui só se observa a
**transição** dessa resposta e se carimba o período — uma pergunta, um dono.

Dois gatilhos, porque nenhum sozinho cobre tudo:

- **evento**: mudou estoque ou reserva, então a resposta pode ter mudado.
- **reconciliação periódica**: reserva que expira não emite evento (o sweep
  usa update em massa), e sem uma varredura calma a volta do produto ficaria
  registrada tarde demais.

A reconciliação é idempotente e recomputa do estado atual: rodar duas vezes
seguidas não cria nem fecha nada a mais.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def offering_channel_refs() -> list[str]:
    """Canais que efetivamente vendem — vitrine de exposição não conta."""
    from shopman.shop.models import Channel

    return list(
        Channel.objects.filter(is_active=True, commerce_policy="order")
        .values_list("ref", flat=True)
    )


def can_offer(sku: str, *, channel_ref: str) -> bool | None:
    """O produto está disponível para oferecer AGORA neste canal?

    ``None`` quando a pergunta não se aplica: produto pausado é decisão
    comercial, não ruptura, e não deve virar falta de abastecimento.
    """
    from shopman.shop.projections.catalog_context import availability_for_sku

    info = availability_for_sku(sku, channel_ref=channel_ref)
    if info is None:
        return None
    if info.get("is_paused"):
        return None
    return _is_offerable(info)


def _is_offerable(info: dict) -> bool:
    """Disponível de verdade OU com fornada planejada que o canal aceita.

    Encomenda para amanhã não é falta: o cliente consegue pedir.
    """
    if (info.get("total_promisable") or 0) > 0:
        return True
    policy = info.get("availability_policy", "planned_ok")
    if policy == "planned_ok" and info.get("is_planned"):
        return True
    return policy == "demand_ok"


def observe(sku: str, *, channels: list[str] | None = None) -> None:
    """Abre ou fecha a falta de um SKU conforme a resposta de agora.

    Best-effort: uma falha aqui nunca pode derrubar uma venda ou uma fornada —
    perde-se precisão da medição, e a reconciliação corrige no ciclo seguinte.
    """
    try:
        for channel_ref in channels if channels is not None else offering_channel_refs():
            _apply(sku, channel_ref, can_offer(sku, channel_ref=channel_ref))
    except Exception:
        logger.debug("shelf_outage.observe falhou para %s", sku, exc_info=True)


def _apply(sku: str, channel_ref: str, offerable: bool | None) -> None:
    from shopman.backstage.models import ShelfOutage

    if offerable is None:  # pausado: nem abre nem fecha; a falta não é de estoque
        return
    now = timezone.now()
    with transaction.atomic():
        open_outage = (
            ShelfOutage.objects.select_for_update()
            .filter(sku=sku, channel_ref=channel_ref, ended_at__isnull=True)
            .first()
        )
        if offerable and open_outage is not None:
            open_outage.ended_at = now
            open_outage.save(update_fields=["ended_at"])
        elif not offerable and open_outage is None:
            ShelfOutage.objects.create(
                sku=sku, channel_ref=channel_ref, started_at=now
            )


def reconcile_outages() -> dict[str, int]:
    """Alinha as faltas abertas com o estado atual. Idempotente.

    Cobre o buraco dos eventos: reserva que expira por varredura em massa não
    dispara signal, e sem isto a volta do produto ficaria registrada só no
    próximo movimento de estoque — que pode ser no dia seguinte.
    """
    from shopman.backstage.models import ShelfOutage

    channels = offering_channel_refs()
    if not channels:
        return {"opened": 0, "closed": 0, "checked": 0}

    skus = set(_tracked_skus())
    skus.update(
        ShelfOutage.objects.filter(ended_at__isnull=True).values_list("sku", flat=True)
    )

    before_open = set(
        ShelfOutage.objects.filter(ended_at__isnull=True).values_list(
            "sku", "channel_ref"
        )
    )
    for sku in sorted(skus):
        observe(sku, channels=channels)
    after_open = set(
        ShelfOutage.objects.filter(ended_at__isnull=True).values_list(
            "sku", "channel_ref"
        )
    )

    return {
        "opened": len(after_open - before_open),
        "closed": len(before_open - after_open),
        "checked": len(skus) * len(channels),
    }


def _tracked_skus() -> list[str]:
    """SKUs com estoque controlado — os únicos que podem faltar."""
    from shopman.stockman.models import Quant

    return list(
        Quant.objects.filter(position__is_saleable=True)
        .values_list("sku", flat=True)
        .distinct()
    )
