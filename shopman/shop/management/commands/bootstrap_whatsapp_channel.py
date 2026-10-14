"""Liga o canal WhatsApp (concierge) num banco VIVO, onde reseed é proibido.

O `seed` cria canal e vitrine do WhatsApp do zero; em produção ele não roda.
Este comando faz só o que falta, e nunca desfaz o que alguém já configurou no canal:

- Canal ``whatsapp``: cria se não existe (config como no seed). Se existe, liga
  ``is_active`` e preenche APENAS as chaves que faltam (``payment.method``,
  ``payment.timing``, ``notifications.backend``, ``pricing.listing_from``).
  Edição do Admin fica como está.
- Vitrine ``whatsapp``: ESPELHA a da loja online (``SHOPMAN_STOREFRONT_CHANNEL_REF``)
  pelo ponteiro ``pricing.listing_from`` (``shop/services/listing_mirror.py``). O
  comando liga o ponteiro e alinha a vitrine uma vez; dali em diante cada mudança no
  site chega ao WhatsApp sozinha, sem rodar nada. Alinhar quer dizer igualar: item
  que só o WhatsApp tinha sai, preço diferente vira o do site. Para manter vitrine
  própria, grave ``pricing.listing_from = ""`` no canal: chave presente não é tocada.

``--dry-run`` mostra o plano sem gravar.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from shopman.offerman.models import Listing

from shopman.shop.models import Channel
from shopman.shop.services import listing_mirror

CHANNEL_REF = "whatsapp"
LISTING_REF = "whatsapp"

#: Config do canal como no seed (`config/management/commands/seed.py`). Só é
#: gravada inteira quando o canal NÃO existe; no canal existente entram apenas as
#: chaves de ``REQUIRED_KEYS`` que faltarem.
CHANNEL_CONFIG = {
    # Pedido remoto só é aceito quando uma pessoa confere disponibilidade, como
    # no seed e na migração ``shop.0054``, que tirou o autoaceite dos canais remotos.
    "confirmation": {"mode": "manual", "stale_new_alert_minutes": 10},
    # Link de Pix/cartão no chat logo depois do pedido; `at_commit` faz a
    # confirmação esperar a captura.
    "payment": {"method": ["pix", "card"], "timing": "at_commit", "timeout_minutes": 10},
    "notifications": {"backend": "manychat"},
    "stock": {"hold_ttl_minutes": 30, "allow_untracked": False, "sells_nonconforming": False},
}


def _storefront_ref() -> str:
    return getattr(settings, "SHOPMAN_STOREFRONT_CHANNEL_REF", "web") or "web"

#: (aspecto, chave, valor) que o concierge precisa para funcionar.
REQUIRED_KEYS = (
    ("payment", "method", ["pix", "card"]),
    ("payment", "timing", "at_commit"),
    ("notifications", "backend", "manychat"),
)


def _required_keys():
    """``REQUIRED_KEYS`` + o ponteiro da vitrine, que depende do settings."""
    return (*REQUIRED_KEYS, ("pricing", "listing_from", _storefront_ref()))


class Command(BaseCommand):
    help = "Garante canal e vitrine espelhada do WhatsApp (concierge) sem reseed. Idempotente."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Mostra o que mudaria sem gravar.")

    def handle(self, *args, **options):
        dry_run = bool(options["dry_run"])
        if dry_run:
            self.stdout.write("Simulação: nada será gravado.")
        with transaction.atomic():
            # Vitrine antes do canal: o save do canal com o ponteiro também alinha
            # (receiver), e aqui o comando quer relatar item por item.
            self._ensure_listing(dry_run)
            self._ensure_channel(dry_run)
            if dry_run:
                transaction.set_rollback(True)

    # ── Canal ─────────────────────────────────────────────────────────

    def _ensure_channel(self, dry_run: bool) -> None:
        channel = Channel.objects.filter(ref=CHANNEL_REF).first()
        if channel is None:
            self.stdout.write(f"Canal '{CHANNEL_REF}': criado (ativo, config do seed).")
            Channel.objects.create(
                ref=CHANNEL_REF,
                name="WhatsApp",
                is_active=True,
                display_order=4,
                config={**CHANNEL_CONFIG, "pricing": {"listing_from": _storefront_ref()}},
            )
            return

        changes: list[str] = []
        if not channel.is_active:
            channel.is_active = True
            changes.append("is_active=True")

        config = dict(channel.config or {})
        for aspect, key, value in _required_keys():
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
        channel.save(update_fields=["is_active", "config"])

    # ── Vitrine ───────────────────────────────────────────────────────

    def _ensure_listing(self, dry_run: bool) -> None:
        channel = Channel.objects.filter(ref=CHANNEL_REF).first()
        config = dict(channel.config or {}) if channel else {}
        pricing = config.get("pricing") if isinstance(config.get("pricing"), dict) else {}
        if channel is not None and "listing_from" in pricing:
            source_ref = listing_mirror.source_ref_from_config(config)
            if not source_ref:
                self.stdout.write(f"Vitrine '{LISTING_REF}': própria (pricing.listing_from vazio), não espelha.")
                return
        else:
            source_ref = _storefront_ref()

        if not Listing.objects.filter(ref=LISTING_REF).exists():
            Listing.objects.create(ref=LISTING_REF, name="WhatsApp", is_active=True, priority=5)
            self.stdout.write(f"Vitrine '{LISTING_REF}': criada.")

        if not Listing.objects.filter(ref=source_ref).exists():
            self.stdout.write(
                self.style.WARNING(f"Vitrine '{source_ref}' não existe: nada para espelhar.")
            )
            return

        result = listing_mirror.sync(LISTING_REF, source_ref)
        if not result.changed:
            self.stdout.write(f"Vitrine '{LISTING_REF}': já espelha '{source_ref}', nada a alinhar.")
            return
        for line in result.lines:
            self.stdout.write(f"  {line}")
        self.stdout.write(
            f"Vitrine '{LISTING_REF}': alinhada com '{source_ref}' "
            f"({result.created} novo(s), {result.updated} alterado(s), {result.deleted} removido(s))."
        )
