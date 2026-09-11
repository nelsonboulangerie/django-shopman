"""Recuperação limitada de trabalho v2 pela fila existente; nunca replay de texto."""
import json

from django.core.management.base import BaseCommand

from shopman.storefront.concierge.service import config, recover_pending


class Command(BaseCommand):
    help = "Recupera claims/entradas v2; envios desconhecidos permanecem contidos."

    def handle(self, *args, **options):
        if config().get("contract_version") != 2:
            return
        self.stdout.write(json.dumps(recover_pending(), sort_keys=True))
