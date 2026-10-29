"""
sync_platform_catalogs — a reconciliação diária dos catálogos do Google e da Meta.

O envio acontece na hora de cada mudança (estoque, pausa, ocultação, preço, coleções,
canal ligado/desligado: ``handlers/catalog_projection``). Esta é a rede de segurança,
e ela cobre três buracos:

- o Google exige que cada produto seja reenviado ao menos a cada 30 dias, ou ele
  expira (developers.google.com/merchant/api/guides/products/frequent-updates);
- produto que entrou numa coleção do canal não dispara sinal nenhum;
- envio que falhou de vez (credencial vencida, queda longa) fica para trás.

Por isso ele reenvia todo SKU do canal cujo último envio passou de
``--min-interval-hours`` (24h), e retira o que saiu da composição. Barato quando
não há nada a fazer: lê a composição e o estado de sync, sem calcular estoque. Roda
no ``maintenance_worker``; quem segura a cadência é o próprio comando.

Usage::

    python manage.py sync_platform_catalogs                 # o que venceu, em todos os canais
    python manage.py sync_platform_catalogs --force         # tudo, agora
    python manage.py sync_platform_catalogs --dry-run --channel google-shopping
"""

from __future__ import annotations

import json
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

DEFAULT_MIN_INTERVAL_HOURS = 24
#: Envio que falhou não é reenfileirado a cada ciclo: espera este tanto antes de tentar.
RETRY_AFTER_FAILURE_HOURS = 1


class Command(BaseCommand):
    help = "Reenvia ao Google e à Meta o catálogo que venceu e retira o que saiu do canal."

    def add_arguments(self, parser):
        parser.add_argument("--channel", default="", help="Só este canal de plataforma.")
        parser.add_argument(
            "--min-interval-hours", type=int, default=DEFAULT_MIN_INTERVAL_HOURS,
            help="Reenvia o SKU cujo último envio é mais velho que isto (default 24).",
        )
        parser.add_argument("--force", action="store_true", help="Reenvia todos os SKUs agora.")
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Mostra o que seria enviado (exige --channel), sem chamar a plataforma nem enfileirar.",
        )

    def handle(self, *args, **options):
        from shopman.offerman.conf import get_projection_backend_channels

        from shopman.shop.services import display_catalog

        if options["dry_run"]:
            # Conferível sem credencial e com o envio desligado: só lê e traduz.
            if not display_catalog.is_platform_channel(options["channel"]):
                raise CommandError("--dry-run exige --channel com um canal de plataforma (Google ou Meta).")
            self._dry_run(options["channel"])
            return

        channels = [ref for ref in get_projection_backend_channels() if display_catalog.is_platform_channel(ref)]
        if options["channel"]:
            if options["channel"] not in channels:
                raise CommandError(
                    f"'{options['channel']}' não é canal de plataforma com envio ligado "
                    f"(GOOGLE_MERCHANT_PROJECTION / META_CATALOG_PROJECTION). Ligados: {channels or 'nenhum'}."
                )
            channels = [options["channel"]]

        for ref in channels:
            sent, retracted = self._reconcile(ref, options)
            if sent or retracted:
                self.stdout.write(f"{ref}: {sent} reenviado(s), {retracted} retirado(s).")

    def _reconcile(self, ref: str, options) -> tuple[int, int]:
        from shopman.shop.handlers.catalog_projection import enqueue_project
        from shopman.shop.models import CatalogSyncState
        from shopman.shop.services import display_catalog

        now = timezone.now()
        composition = set(display_catalog.composition_skus(ref))
        states = {state.sku: state for state in CatalogSyncState.objects.filter(channel_ref=ref)}
        stale_before = now - timedelta(hours=max(0, options["min_interval_hours"]))
        retry_before = now - timedelta(hours=RETRY_AFTER_FAILURE_HOURS)

        def due(state) -> bool:
            if options["force"] or state is None:
                return True
            if state.status == "pending":
                return False  # já está na fila
            if state.status == "error":
                return state.updated_at <= retry_before
            return state.last_synced_at is None or state.last_synced_at <= stale_before

        sent = 0
        for sku in sorted(composition):
            if due(states.get(sku)):
                enqueue_project(sku, ref, trigger="daily_resync")
                sent += 1

        retracted = 0
        gone = (
            CatalogSyncState.objects.filter(channel_ref=ref)
            .exclude(sku__in=composition)
            .filter(~Q(status="retracted"))
            .values_list("sku", flat=True)
        )
        for sku in gone:
            if due(states.get(sku)):
                enqueue_project(sku, ref, trigger="left_channel")
                retracted += 1
        return sent, retracted

    def _dry_run(self, ref: str) -> None:
        from shopman.shop.services import display_catalog

        _channel, fmt = display_catalog.resolve_channel(ref)
        items = display_catalog.display_items(ref)
        if fmt == "google_merchant":
            from shopman.shop.adapters.catalog_projection_google import _get_config, build_product_input

            cfg = _get_config()
            payload = [build_product_input(item, cfg) for item in items]
        else:
            from shopman.shop.adapters.catalog_projection_meta import _get_config, item_data

            cfg = _get_config()
            payload = [{"method": "UPDATE", "retailer_id": item.sku, "data": item_data(item, cfg)} for item in items]
        self.stdout.write(f"Dry run — {len(items)} item(s) em {ref}:\n")
        self.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False))
        self.stdout.write("\nNada foi enviado (dry run).")
