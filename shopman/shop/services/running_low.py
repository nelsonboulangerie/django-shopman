"""Quando um item está ACABANDO — a regra única do balcão e da Cozinha (DEV-2026-077).

Decisão do dono (23/11/2026): o saldo aparece no tile do PDV só quando o item
está acabando, e "acabando" é uma porcentagem configurável por SKU, mostrada em
unidades. Porcentagem, e não um número fixo, porque há pães de que a casa faz
poucas unidades: "5 ou menos" de um pão de 6 é quase sempre; de um pão de 30,
é a última bandeja.

A mesma régua diz o "Últimas N un." do card da Cozinha. Antes ele lia o
``StockAlert.min_quantity`` do Stockman, que continua existindo, mas só para o
alerta de REPOSIÇÃO do painel: um campo, um significado.

O "Últimas unidades" da LOJA (``ChannelConfig.stock.low_stock_threshold``) é
outra régua, de propósito: é por canal, fala ao cliente e dispara a campanha do
Marketing. Não passa por aqui.

**A porcentagem.** ``Product.metadata["running_low_percent"]`` (0 a 100), e na
ausência o padrão da loja em ``Shop.defaults["running_low"]["percent"]``
(padrão do código: 20). ``0`` = nunca avisa; ``100`` = sempre mostra.

**A referência (o 100%).** O que o dia teve para vender: o que ainda resta MAIS
o que já saiu hoje (venda e perda, descontada a devolução). Para a prateleira
isso é exatamente o "abertura + entradas do dia" do ``shelf_history``
(``abertura + entradas − saídas = saldo``), e tem uma vantagem que conta: a
referência sai do MESMO número que o tile mostra. O ``units_left`` do PDV conta
o quant datado de hoje (a fornada de hoje ainda não finalizada) como pronto, e
o ``shelf_history`` não conta; medir um contra o outro daria "acabando" a um
pão de que ainda vêm 18. Somando as saídas ao próprio saldo, numerador e
denominador olham o mesmo estoque.

**O arredondamento.** O limiar em unidades é ``ceil(porcentagem × referência)``:
20% de 6 pães é 1,2, que vira 2; 20% de 4 é 0,8, que vira 1. Arredondar para
baixo apagaria o aviso justamente do pão de poucas unidades, que é o caso que
motivou a regra. O item acaba quando ``saldo ≤ limiar``.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, time

logger = logging.getLogger(__name__)

BLOCK = "running_low"
METADATA_KEY = "running_low_percent"
DEFAULT_PERCENT = 20


def coerce_percent(value) -> int | None:
    """Porcentagem inteira de 0 a 100, ou ``None`` quando ilegível ou fora da faixa."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, float):
        if not value.is_integer():
            return None
        value = int(value)
    try:
        coerced = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return coerced if 0 <= coerced <= 100 else None


def shop_default_percent() -> int:
    """O padrão da loja; ilegível ou ausente cai no padrão do código, nunca desliga."""
    from shopman.shop.models import Shop

    shop = Shop.load()
    defaults = getattr(shop, "defaults", None) if shop else None
    block = defaults.get(BLOCK) if isinstance(defaults, dict) else None
    if isinstance(block, dict):
        value = coerce_percent(block.get("percent"))
        if value is not None:
            return value
        if "percent" in block:
            logger.warning("Shop.defaults.running_low.percent ilegível: %r", block.get("percent"))
    return DEFAULT_PERCENT


def product_percent(metadata) -> int | None:
    """A porcentagem PRÓPRIA do produto; ``None`` = usa o padrão da loja."""
    if not isinstance(metadata, Mapping):
        return None
    return coerce_percent(metadata.get(METADATA_KEY))


def threshold_units(percent: int, reference: int) -> int:
    """``ceil(percent% × reference)``, em inteiros (sem ponto flutuante)."""
    if percent <= 0 or reference <= 0:
        return 0
    return -(-percent * reference // 100)


def is_running_low(left: int, *, percent: int, reference: int) -> bool:
    """Acabando = ainda há (``left > 0``) e o saldo chegou ao limiar."""
    if left <= 0 or percent <= 0:
        return False
    return left <= threshold_units(percent, max(reference, left))


def percents_for(skus) -> dict[str, int]:
    """A porcentagem efetiva de cada SKU: a própria, ou o padrão da loja."""
    from shopman.offerman.models import Product

    skus = [sku for sku in dict.fromkeys(skus) if sku]
    if not skus:
        return {}
    default = shop_default_percent()
    own = {
        sku: product_percent(metadata)
        for sku, metadata in Product.objects.filter(sku__in=skus).values_list("sku", "metadata")
    }
    return {sku: own.get(sku) if own.get(sku) is not None else default for sku in skus}


def left_today(skus) -> dict[str, int]:
    """O que já saiu hoje de cada SKU: venda e perda, menos a devolução. Nunca negativo."""
    from django.db.models import Sum
    from django.utils import timezone
    from shopman.stockman import Move

    skus = [sku for sku in dict.fromkeys(skus) if sku]
    if not skus:
        return {}
    tz = timezone.get_current_timezone()
    start = datetime.combine(timezone.localdate(), time.min, tzinfo=tz)
    rows = (
        Move.objects.filter(
            quant__sku__in=skus,
            timestamp__gte=start,
            kind__in=(Move.Kind.SELL, Move.Kind.WASTE, Move.Kind.RETURN),
        )
        .values("quant__sku")
        .annotate(total=Sum("delta"))
    )
    out: dict[str, int] = {}
    for row in rows:
        gone = -(row["total"] or 0)
        if gone > 0:
            out[row["quant__sku"]] = int(gone)
    return out


def running_low_skus(left_by_sku: Mapping[str, int]) -> set[str]:
    """Os SKUs acabando, dado o saldo que a tela mostra de cada um.

    ``left_by_sku`` é o número que a tela vai mostrar (o ``units_left`` do PDV,
    o saldo físico da Cozinha): a referência é ele mais o que saiu hoje, então
    cada tela mede o próprio número contra o próprio dia. Silencioso quando o
    estoque não responde: o selo nunca derruba a tela.
    """
    candidates = {sku: int(left) for sku, left in left_by_sku.items() if sku and left and left > 0}
    if not candidates:
        return set()
    try:
        percents = percents_for(candidates)
        gone = left_today(candidates)
    except Exception:
        logger.exception("running_low_lookup_failed")
        return set()
    return {
        sku
        for sku, left in candidates.items()
        if is_running_low(left, percent=percents.get(sku, DEFAULT_PERCENT), reference=left + gone.get(sku, 0))
    }
