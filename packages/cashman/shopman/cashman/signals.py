"""Sinais do Cashman.

O pacote anuncia; quem quer efeito escuta. O pacote não sabe o que é SSE.

Quem escuta hoje: o backstage liga ``entry_recorded`` a
``shopman/backstage/handlers.py::on_entry_for_change_request`` (registro em
``backstage/apps.py``), que anuncia o pedido de troco no canal ``alerts``.
``shift_opened`` e ``shift_closed`` ainda não têm ouvinte.

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
