"""PTAX de venda do Banco Central: a cotação que converte o gasto com IA em reais.

``quotes_for(days)`` devolve, para cada dia, a cotação a usar, SÓ LENDO (é o lado de leitura
do B.I.): primeiro o que já está gravado (``UsdBrlQuote``); o que falta vem da API pública
do BCB (Olinda, sem chave), numa chamada só para o período, com prazo curto, e não é gravado
ali. Cai a API e não há gravado: vale a última cotação conhecida, marcada como provisória.
Sem nenhuma cotação na casa, o dia fica sem.

``record_quotes(days)`` é quem grava: a cotação final de cada dia (dia passado, ou o próprio
dia depois de publicada), pelo ``record_usd_brl_quotes`` no ``maintenance_worker``. Gravada,
o real de um dia passado não muda mais.

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


def _resolve(missing: list[date]) -> dict[date, tuple[Quote, bool]]:
    """A cotação de cada dia que falta, pela API, e se ela já é a final (para gravar)."""
    today = timezone.localdate()
    try:
        rates = fetch_ptax(missing[0] - timedelta(days=LOOKBACK_DAYS), min(missing[-1], today))
    except Exception:  # noqa: BLE001 — API fora: quem chama decide o que vale
        logger.warning("usd_brl.ptax_unavailable", exc_info=True)
        return {}
    found: dict[date, tuple[Quote, bool]] = {}
    for day in missing:
        known = _last_known(rates, day)
        if known is None:
            continue
        quoted_on, rate = known
        final = day < today or quoted_on == day
        found[day] = (Quote(rate, quoted_on, provisional=not final), final)
    return found


def quotes_for(days: list[date] | set[date]) -> dict[date, Quote]:
    """A cotação de cada dia pedido. Só lê: o gravado, ou a API sem gravar, ou a última conhecida."""
    from shopman.shop.models import UsdBrlQuote

    wanted = sorted(set(days))
    if not wanted:
        return {}
    quotes = {q.date: Quote(q.sell_rate, q.quoted_on) for q in UsdBrlQuote.objects.filter(date__in=wanted)}
    missing = [d for d in wanted if d not in quotes]
    if not missing:
        return quotes
    quotes.update({day: quote for day, (quote, _final) in _resolve(missing).items()})
    still = [d for d in missing if d not in quotes]
    if still:
        latest = UsdBrlQuote.objects.order_by("-date").first()
        if latest is not None:
            for day in still:
                quotes[day] = Quote(latest.sell_rate, latest.quoted_on, provisional=True)
    return quotes


def record_quotes(days: list[date] | set[date]) -> int:
    """Grava a cotação FINAL dos dias que ainda não têm. Devolve quantos gravou."""
    from shopman.shop.models import UsdBrlQuote

    wanted = sorted(set(days))
    stored = set(UsdBrlQuote.objects.filter(date__in=wanted).values_list("date", flat=True))
    missing = [d for d in wanted if d not in stored]
    if not missing:
        return 0
    recorded = 0
    for day, (quote, final) in _resolve(missing).items():
        if final:
            _, created = UsdBrlQuote.objects.get_or_create(
                date=day, defaults={"quoted_on": quote.quoted_on, "sell_rate": quote.rate})
            recorded += int(created)
    return recorded
