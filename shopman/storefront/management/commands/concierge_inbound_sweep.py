"""Reentrega do que o ManyChat recebeu e não chegou aqui (#2943).

    manage.py concierge_inbound_sweep            # uma rodada (o maintenance_worker roda)
    manage.py concierge_inbound_sweep --limit 5  # menos contatos por rodada

Pergunta ao ManyChat pela última entrada de quem conversa com a Concierge e reingere o que
for mais novo que a nossa. Idempotente: não responde duas vezes.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from shopman.storefront.concierge import inbound_sweep, service


class Command(BaseCommand):
    help = "Reingere a última entrada do ManyChat que não chegou ao webhook (Concierge)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=inbound_sweep.MAX_PER_ROUND)

    def handle(self, *args, **options):
        if service.disabled_reason():
            self.stdout.write("Concierge desligada: nada a conferir.")
            return
        counts = inbound_sweep.sweep(limit=max(1, options["limit"]))
        self.stdout.write(
            f"conferidos {counts['checked']} · reingeridos {counts['reingested']} · "
            f"sem novidade {counts['skipped']} · erros {counts['errors']}"
        )
