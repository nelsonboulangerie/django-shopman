"""Avalia os alarmes do B.I. e avisa quem opera (BI-DATA-FOUNDATION-PLAN §7.2).

Invólucro de ``shopman.backstage.bi.alerts.evaluate_all``: roda a cada ciclo
do ``maintenance_worker`` e pode ser chamado à mão para conferir. O que cada
regra viu fica em ``BIAlertRule.last_reading``; o disparo vira ``BIAlertEvent``
+ ``OperatorAlert``. Cooldown é respeitado aqui — um alarme não grita a cada
cinco minutos.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from shopman.backstage.bi.alerts import evaluate_all


class Command(BaseCommand):
    help = "Avalia os alarmes ativos do B.I. contra a camada de leitura e avisa o operador quando disparam."

    def handle(self, *args, **options):
        summary = evaluate_all()
        self.stdout.write(
            f"alarmes do B.I.: {summary.evaluated} avaliados, {summary.fired} disparados, "
            f"{summary.silenced} em silêncio (cooldown), {summary.abstained} sem amostra para opinar."
        )
