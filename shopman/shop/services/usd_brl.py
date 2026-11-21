"""PTAX de venda do Banco Central: a cotação que converte o gasto com IA em reais.

``quotes_for(days)`` devolve, para cada dia, a cotação a usar. Primeiro o que já está
gravado (``UsdBrlQuote``); o que falta vem da API pública do BCB (Olinda, sem chave),
numa chamada só para o período, com prazo curto. Cai a API e não há gravado: vale a última
cotação conhecida, marcada como provisória, para o número em reais nunca sair sem a
cotação ao lado dizendo de onde veio. Sem nenhuma cotação na casa, o dia fica sem.

Dinheiro de IA segue em micro-dólar inteiro; a conversão é ``brl_micros``: micro-real
inteiro, arredondado uma vez só, no fim.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

import requests
from django.utils import timezone

logger = logging.getLogger(__name__)

PTAX_URL = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
)
TIMEOUT_S = 4.0
#: Quantos dias antes do primeiro pedir, para achar o último dia útil (carnaval: 4 dias).
LOOKBACK_DAYS = 7


@dataclass(frozen=True)
class Quote:
    rate: Decimal
    quoted_on: date
    #: A cotação ainda pode mudar (a de hoje antes de publicada, ou a última conhecida
    #: porque a API caiu). A tela diz.
    provisional: bool = False


def brl_micros(usd_micros: int, rate: Decimal) -> int:
    """Micro-dólar em micro-real, arredondado uma vez."""
    return int((Decimal(usd_micros) * rate).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def fetch_ptax(start: date, end: date) -> dict[date, Decimal]:
    """A PTAX de venda de cada dia útil entre ``start`` e ``end``. Levanta se a API cair."""
    response = requests.get(
        PTAX_URL,
        params={
            "@dataInicial": f"'{start:%m-%d-%Y}'",
            "@dataFinalCotacao": f"'{end:%m-%d-%Y}'",
            "$format": "json",
            "$select": "cotacaoVenda,dataHoraCotacao",
        },
        timeout=TIMEOUT_S,
    )
    response.raise_for_status()
    rates: dict[date, Decimal] = {}
    for row in response.json().get("value") or []:
        day = datetime.fromisoformat(str(row["dataHoraCotacao"])[:10]).date()
        rates[day] = Decimal(str(row["cotacaoVenda"])).quantize(Decimal("0.0001"))
    return rates


def _last_known(rates: dict[date, Decimal], day: date) -> tuple[date, Decimal] | None:
    known = [d for d in rates if d <= day]
    if not known:
        return None
    quoted_on = max(known)
    return quoted_on, rates[quoted_on]


def quotes_for(days: list[date] | set[date]) -> dict[date, Quote]:
    """A cotação de cada dia pedido. Grava a final; devolve a provisória sem gravar."""
    from shopman.shop.models import UsdBrlQuote

    wanted = sorted(set(days))
    if not wanted:
        return {}
    stored = {q.date: q for q in UsdBrlQuote.objects.filter(date__in=wanted)}
    quotes = {d: Quote(q.sell_rate, q.quoted_on) for d, q in stored.items()}
    missing = [d for d in wanted if d not in quotes]
    if not missing:
        return quotes

    today = timezone.localdate()
    try:
        rates = fetch_ptax(missing[0] - timedelta(days=LOOKBACK_DAYS), min(missing[-1], today))
    except Exception:  # noqa: BLE001 — API fora: vale a última conhecida, provisória
        logger.warning("usd_brl.ptax_unavailable", exc_info=True)
        rates = {}

    for day in missing:
        found = _last_known(rates, day)
        if found is None:
            continue
        quoted_on, rate = found
        final = day < today or quoted_on == day
        if final:
            UsdBrlQuote.objects.get_or_create(date=day, defaults={"quoted_on": quoted_on, "sell_rate": rate})
        quotes[day] = Quote(rate, quoted_on, provisional=not final)

    still = [d for d in missing if d not in quotes]
    if still:
        latest = UsdBrlQuote.objects.order_by("-date").first()
        if latest is not None:
            for day in still:
                quotes[day] = Quote(latest.sell_rate, latest.quoted_on, provisional=True)
    return quotes
