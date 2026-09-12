"""Recuperação limitada pela fila canônica; nunca repete efeito incerto."""

import json

from django.core.management.base import BaseCommand

from shopman.storefront.concierge.service import recover_pending


class Command(BaseCommand):
    help = "Recupera trabalho pendente; envios de resultado desconhecido permanecem contidos."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(recover_pending(), sort_keys=True))
