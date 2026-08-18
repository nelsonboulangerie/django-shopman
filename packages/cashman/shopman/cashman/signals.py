"""Sinais do Cashman.

O pacote anuncia; quem quer efeito (SSE, alerta, B.I. incremental) escuta. O
pacote não sabe o que é SSE.

    from shopman.cashman.signals import entry_recorded

    @receiver(entry_recorded)
    def on_entry(sender, entry, **kwargs): ...

Sinais:
    shift_opened   — kwargs: shift
    shift_closed   — kwargs: shift, count (o lançamento de contagem)
    entry_recorded — kwargs: entry (todo lançamento, inclusive float_in e count)
"""

from django.dispatch import Signal

shift_opened = Signal()
shift_closed = Signal()
entry_recorded = Signal()
