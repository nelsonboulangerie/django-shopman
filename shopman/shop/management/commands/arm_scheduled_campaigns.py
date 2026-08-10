"""Arma as ocasiões agendadas que vão acontecer em breve.

**Este comando não dispara nada.** Ele cria uma `Directive` com `available_at` no instante
exato do início da janela; quem dispara é `process_directives --watch`, que roda a cada
~2 segundos.

A diferença é a razão de a F9 existir: antes, o despacho acontecia no ciclo de manutenção
(a cada 5 minutos), então uma relâmpago das 17h30 podia sair às 17h34 — numa promoção cujo
valor é o minuto. Agora a latência de ARMAR é irrelevante (acontece na hora anterior) e a
de DISPARAR é de segundos.

Nenhum threshold da ADR-003 mudou, e não entrou broker: é o mesmo padrão que o atraso da
onda VIP já usava.
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Arma Directives para as ocasiões agendadas do próximo horizonte."

    def add_arguments(self, parser):
        parser.add_argument(
            "--horizon-minutes",
            type=int,
            default=60,
            help=(
                "Quão à frente armar (default 60). Precisa ser maior que o intervalo da "
                "vassoura, senão uma ocasião cai entre dois ciclos e nunca é armada."
            ),
        )

    def handle(self, *args, **options):
        from shopman.shop.services import campaign

        armed = campaign.arm_scheduled(horizon_minutes=int(options["horizon_minutes"]))
        if armed:
            logger.info("arm_scheduled_campaigns: %d ocasião(ões) armada(s)", armed)
            self.stdout.write(f"{armed} ocasião(ões) armada(s).")
        return None
