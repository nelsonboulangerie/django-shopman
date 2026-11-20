"""Copia as mensagens para o corpus anonimizado (dono, 20/11/2026, #2851); roda no ``maintenance_worker``.

Antes da limpeza de retenção, para a observação ser copiada antes de vencer. Sem nada que
ligue à pessoa; achado de dado pessoal na conferência do curador pausa a cópia.
"""

import json

from django.core.management.base import BaseCommand

from shopman.storefront.concierge.corpus import copy


class Command(BaseCommand):
    help = "Copia as mensagens dos clientes para o corpus anonimizado de aprendizado conversacional."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(copy(), sort_keys=True))
