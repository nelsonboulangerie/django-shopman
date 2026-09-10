"""Liga o canal WhatsApp (concierge) num banco VIVO, onde reseed é proibido.

O `seed` cria canal e vitrine do WhatsApp do zero; em produção ele não roda.
Este comando faz só o que falta, e nunca desfaz o que alguém já configurou:

- Canal ``whatsapp``: cria se não existe (config como no seed). Se existe, liga
  ``is_active`` e preenche APENAS as chaves que faltam (``payment.method``,
  ``payment.timing``, ``notifications.backend``). Edição do Admin fica como está.
- Vitrine ``whatsapp``: cria se não existe e copia da vitrine da loja online
  (``SHOPMAN_STOREFRONT_CHANNEL_REF``) todo item que ainda não está nela, com o
  mesmo preço e as mesmas flags. Item que já existe não é tocado.

Nunca apaga nada. ``--dry-run`` mostra o plano sem gravar.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from shopman.offerman.models import Listing, ListingItem

from shopman.shop.models import Channel

CHANNEL_REF = "whatsapp"
LISTING_REF = "whatsapp"

#: Config do canal como no seed (`config/management/commands/seed.py`). Só é
#: gravada inteira quando o canal NÃO existe; no canal existente entram apenas as
#: chaves de ``REQUIRED_KEYS`` que faltarem.
CHANNEL_CONFIG = {
    "confirmation": {"mode": "auto_confirm", "timeout_minutes": 5, "stale_new_alert_minutes": 10},
    # Link de Pix/cartão no chat logo depois do pedido; `at_commit` faz a
    # confirmação esperar a captura.
    "payment": {"method": ["pix", "card"], "timing": "at_commit", "timeout_minutes": 10},
    "notifications": {"backend": "manychat"},
    "stock": {"hold_ttl_minutes": 30, "allow_untracked": False, "sells_nonconforming": False},
}

#: (aspecto, chave, valor) que o concierge precisa para funcionar.
REQUIRED_KEYS = (
    ("payment", "method", ["pix", "card"]),
    ("payment", "timing", "at_commit"),
    ("notifications", "backend", "manychat"),
)


class Command(BaseCommand):
    help = "Garante canal e vitrine do WhatsApp (concierge) sem reseed. Idempotente; nunca apaga."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Mostra o que mudaria sem gravar.")

    def handle(self, *args, **options):
        dry_run = bool(options["dry_run"])
        if dry_run:
            self.stdout.write("Simulação: nada será gravado.")
        with transaction.atomic():
            self._ensure_channel(dry_run)
            self._ensure_listing(dry_run)
            if dry_run:
                transaction.set_rollback(True)

    # ── Canal ─────────────────────────────────────────────────────────

    def _ensure_channel(self, dry_run: bool) -> None:
        channel = Channel.objects.filter(ref=CHANNEL_REF).first()
        if channel is None:
            self.stdout.write(f"Canal '{CHANNEL_REF}': criado (ativo, config do seed).")
            if not dry_run:
                Channel.objects.create(
                    ref=CHANNEL_REF,
                    name="WhatsApp",
                    is_active=True,
                    display_order=4,
                    config=dict(CHANNEL_CONFIG),
                )
            return

        changes: list[str] = []
        if not channel.is_active:
            channel.is_active = True
            changes.append("is_active=True")

        config = dict(channel.config or {})
        for aspect, key, value in REQUIRED_KEYS:
            section = config.get(aspect)
            if not isinstance(section, dict):
                section = {}
            if key not in section:
                section = {**section, key: value}
                config[aspect] = section
                changes.append(f"{aspect}.{key}={value!r}")
        channel.config = config

        if not changes:
            self.stdout.write(f"Canal '{CHANNEL_REF}': já em ordem, nada a fazer.")
            return
        self.stdout.write(f"Canal '{CHANNEL_REF}': {', '.join(changes)}.")
        if not dry_run:
            channel.save(update_fields=["is_active", "config"])

    # ── Vitrine ───────────────────────────────────────────────────────

    def _ensure_listing(self, dry_run: bool) -> None:
        source_ref = getattr(settings, "SHOPMAN_STOREFRONT_CHANNEL_REF", "web") or "web"
        source = Listing.objects.filter(ref=source_ref).first()

        listing = Listing.objects.filter(ref=LISTING_REF).first()
        if listing is None:
            self.stdout.write(f"Vitrine '{LISTING_REF}': criada.")
            if dry_run:
                listing = Listing(ref=LISTING_REF, name="WhatsApp", is_active=True, priority=5)
            else:
                listing = Listing.objects.create(ref=LISTING_REF, name="WhatsApp", is_active=True, priority=5)

        if source is None:
            self.stdout.write(
                self.style.WARNING(f"Vitrine '{source_ref}' não existe: nenhum item para copiar.")
            )
            return

        existing = set()
        if listing.pk:
            existing = {
                (product_id, min_qty)
                for product_id, min_qty in ListingItem.objects.filter(listing=listing).values_list("product_id", "min_qty")
            }
        missing = [
            item
            for item in ListingItem.objects.filter(listing=source).select_related("product").order_by("product__sku")
            if (item.product_id, item.min_qty) not in existing
        ]
        if not missing:
            self.stdout.write(f"Vitrine '{LISTING_REF}': já espelha '{source_ref}', nada a copiar.")
            return

        for item in missing:
            self.stdout.write(
                f"  + {item.product.sku}: R$ {item.price_q / 100:.2f}"
                f"{'' if item.is_published else ' (não publicado)'}"
                f"{'' if item.is_sellable else ' (não vendável)'}"
            )
            if not dry_run:
                ListingItem.objects.create(
                    listing=listing,
                    product=item.product,
                    price_q=item.price_q,
                    min_qty=item.min_qty,
                    is_published=item.is_published,
                    is_sellable=item.is_sellable,
                )
        self.stdout.write(f"Vitrine '{LISTING_REF}': {len(missing)} item(ns) copiado(s) de '{source_ref}'.")
