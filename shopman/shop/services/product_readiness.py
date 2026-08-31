"""A que horas cada SKU fica PRONTO — a promessa por trás do horário combinado.

Existe uma pergunta só, e três telas a fazem: a loja no checkout, o PDV ao
agendar, e qualquer coisa que venha depois. *"Se tem baguete de tradição no
pedido, dá para prometer as 9h?"* A resposta não pode depender de quem pergunta.

## Duas fontes, e por que são duas

- **Declarada** — ``Product.metadata["ready_from"]`` (``"HH:MM"``). A casa SABE
  que a baguete de tradição sai depois do meio-dia; isto é a porta para dizer
  isso. Irmã de ``made_to_order`` e ``allows_next_day_sale``: metadata do
  Product, zero migração no Core.
- **Observada** — a mediana da hora de término das WorkOrders recentes daquele
  SKU. Mede o que a casa REALMENTE fez, e cobre o produto que ninguém declarou.

Quando as duas existem, **vence a mais tarde**. A declaração é piso, não teto: um
pão declarado para as 10h que há um mês sai às 11h30 não pode ser prometido para
as 10h só porque o cadastro diz isso — quem paga a diferença é o cliente na
porta. E produto sem histórico nenhum fica com a declaração, que é justamente o
caso que o histórico sozinho deixava passar.

## Por que aqui, e não no storefront

Isto nasceu dentro de ``storefront/services/pickup_slots.py``, e ficou preso lá:
**backstage não pode importar storefront**. Enquanto a resposta morasse na loja,
o PDV não tinha como consultá-la — e não consultava, o que fazia do balcão o
caminho mais curto para prometer um horário impossível. Aqui os dois alcançam.

Este módulo não sabe o que é um "slot". Ele responde a hora; quem casa isso com a
grade de horários é ``fulfillment_window``.
"""

from __future__ import annotations

import logging
from datetime import date, time, timedelta
from statistics import median

logger = logging.getLogger(__name__)

#: De quanto em quanto tempo a hora observada é arredondada PARA CIMA. Prometer
#: 11:07 é precisão que a padaria não tem; 11:30 é promessa que ela cumpre.
DEFAULT_ROUNDING_MINUTES = 30

#: Janela de histórico de produção considerada.
DEFAULT_HISTORY_DAYS = 30


def _local_date() -> date:
    try:
        from django.utils import timezone

        return timezone.localtime().date()
    except Exception:
        logger.debug("product_readiness: could not read Django local date", exc_info=True)
        return date.today()


def parse_clock(raw) -> time | None:
    """``"HH:MM"`` → ``time``, ou ``None`` quando não dá para ler.

    Aceita ``"09:00"``, ``"9:00"`` e ``"09:00:00"``. Lixo devolve ``None`` — e
    ``None`` aqui significa "não declarado", nunca "meia-noite": um cadastro
    torto não pode virar uma promessa de madrugada.
    """
    if isinstance(raw, time):
        return raw.replace(second=0, microsecond=0)
    text = str(raw or "").strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) < 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except (TypeError, ValueError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return time(hour, minute)


def format_clock(value: time | None) -> str:
    return value.strftime("%H:%M") if isinstance(value, time) else ""


def declared_ready_times(skus: list[str]) -> dict[str, time]:
    """O que a CASA declarou, por SKU — ``Product.metadata["ready_from"]``.

    SKU sem declaração (ou com declaração ilegível) simplesmente não aparece no
    resultado: ausência é ausência, e quem decide o que fazer com ela é o
    chamador.
    """
    if not skus:
        return {}
    try:
        from shopman.offerman.models import Product

        rows = Product.objects.filter(sku__in=list(skus)).values_list("sku", "metadata")
    except Exception:
        logger.warning("product_readiness: declared lookup failed skus=%s", skus, exc_info=True)
        return {}

    out: dict[str, time] = {}
    for sku, metadata in rows:
        declared = parse_clock((metadata or {}).get("ready_from"))
        if declared is not None:
            out[str(sku)] = declared
    return out


def observed_ready_times(
    skus: list[str],
    *,
    history_days: int = DEFAULT_HISTORY_DAYS,
    rounding_minutes: int = DEFAULT_ROUNDING_MINUTES,
) -> dict[str, time]:
    """O que a casa REALMENTE fez — mediana do término das WorkOrders recentes.

    Arredonda para cima na granularidade de ``rounding_minutes``. SKU sem fornada
    na janela não aparece.
    """
    if not skus:
        return {}
    try:
        from shopman.shop.adapters import get_adapter

        production = get_adapter("production")
    except Exception:
        logger.debug("product_readiness: no production adapter", exc_info=True)
        return {}

    cutoff = _local_date() - timedelta(days=max(0, history_days))
    try:
        work_orders = production.get_finished_work_orders(list(skus), cutoff)
    except Exception:
        logger.warning("product_readiness: production history failed", exc_info=True)
        return {}

    minutes_by_sku: dict[str, list[float]] = {}
    for sku, finished_at in work_orders:
        local_dt = _localize(finished_at)
        minutes_by_sku.setdefault(str(sku), []).append(local_dt.hour * 60 + local_dt.minute)

    out: dict[str, time] = {}
    for sku, minutes_list in minutes_by_sku.items():
        if not minutes_list:
            continue
        rounded = _round_up_minutes(median(minutes_list), rounding_minutes)
        out[sku] = time(min(int(rounded // 60), 23), int(rounded % 60))
    return out


def _localize(value):
    if hasattr(value, "astimezone"):
        try:
            from django.utils import timezone as tz

            return value.astimezone(tz.get_current_timezone())
        except Exception:
            logger.debug("product_readiness: could not localize finish time", exc_info=True)
    return value


def _round_up_minutes(minutes: float, granularity: int) -> int:
    import math

    if granularity <= 0:
        return int(minutes)
    return int(math.ceil(minutes / granularity) * granularity)


def ready_times_for(
    skus: list[str],
    *,
    history_days: int = DEFAULT_HISTORY_DAYS,
    rounding_minutes: int = DEFAULT_ROUNDING_MINUTES,
) -> dict[str, time]:
    """A hora de prontidão que VALE, por SKU — declarada e observada reunidas.

    As duas juntas, a mais TARDE vencendo. Ver o cabeçalho do módulo para o
    porquê da direção.
    """
    unique = sorted({str(sku) for sku in (skus or []) if sku})
    if not unique:
        return {}
    declared = declared_ready_times(unique)
    observed = observed_ready_times(
        unique, history_days=history_days, rounding_minutes=rounding_minutes
    )
    out: dict[str, time] = {}
    for sku in unique:
        candidates = [t for t in (declared.get(sku), observed.get(sku)) if t is not None]
        if candidates:
            out[sku] = max(candidates)
    return out


def bottleneck(skus: list[str], **kwargs) -> tuple[time | None, str]:
    """O SKU que segura o pedido, e a que horas ele libera.

    ``(None, "")`` quando nada no carrinho tem hora conhecida — e aí quem decide
    o que fazer com o silêncio é o chamador. Aqui não se inventa restrição nem se
    dá passe livre.
    """
    times = ready_times_for(skus, **kwargs)
    if not times:
        return None, ""
    sku = max(times, key=lambda key: times[key])
    return times[sku], sku


def product_names(skus: list[str]) -> dict[str, str]:
    """``{sku: nome}`` para o motivo poder falar em português de balcão.

    "A baguete de tradição sai às 12:00" responde a pergunta que o operador vai
    ouvir; "BAG-TRAD sai às 12:00" faz ele abrir o Admin com o cliente na frente.
    """
    if not skus:
        return {}
    try:
        from shopman.offerman.models import Product

        return {
            str(sku): str(name or sku)
            for sku, name in Product.objects.filter(sku__in=list(skus)).values_list("sku", "name")
        }
    except Exception:
        logger.warning("product_readiness: name lookup failed skus=%s", skus, exc_info=True)
        return {}
