"""Ensaio do botão "Confirmar pedido" no WhatsApp (#2926).

    manage.py concierge_button_probe --subscriber <id do assinante do dono>   # manda o teste
    manage.py concierge_button_probe --show                                    # o que chegou

Só no número do dono: nada de pedido, o clique só é gravado e respondido.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from shopman.storefront.concierge import button_probe


class Command(BaseCommand):
    help = "Ensaio do botão Confirmar pedido no WhatsApp: manda o teste (--subscriber) ou mostra o que chegou (--show)."

    def add_arguments(self, parser):
        parser.add_argument("--subscriber", default="", help="Id do assinante no ManyChat (o do dono).")
        parser.add_argument("--base-url", default="", help="Endereço público da API (ex.: https://api.boulangerie.com.br).")
        parser.add_argument("--show", action="store_true", help="Mostra os cliques gravados.")

    def handle(self, *args, **options):
        if options["show"]:
            rows = button_probe.recorded()
            if not rows:
                self.stdout.write("Nenhum clique gravado ainda.")
            for row in rows:
                self.stdout.write(json.dumps(row, ensure_ascii=False, indent=1, default=str))
            return
        if not options["subscriber"] or not options["base_url"]:
            raise CommandError("Use --subscriber <id> e --base-url https://<api> (ou --show).")
        url = options["base_url"].rstrip("/") + reverse("concierge:button-probe")
        if not url.startswith("https://"):
            raise CommandError("O ManyChat só chama endereço https.")
        result = button_probe.send(options["subscriber"], callback_url=url)
        self.stdout.write(json.dumps({k: v for k, v in result.items() if k != "raw"}, ensure_ascii=False, default=str))
