"""Avisa o operador do experimento de versão que passou do prazo (R4 do release, OC-20).

O resolvedor já devolve a versão padrão a todo mundo quando ``remove_after`` passa;
este comando é quem conta a alguém, sem depender de um GET (que só lê). Roda no
``maintenance_worker``; o debounce do alerta segura a repetição.
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Avisa o operador de cada experimento de versão ligado com o prazo vencido."

    def handle(self, *args, **options):
        from shopman.shop.services import experience

        expired = experience.alert_expired_experiments()
        if expired:
            logger.info("alert_expired_experiments: %d experimento(s) vencido(s)", expired)
            self.stdout.write(f"{expired} experimento(s) vencido(s).")
        return None
