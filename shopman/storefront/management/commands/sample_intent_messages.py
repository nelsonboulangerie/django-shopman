"""Sorteia mensagens de clientes para o gabarito de intenções (INTENT-PILOT-PLAN).

Cria uma ``MessageIntentSample`` "a rotular" por mensagem sorteada: só entrada
de cliente com texto, nunca uma que já esteja na amostra. Não copia texto — a
amostra aponta para a mensagem, e a tela de rotulagem mostra a versão redigida.
Rodar de novo acrescenta mais; nada é apagado.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Sorteia mensagens de clientes para rotular no Admin (Clientes → Mensagens para rotular)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200, help="Quantas sortear (default 200).")
        parser.add_argument("--days", type=int, default=0, help="Só as dos últimos N dias (default: todas).")
        parser.add_argument("--min-chars", type=int, default=3, help="Ignora mensagens mais curtas (default 3).")

    def handle(self, *args, **options):
        from shopman.shop.models import ConversationMessage
        from shopman.storefront.models import MessageIntentSample

        if options["limit"] <= 0:
            raise CommandError("--limit precisa ser positivo.")
        candidates = (
            ConversationMessage.objects.filter(kind=ConversationMessage.Kind.INBOUND)
            .exclude(text="")
            .filter(intent_sample__isnull=True)
        )
        if options["days"]:
            candidates = candidates.filter(created_at__gte=timezone.now() - timedelta(days=options["days"]))
        picked = [
            message_id
            for message_id, text in candidates.order_by("?").values_list("id", "text")[: options["limit"] * 3]
            if len((text or "").strip()) >= options["min_chars"]
        ][: options["limit"]]
        MessageIntentSample.objects.bulk_create([MessageIntentSample(message_id=pk) for pk in picked])
        pending = MessageIntentSample.objects.filter(status="pending").count()
        self.stdout.write(self.style.SUCCESS(
            f"{len(picked)} mensagem(ns) sorteada(s); {pending} esperando rótulo. "
            "Rotule em Admin → Clientes → Mensagens para rotular."
        ))
        if not picked:
            self.stdout.write(self.style.WARNING(
                "Nenhuma mensagem nova: o concierge ainda não recebeu texto de cliente neste ambiente, "
                "ou todas já estão na amostra."
            ))
