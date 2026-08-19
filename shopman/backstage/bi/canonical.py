"""A camada canônica do B.I.: uma venda é uma venda, venha de onde vier (P2).

Toda leitura de venda do B.I. passa por aqui. Cada fonte tem um adaptador em
``bi/sources/`` que traduz o seu formato para ``CanonicalSale``/``CanonicalSaleLine``;
este módulo **compõe** as fontes numa janela e aplica, num lugar só, a regra
que antes estava copiada em cinco leitores:

**O dia nativo vence.** Num dia em que o Shopman registrou venda, o histórico
externo não entra — nunca se somam, porque a mesma venda contaria duas vezes.
Um pedido de teste num dia antigo apaga o histórico daquele dia, e é assim de
propósito; o que mudou é que agora isso é **declarado** (``source_conflicts``)
em vez de silencioso: dia com poucos pedidos nativos e muito histórico
descartado aparece na resposta, para o gestor ver que a régua mudou ali.

Nada aqui é tabela nem cache: é leitura composta sobre as fontes, com o
mesmo custo de antes. Materializar é assunto da camada de leitura (P3), e
quando acontecer, o contrato de quem lê não muda.

Ausência não é zero: dia sem venda registrada não aparece; forma de pagamento
que o vocabulário não reconhece sai com o texto cru e ``payment_known=False``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

#: Guarda da fusão: dia nativo com MENOS que isto de pedidos…
CONFLICT_MAX_NATIVE = 5
#: …que descartou MAIS que isto de vendas históricas vira aviso declarado.
CONFLICT_MIN_HISTORICAL = 20


@dataclass(frozen=True, slots=True)
class CanonicalPayment:
    method: str  # chave canônica (cash, pix, credit…) ou raw:<texto> quando desconhecida
    label: str
    amount_q: int
    pending: bool  # cobrança na entrega ainda não recebida (só o nativo sabe)


@dataclass(frozen=True, slots=True)
class CanonicalSale:
    source: str  # "shopman" | "yooga" | "seed" | …
    key: int  # pk na tabela de origem; junta com as linhas
    ref: str  # identidade legível: "shopman:<ref>" | "yooga:<external_id>"
    occurred_at: datetime  # local, aware
    day: date  # local
    channel_key: str  # channel_ref nativo | "<source> · loja|delivery"
    is_delivery: bool
    total_q: int
    payments: tuple[CanonicalPayment, ...]
    payment_known: bool  # a forma é conhecida (nativo: sempre que há método; histórico: vocabulário casou)
    is_cash: bool  # houve dinheiro em espécie (qualquer parcela)
    change_q: int | None  # troco devolvido, medido; None = não medido ou a fonte não tem (histórico)


@dataclass(frozen=True, slots=True)
class CanonicalSaleLine:
    source: str
    sale_key: int
    product_ref: str  # SKU do catálogo (nativo, ou histórico via de-para confirmado); "" se não há
    external_sku: str  # SKU como a fonte escreveu (histórico); "" no nativo
    name: str
    category: str  # crua, como a fonte escreveu; "" no nativo
    qty: Decimal
    line_total_q: int

    @property
    def product_key(self) -> str:
        """A chave que agrega o produto no ranking e nas dimensões.

        Catálogo primeiro (junta Yooga e nativo quando o de-para existe), SKU da
        fonte depois, e por último o nome — 7% do export não tem SKU e não pode
        sumir do ranking.
        """
        return self.product_ref or self.external_sku or f"nome:{self.name}"


@dataclass(frozen=True, slots=True)
class SourceConflict:
    """Um dia em que o nativo venceu e apagou histórico relevante — declarado."""

    day: date
    native_orders: int
    historical_dropped: int
    source: str  # a fonte histórica descartada


@dataclass(frozen=True)
class SalesWindow:
    """As vendas de uma janela, já conciliadas, e o que a conciliação fez."""

    date_from: date
    date_to: date
    sales: tuple[CanonicalSale, ...]
    native_days: frozenset[date]
    historical_days: dict[date, str]  # dia preenchido pelo histórico → fonte
    source_conflicts: tuple[SourceConflict, ...]
    cancelled_native: int  # pedidos nativos cancelados/devolvidos: contados à parte, fora da venda
    _lines: list[CanonicalSaleLine] | None = field(default=None, repr=False, compare=False)

    @property
    def sources(self) -> tuple[str, ...]:
        """As fontes presentes, na ordem em que aparecem (nativo primeiro)."""
        seen: list[str] = []
        for sale in self.sales:
            if sale.source not in seen:
                seen.append(sale.source)
        return tuple(seen)

    def lines(self) -> list[CanonicalSaleLine]:
        """As linhas das vendas conciliadas. Carrega uma vez, só quando alguém pede.

        Classificar 380 mil linhas para responder "faturamento por hora" seria
        trabalho jogado fora; o ranking e o modo de consumo pedem, o resto não.
        """
        if self._lines is None:
            from .sources import historical, orderman

            window = local_window(self.date_from, self.date_to)
            lines = orderman.read_lines(window)
            lines.extend(historical.read_lines(window, skip_days=self.native_days))
            object.__setattr__(self, "_lines", lines)
        return self._lines

    def sales_by_key(self) -> dict[tuple[str, int], CanonicalSale]:
        return {(sale.source, sale.key): sale for sale in self.sales}


def local_window(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    """[início do dia, início do dia seguinte) em hora local — o recorte de toda leitura."""
    tz = timezone.get_current_timezone()
    return (
        datetime.combine(date_from, time.min, tzinfo=tz),
        datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=tz),
    )


def read_sales(date_from: date, date_to: date) -> SalesWindow:
    """Compõe as fontes na janela: nativo, depois histórico onde o nativo não vendeu."""
    from .sources import historical, orderman

    window = local_window(date_from, date_to)
    native, cancelled = orderman.read_sales(window)
    native_days = frozenset(sale.day for sale in native)
    native_per_day: dict[date, int] = {}
    for sale in native:
        native_per_day[sale.day] = native_per_day.get(sale.day, 0) + 1

    kept: list[CanonicalSale] = list(native)
    historical_days: dict[date, str] = {}
    dropped: dict[date, tuple[int, str]] = {}
    for sale in historical.read_sales(window):
        if sale.day in native_days:
            count, source = dropped.get(sale.day, (0, sale.source))
            dropped[sale.day] = (count + 1, source)
            continue
        historical_days.setdefault(sale.day, sale.source)
        kept.append(sale)

    conflicts = tuple(
        SourceConflict(day=day, native_orders=native_per_day[day], historical_dropped=count, source=source)
        for day, (count, source) in sorted(dropped.items())
        if native_per_day[day] < CONFLICT_MAX_NATIVE and count > CONFLICT_MIN_HISTORICAL
    )
    return SalesWindow(
        date_from=date_from,
        date_to=date_to,
        sales=tuple(kept),
        native_days=native_days,
        historical_days=historical_days,
        source_conflicts=conflicts,
        cancelled_native=cancelled,
    )


def iter_days(date_from: date, date_to: date) -> Iterator[date]:
    day = date_from
    while day <= date_to:
        yield day
        day += timedelta(days=1)
