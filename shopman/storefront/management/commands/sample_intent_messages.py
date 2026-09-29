"""Sorteia mensagens para o gabarito de intenções (INTENT-PILOT-PLAN), à mão.

O ciclo automático (``run_intent_pilot``) já sorteia sozinho, com teto por dia;
este comando existe para encher a fila de uma vez. Só entrada com texto, nunca
uma que já esteja na amostra, e sem copiar texto: a amostra aponta para a
mensagem, e a tela de conferência mostra a versão redigida.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Sorteia mensagens de entrada para conferir no Admin (Clientes → Mensagens para rotular)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200, help="Quantas sortear (default 200).")
        parser.add_argument("--days", type=int, default=0, help="Só as dos últimos N dias (default: todas).")
        parser.add_argument("--min-chars", type=int, default=3, help="Ignora mensagens mais curtas (default 3).")

    def handle(self, *args, **options):
        from shopman.storefront.concierge.intent_pilot import sample_messages
        from shopman.storefront.models import MessageIntentSample, SampleStatus

        if options["limit"] <= 0:
            raise CommandError("--limit precisa ser positivo.")
        picked = sample_messages(limit=options["limit"], days=options["days"], min_chars=options["min_chars"])
        waiting = MessageIntentSample.objects.filter(
            status__in=[SampleStatus.PENDING, SampleStatus.PROPOSED]
        ).count()
        self.stdout.write(self.style.SUCCESS(
            f"{picked} mensagem(ns) sorteada(s); {waiting} esperando conferência em "
            "Admin → Clientes → Mensagens para rotular."
        ))
        if not picked:
            self.stdout.write(self.style.WARNING(
                "Nenhuma mensagem nova: o concierge não recebeu texto neste ambiente (atendimento ou "
                "observação), ou todas já estão na amostra."
            ))
