"""Formatting utilities for the Shopman suite."""

from decimal import Decimal


def format_quantity(value: Decimal | None, decimal_places: int = 2) -> str:
    """
    Format a quantity value.

    Args:
        value: Decimal value to format.
        decimal_places: Number of decimal places (default: 2).

    Returns:
        Formatted string (e.g., "10.50"), or "-" if value is None.
    """
    if value is None:
        return "-"
    return f"{value:.{decimal_places}f}"


def format_local(dt, fmt: str = "%d/%m/%Y %H:%M", empty: str = "-") -> str:
    """Formata um ``datetime`` na hora local da loja (``TIME_ZONE``).

    Com ``USE_TZ=True`` o banco devolve o instante em UTC. ``strftime`` (ou um
    f-string com ``:%H:%M``) formata o que recebeu, sem converter: às 07:40 em
    Brasília a tela dizia 10:40. Toda data que vai para a tela passa por aqui.
    Data ingênua (sem fuso) sai como veio.
    """
    if dt is None:
        return empty
    from django.utils import timezone

    if timezone.is_aware(dt):
        dt = timezone.localtime(dt)
    return dt.strftime(fmt)
