"""Os prazos do motor do framework conversacional (#3298); roda no ``maintenance_worker``.

Com as classes da Shop desligadas (``Shop.conversational_live_*``), ou enquanto o aviso de
prazo (``wait.*``) não tem frase da Nice aprovada, não faz nada. Ligado, cada compromisso do
motor com prazo vencido avisa o cliente UMA vez, pelo envio da conversa. Nenhuma chamada de modelo.
"""

import json

from django.core.management.base import BaseCommand

from shopman.storefront.concierge.turn_framework import tick


class Command(BaseCommand):
    help = "Aplica os prazos vencidos do motor da Concierge (aviso ao cliente), atrás das chaves da Shop."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(tick(), sort_keys=True))
