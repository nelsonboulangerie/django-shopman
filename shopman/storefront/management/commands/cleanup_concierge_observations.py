"""Remove captura passiva vencida ou atende exclusão por subject autenticado."""

import json

from django.core.management.base import BaseCommand, CommandError

from shopman.storefront.concierge.service import purge_observations


class Command(BaseCommand):
    help = "Remove observações vencidas; --subject executa descarte pontual do titular."

    def add_arguments(self, parser):
        parser.add_argument("--connection-key", default="")
        parser.add_argument("--subject", default="")

    def handle(self, *args, **options):
        connection_key = str(options["connection_key"] or "").strip()
        subject = str(options["subject"] or "").strip()
        if subject and not connection_key:
            raise CommandError("--subject exige --connection-key")
        result = purge_observations(
            connection_key=connection_key,
            subject=subject,
        )
        self.stdout.write(json.dumps(result, sort_keys=True))
