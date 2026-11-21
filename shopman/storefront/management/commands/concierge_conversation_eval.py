"""Placar de conversa sobre as conversas reais: o cliente foi atendido, turno a turno.

    manage.py concierge_conversation_eval                  # últimos 7 dias, canal whatsapp
    manage.py concierge_conversation_eval --days 1 --show 60
    manage.py concierge_conversation_eval --conversation 42

Só leitura, sem modelo, sem rede. Cada turno sai como útil, sem saída, sem lastro ou
silêncio, com a coluna "ManyChat AI faria" (perfil de capacidade, levantamento de 21/11).
O texto do cliente e da casa sai redigido (documento, telefone, e-mail, endereço omitidos).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from shopman.storefront.concierge import conversation_eval


class Command(BaseCommand):
    help = "Placar de conversa: as conversas reais, turno a turno, e o que a IA do ManyChat faria."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7)
        parser.add_argument("--channel", default="whatsapp")
        parser.add_argument("--conversation", type=int, default=None, help="Só esta conversa (id).")
        parser.add_argument("--show", type=int, default=40, help="Quantos turnos a consertar mostrar.")

    def handle(self, *args, **options):
        turns = conversation_eval.read_turns(
            days=options["days"], channel_ref=options["channel"], conversation_id=options["conversation"]
        )
        self.stdout.write(conversation_eval.render(turns, show=options["show"]))
