"""
Demand Protocol — interface for historical demand and committed orders.

Used by craft.suggest() to calculate recommended production quantities.
Orderman (or other order management systems) implements this.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class DailyDemand:
    """Historical demand data for a single day."""

    date: date
    sold: Decimal
    wasted: Decimal
    soldout_at: time | None = None


@runtime_checkable
class DemandProtocol(Protocol):
    """
    Protocol for querying demand data.

    Se não configurado: craft.suggest() retorna [].
    Se configurado: suggest() usa history + committed para calcular sugestões.
    """

    def history(
        self,
        product_ref: str,
        days: int = 28,
        same_weekday: bool = True,
        *,
        target_date: date,
        exclude_dates: frozenset[date] = frozenset(),
    ) -> list[DailyDemand]:
        """
        Return historical demand for a product.

        Args:
            product_ref: Product reference string
            days: Number of days to look back (default: 28)
            same_weekday: Only include days with the same weekday as
                ``target_date``. É o dia que está sendo PLANEJADO que define o
                recorte, nunca o dia em que o cálculo roda: planejar o sábado
                numa sexta tem de olhar sábados.
            target_date: The day being planned. Obrigatório — sem ele o recorte
                por dia-da-semana não tem âncora.
            exclude_dates: Dias que não contam como amostra (loja fechada,
                feriado). Sem isso um domingo fechado entra na média como um
                domingo fraco e puxa a sugestão para baixo.

        Returns:
            List of DailyDemand entries
        """
        ...

    def committed(self, product_ref: str, target_date: date) -> Decimal:
        """
        Return total committed (ordered/reserved) quantity for a date.

        Args:
            product_ref: Product reference string
            target_date: The target delivery date

        Returns:
            Total committed quantity
        """
        ...
