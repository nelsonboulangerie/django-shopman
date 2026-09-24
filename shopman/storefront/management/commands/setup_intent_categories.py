"""Cria o vocabulário de intenções do piloto (INTENT-PILOT-PLAN). Idempotente.

Invólucro de ``intent_pilot.ensure_categories`` — o ciclo automático já faz
isto sozinho; o comando existe para rodar à mão num ambiente novo. Só cria o
que falta pela referência e nunca sobrescreve o que alguém mudou no Admin
(Clientes → Intenções).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Cria as intenções padrão do piloto de mensageria (só as que faltam; nunca sobrescreve)."

    def handle(self, *args, **options):
        from shopman.storefront.concierge.intent_pilot import DEFAULT_INTENTS, ensure_categories

        created = ensure_categories()
        self.stdout.write(self.style.SUCCESS(
            f"{created} intenção(ões) criada(s); {len(DEFAULT_INTENTS) - created} já existiam. "
            "Edite em Admin → Clientes → Intenções."
        ))
