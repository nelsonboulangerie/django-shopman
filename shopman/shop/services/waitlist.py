"""
Fila de espera — quanto da fornada AINDA NÃO ASSADA a loja promete (WP-P2E).

O Stockman sempre soube somar fornada planejada: ``total_promisable`` é
``expected + planned`` para a política ``planned_ok``. O que faltava era a
PERGUNTA. Toda leitura da loja pergunta "e para HOJE?", e fornada de amanhã,
por construção, não conta para hoje — ``quants_eligible_for`` corta
``target_date > target`` e ``_planned_supply_for_target`` exige ``target >
today``. Resultado: o balde ``planned`` chega zerado em toda leitura de
cliente, o item lê "Esgotado" e não há fila em que entrar, mesmo com a
fornada de amanhã já planejada.

Este módulo é a pergunta certa, num lugar só: até que DIA de fornada
planejada este canal promete. As leituras (sacola, cardápio, PDP) passam
:func:`promise_horizon` como ``target_date``; a reserva passa
:func:`reserve_target_date`, que é a data da fornada de verdade — o hold
precisa ancorar no lote certo para que a sacola diga "Previsto para
<dia>" sem mentir.

Desligado (``waitlist.enabled=False``, o default) tudo devolve hoje: o
comportamento é exatamente o de sempre.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

logger = logging.getLogger(__name__)


def config(channel_ref: str | None = None):
    """Resolve o aspecto ``waitlist`` na cascata canal ← loja ← hardcoded."""
    from shopman.shop.config import ChannelConfig

    try:
        if channel_ref:
            return ChannelConfig.for_channel(channel_ref).waitlist
        return ChannelConfig().waitlist
    except Exception:
        logger.debug("waitlist.config degraded; using hardcoded defaults", exc_info=True)
        return ChannelConfig().waitlist


def is_enabled(channel_ref: str | None = None) -> bool:
    cfg = config(channel_ref)
    return bool(cfg.enabled and cfg.horizon_days > 0)


def promise_horizon(channel_ref: str | None = None) -> date:
    """Última data de fornada planejada que este canal promete.

    Fila desligada devolve HOJE — que é o que toda leitura já usava, então
    passar isto adiante não muda nada até alguém ligar a fila.
    """
    from django.utils import timezone

    today = timezone.localdate()
    cfg = config(channel_ref)
    if not (cfg.enabled and cfg.horizon_days > 0):
        return today
    return today + timedelta(days=cfg.horizon_days)


def next_batch_date(sku: str, *, channel_ref: str | None = None) -> date | None:
    """Data da próxima fornada PLANEJADA deste SKU dentro do horizonte.

    ``None`` quando não há fornada planejada alcançável — que é o caso
    honesto de "esgotou mesmo", e o chamador deve recusar.
    """
    if not sku:
        return None
    horizon = promise_horizon(channel_ref)
    from django.utils import timezone

    today = timezone.localdate()
    if horizon <= today:
        return None
    try:
        from shopman.stockman.models import Quant
    except Exception:
        logger.debug("waitlist.next_batch_date degraded; returning None", exc_info=True)
        return None

    return (
        Quant.objects.filter(
            sku=sku,
            _quantity__gt=0,
            target_date__gt=today,
            target_date__lte=horizon,
        )
        .order_by("target_date")
        .values_list("target_date", flat=True)
        .first()
    )


def reserve_target_date(
    sku: str,
    qty: Decimal,
    *,
    channel_ref: str | None = None,
) -> date | None:
    """Data que a reserva deve carregar para entrar na fila deste SKU.

    ``None`` = nada a fazer, siga com o comportamento de hoje. Só devolve a
    data da fornada quando o que existe para hoje NÃO cobre o pedido: a
    pronta-entrega continua sendo servida primeiro, e a fila só é acionada
    quando ela acaba (FCFS — quem chega antes leva o que já existe).
    """
    if not is_enabled(channel_ref) or not sku:
        return None
    try:
        from shopman.stockman.services.availability import availability_for_sku

        from shopman.shop.adapters import stock as stock_adapter

        scope = stock_adapter.get_channel_scope(channel_ref) if channel_ref else {}
        info = availability_for_sku(
            sku,
            safety_margin=int(scope.get("safety_margin") or 0),
            allowed_positions=scope.get("allowed_positions"),
            excluded_positions=scope.get("excluded_positions"),
            expiry_margin_days=int(scope.get("expiry_margin_days") or 0),
            include_nonconforming=bool(scope.get("sells_nonconforming", True)),
        )
    except Exception:
        logger.debug("waitlist.reserve_target_date degraded; returning None", exc_info=True)
        return None

    if info.get("is_paused"):
        return None
    promisable = Decimal(str(info.get("total_promisable") or 0))
    if promisable >= Decimal(str(qty)):
        return None
    return next_batch_date(sku, channel_ref=channel_ref)
