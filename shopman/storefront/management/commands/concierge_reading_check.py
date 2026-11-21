"""A Concierge sem modelo vira aviso no Gestor (dono, 19/11/2026); roda no ``maintenance_worker``.

Sem modelo para a leitura de partes (sem conexão, sem chave, freio de gasto ou provedor
falhando), abre um aviso por causa, de cor de erro, no topo do Gestor de pedidos; quando
o modelo volta, ou a causa muda, o aviso velho sai. Nenhuma chamada de modelo.
"""

import json

from django.core.management.base import BaseCommand

from shopman.storefront.concierge.reading_health import sync_alert


class Command(BaseCommand):
    help = "Abre ou resolve o aviso do Gestor de quando a Concierge atende sem modelo."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(sync_alert(), sort_keys=True))
