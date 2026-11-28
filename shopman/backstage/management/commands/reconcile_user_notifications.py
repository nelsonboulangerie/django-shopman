"""Fecha o alerta pessoal cuja causa já acabou, para toda caixa com alerta ativo.

Cada produtor fecha o próprio alerta no caminho feliz (o signal do anúncio, do
ticket da Cozinha, da revisão de qualidade). Isto é a rede por baixo: o signal
que falhou, o processo que caiu entre o fato e o alerta. Era a leitura do sino
(GET da caixa) que fazia esta conferência, e leitura não produz efeito.

Idempotente: roda no ciclo do ``maintenance_worker``; rodar duas vezes seguidas
não fecha nada a mais.
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from shopman.shop.models import UserNotification
from shopman.shop.models.user_notification import ACTIVE_NOTIFICATION_STATES
from shopman.shop.services import user_notifications

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Fecha os alertas pessoais cuja condição de origem já acabou."

    def handle(self, *args, **options):
        owner_ids = (
            UserNotification.objects.filter(lifecycle__in=ACTIVE_NOTIFICATION_STATES)
            .values_list("user_id", flat=True)
            .distinct()
        )
        changed = 0
        failures = 0
        for user in get_user_model().objects.filter(pk__in=owner_ids).order_by("pk"):
            try:
                changed += user_notifications.reconcile_user_notifications(user=user)
            except Exception:
                failures += 1
                logger.warning("reconcile_user_notifications failed user=%s", user.pk, exc_info=True)
        self.stdout.write(f"alertas pessoais: {changed} fechados, {failures} caixas com falha")
