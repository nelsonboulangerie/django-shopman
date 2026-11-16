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


#: Marca da hora dentro do formato de :func:`format_local`. Ocupa o lugar do
#: par hora:minuto do ``strftime``: ``"%d/%m às {clock}"`` vira "16/11 às 12h45".
CLOCK = "{clock}"


def format_clock(value, empty: str = "") -> str:
    """A hora como a casa escreve: "12h45", "9h05", "9h" (dono, 16/11/2026).

    É o ÚNICO formatador de hora lida por gente no servidor: tela, notificação,
    alerta, comprovante e Admin passam por aqui (ou por :func:`format_local` com
    a marca ``{clock}``). Sem zero à esquerda na hora, minuto com dois dígitos,
    hora cheia sem minuto. A regra e o que fica de fora (formato de máquina,
    campo de formulário, carimbo com segundos) estão em
    ``docs/reference/suite-vocabulary.md``, seção "Hora"; a trava é
    ``shopman/backstage/tests/test_formato_de_hora.py``.

    Aceita ``datetime`` (com fuso vira a hora local da loja; ingênuo sai como
    veio), ``time`` e o texto ``"HH:MM"`` dos contratos. O que não dá para ler
    devolve ``empty``: cadastro torto não vira promessa de meia-noite.
    """
    from datetime import datetime, time

    if isinstance(value, datetime):
        from django.utils import timezone

        if timezone.is_aware(value):
            value = timezone.localtime(value)
    elif isinstance(value, str):
        parts = value.strip().split(":")
        try:
            value = time(int(parts[0]), int(parts[1]))
        except (IndexError, TypeError, ValueError):
            return empty
    elif not isinstance(value, time):
        return empty
    return f"{value.hour}h{value.minute:02d}" if value.minute else f"{value.hour}h"


def format_local(dt, fmt: str = "%d/%m/%Y {clock}", empty: str = "-") -> str:
    """Formata um ``datetime`` na hora local da loja (``TIME_ZONE``).

    Com ``USE_TZ=True`` o banco devolve o instante em UTC. ``strftime`` (ou um
    f-string com formato de hora) formata o que recebeu, sem converter: às 7h40
    em Brasília a tela dizia 10h40. Toda data que vai para a tela passa por aqui.
    Data ingênua (sem fuso) sai como veio.

    A hora entra pela marca ``{clock}``, que sai no formato da casa
    (:func:`format_clock`): ``format_local(dt, "%d/%m às {clock}")``.
    """
    if dt is None:
        return empty
    from django.utils import timezone

    if timezone.is_aware(dt):
        dt = timezone.localtime(dt)
    text = dt.strftime(fmt)
    return text.replace(CLOCK, format_clock(dt)) if CLOCK in text else text
