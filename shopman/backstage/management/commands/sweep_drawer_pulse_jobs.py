"""O pulso da gaveta que o agente do Balcão nunca respondeu vai ao livro.

O tablet acompanha o pulso só lendo (``GET pos/cash/drawer-pulse/<ref>/``), e a
leitura não grava. Quando o agente responde, a resposta vai ao livro pelo ack.
Este comando cobre o que ele nunca respondeu: grava o veredito do relógio
(``expired`` para a fila vencida, ``uncertain`` para o lease vencido) e a nota
filha da abertura, para o gerente ler no relatório do turno. Roda no
``maintenance_worker``. Ver ``services/drawer_pulse.py``.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Grava no livro a resposta do pulso de gaveta que o agente não respondeu."

    def handle(self, *args, **options):
        from shopman.backstage.services.drawer_pulse import sweep_stale_pulses

        closed = sweep_stale_pulses()
        if closed:
            self.stdout.write(f"{closed} pulso(s) de gaveta sem resposta foram ao livro.")
