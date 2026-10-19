"""Reconcilia a cabeça do snapshot público Continuum com o catálogo canônico.

O caminho rápido é a directive ``continuum.catalog_structure.refresh``, que a
escrita no catálogo enfileira. Este comando é a rede: roda no
``maintenance_worker`` e reconstrói a cabeça que falta, que ficou suja ou que
venceu ``reconcile_after_ms`` (signal perdido, ``QuerySet.update`` em massa,
processo que morreu antes do ``on_commit``). Com o Continuum desligado, volta
calado.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.continuum import candidate_enabled, refresh_head, shadow_enabled


class Command(BaseCommand):
    help = "Reconstrói a cabeça do snapshot público do cardápio quando falta, está suja ou venceu."

    def handle(self, *args, **options):
        if not (candidate_enabled() or shadow_enabled()):
            return
        head, status = refresh_head(channel_ref=STOREFRONT_CHANNEL_REF)
        if status != "head":
            self.stdout.write(f"refresh_catalog_structure: {status} sequence={head.sequence}")
