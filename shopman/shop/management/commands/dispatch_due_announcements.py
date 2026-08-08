"""Despacha campanhas aprovados com hora marcada.

O gestor aprova de manhã e marca "às 7h"; ninguém precisa estar na tela na
hora. Este comando é quem abre a porta quando o relógio chega — contraparte de
``expire_stale_announcements``, que fecha quando o prazo passa.
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Despacha Announcements agendados cuja hora de publicação chegou."

    def handle(self, *args, **options):
        from shopman.shop.services import campaign

        dispatched = campaign.dispatch_due()
        if dispatched:
            logger.info("dispatch_due_announcements: %d announcement(s) despachado(s)", dispatched)
            self.stdout.write(f"{dispatched} anúncio(s) despachado(s).")
        return None
