"""A decisão em sombra da Concierge (N5): varre as entradas e junta os resultados.

Roda no ``maintenance_worker``. Desligada pelo campo ``Shop.conversational_shadow_enabled``
(nasce desligada), não toca em nada. Ligada, grava o que o framework de comércio
conversacional faria com cada entrada e, depois, os pedidos do cliente em 24 h e em 7 dias.
Nunca envia, nunca escreve no comércio, nunca chama modelo.
"""

import json

from django.core.management.base import BaseCommand

from shopman.storefront.concierge.shadow import SWEEP_LIMIT, join_outcomes, sweep


class Command(BaseCommand):
    help = "Decide em sombra as entradas da Concierge e junta os pedidos em 24 h e 7 dias."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=SWEEP_LIMIT, help="Entradas por ciclo.")

    def handle(self, *args, **options):
        result = {"sweep": sweep(limit=options["limit"]), "join": join_outcomes(limit=options["limit"])}
        self.stdout.write(json.dumps(result, sort_keys=True))
