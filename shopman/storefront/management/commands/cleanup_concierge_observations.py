"""Remove captura passiva vencida ou atende exclusão por subject autenticado.

Na limpeza periódica, antes de apagar, o prazo de cada observação é
realinhado à política vigente (``align_observation_retention``): mudar
``CONCIERGE_OBSERVATION_RETENTION_DAYS`` vale também para o que já foi guardado.
"""

import json

from django.core.management.base import BaseCommand, CommandError

from shopman.storefront.concierge.service import align_observation_retention, purge_observations


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
        realigned = 0 if subject else align_observation_retention()
        result = purge_observations(
            connection_key=connection_key,
            subject=subject,
        )
        if realigned:
            result = {**result, "realigned": realigned}
        self.stdout.write(json.dumps(result, sort_keys=True))
