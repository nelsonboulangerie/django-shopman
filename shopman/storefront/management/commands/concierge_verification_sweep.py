"""Os prazos do "vou verificar" da Concierge (WP-06); roda no ``maintenance_worker``.

Primeiro prazo (``ChannelConfig.confirmation.concierge_verify_nudge_minutes``, 10 por
padrão) sem resposta da equipe: o cartão sobe a urgente no sino do Gestor e o cliente
recebe UM aviso. Segundo prazo (``..._handoff_minutes``, 30): a conversa vai para a
equipe, com a pergunta no cartão. Só com a casa aberta. Nenhuma chamada de modelo.
"""

import json

from django.core.management.base import BaseCommand

from shopman.storefront.concierge.verification import sweep


class Command(BaseCommand):
    help = "Aplica os prazos do vou verificar da Concierge (aviso ao cliente e passagem à equipe)."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(sweep(), sort_keys=True))
