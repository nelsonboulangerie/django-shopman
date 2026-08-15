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


def offer_block_reason(sku: str, *, channel_ref: str) -> str | None:
    """Por que o cliente não consegue comprar este SKU agora, se for o caso.

    Três respostas distintas, e a distinção importa:

    - ``""`` — dá para comprar;
    - ``"paused"`` / ``"sold_out"`` — não dá, e por quê;
    - ``None`` — **não sabemos** (a consulta falhou). Nesse caso nada é aberto
      nem fechado: ausência de resposta não é resposta.

    Pausa tem precedência sobre falta: produto pausado não é vendável nem com
    estoque cheio, então é a pausa que explica o bloqueio.
    """
    from shopman.shop.projections.catalog_context import availability_for_sku

    info = availability_for_sku(sku, channel_ref=channel_ref)
    return _reason_from(info)


def _reason_from(info: dict | None) -> str | None:
    from shopman.backstage.models import OutageReason

    if info is None:
        return None
    if info.get("is_paused"):
        return OutageReason.PAUSED
    return "" if _is_offerable(info) else OutageReason.SOLD_OUT


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
            _apply(sku, channel_ref, offer_block_reason(sku, channel_ref=channel_ref))
    except Exception:
        logger.debug("shelf_outage.observe falhou para %s", sku, exc_info=True)


def _apply(sku: str, channel_ref: str, reason: str | None) -> None:
    """Abre, fecha ou troca o motivo do período aberto.

    Mudança de motivo fecha um período e abre outro no mesmo instante: o
    bloqueio continua ininterrupto para o cliente, e o tempo fica atribuído ao
    motivo certo para o gestor.
    """
    from shopman.backstage.models import ShelfOutage

    if reason is None:  # não sabemos: não afirmar nada
        return
    now = timezone.now()
    with transaction.atomic():
        open_outage = (
            ShelfOutage.objects.select_for_update()
            .filter(sku=sku, channel_ref=channel_ref, ended_at__isnull=True)
            .first()
        )
        if open_outage is not None and (not reason or open_outage.reason != reason):
            open_outage.ended_at = now
            open_outage.save(update_fields=["ended_at"])
            open_outage = None
        if reason and open_outage is None:
            ShelfOutage.objects.create(
                sku=sku, channel_ref=channel_ref, reason=reason, started_at=now
            )


def reconcile_outages() -> dict[str, int]:
    """Alinha os bloqueios abertos com o estado atual. Idempotente.

    Cobre dois buracos dos eventos: reserva que expira por varredura em massa
    não dispara signal (sem isto a volta do produto ficaria registrada só no
    próximo movimento de estoque, que pode ser no dia seguinte), e **pausar ou
    despausar** um produto acontece no catálogo, longe de estoque e reserva.

    Usa a consulta em LOTE: o ciclo roda a cada poucos minutos sobre o catálogo
    inteiro, e uma consulta por SKU custaria centenas de idas ao banco.
    """
    from shopman.backstage.models import ShelfOutage

    channels = offering_channel_refs()
    if not channels:
        return {"opened": 0, "closed": 0, "checked": 0}

    skus = sorted(_watched_skus())
    if not skus:
        return {"opened": 0, "closed": 0, "checked": 0}

    before_open = set(
        ShelfOutage.objects.filter(ended_at__isnull=True).values_list(
            "sku", "channel_ref"
        )
    )
    for channel_ref in channels:
        for sku, reason in _reasons_for_channel(skus, channel_ref).items():
            _apply(sku, channel_ref, reason)
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


def _reasons_for_channel(skus: list[str], channel_ref: str) -> dict[str, str | None]:
    from shopman.shop.projections.catalog_context import availability_for_skus

    infos = availability_for_skus(skus, channel_ref=channel_ref)
    return {sku: _reason_from(infos.get(sku)) for sku in skus}


def _watched_skus() -> set[str]:
    """Tudo que a casa se propõe a vender, mais o que já está bloqueado.

    Não bastam os SKUs com estoque: **produto pausado costuma não ter quant
    nenhum**, e é justamente o tempo dele parado que se quer medir.
    """
    from shopman.offerman.models import Product
    from shopman.stockman.models import Quant

    from shopman.backstage.models import ShelfOutage

    skus = set(
        Quant.objects.filter(position__is_saleable=True)
        .values_list("sku", flat=True)
        .distinct()
    )
    skus.update(Product.objects.values_list("sku", flat=True))
    skus.update(
        ShelfOutage.objects.filter(ended_at__isnull=True).values_list("sku", flat=True)
    )
    return {sku for sku in skus if sku}
