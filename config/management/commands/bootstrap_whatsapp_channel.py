"""Liga o canal WhatsApp (concierge) num banco VIVO, onde reseed é proibido.

O `seed` cria canal e vitrine do WhatsApp do zero; em produção ele não roda.
Este comando faz só o que falta, e nunca desfaz o que alguém já configurou no canal.

A definição do canal é UMA: o item ``whatsapp`` de ``bootstrap.channels`` no
descritor da Instância (``SHOPMAN_INSTANCE_DESCRIPTOR``). Este comando não carrega
config própria; ele lê o descritor.

- Canal ``whatsapp``: cria se não existe, com nome, ordem e config do descritor.
  Se existe, liga ``is_active`` e preenche APENAS as chaves de ``REQUIRED_KEYS``
  que faltam, com o valor do descritor. Edição do Admin fica como está.
- Vitrine ``whatsapp``: ESPELHA a vitrine apontada por ``pricing.listing_from``
  (``shop/services/listing_mirror.py``). O comando liga o ponteiro e alinha a
  vitrine uma vez; dali em diante cada mudança no site chega ao WhatsApp sozinha,
  sem rodar nada. Alinhar quer dizer igualar: item que só o WhatsApp tinha sai,
  preço diferente vira o do site. Para manter vitrine própria, grave
  ``pricing.listing_from = ""`` no canal: chave presente não é tocada.

Instância cujo descritor não declara o canal ``whatsapp``: nada a fazer.

``--dry-run`` mostra o plano sem gravar.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from shopman.offerman.models import Listing

from config.instance_descriptors import (
    UnsafeDescriptor,
    configured_descriptor,
    declared_channel,
)
from shopman.shop.models import Channel, Shop
from shopman.shop.services import listing_mirror

CHANNEL_REF = "whatsapp"
LISTING_REF = "whatsapp"

#: (aspecto, chave) que o concierge precisa para funcionar. O VALOR vem do
#: descritor; aqui mora só a lista do que o canal existente não pode não ter.
REQUIRED_KEYS = (
    ("payment", "method"),
    ("payment", "timing"),
    ("notifications", "backend"),
    ("pricing", "listing_from"),
)


def _declared_overrides(item: dict) -> dict:
    overrides = item.get("config", {}).get("overrides", {})
    for aspect, key in REQUIRED_KEYS:
        if key not in (overrides.get(aspect) or {}):
            raise CommandError(
                f"o descritor declara o canal '{CHANNEL_REF}' sem {aspect}.{key}, "
                "que o concierge exige"
            )
    return overrides


class Command(BaseCommand):
    help = "Garante canal e vitrine espelhada do WhatsApp (concierge) a partir do descritor, sem reseed. Idempotente."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Mostra o que mudaria sem gravar.")

    def handle(self, *args, **options):
        try:
            descriptor = configured_descriptor()
        except (OSError, KeyError, ValueError, UnsafeDescriptor) as exc:
            raise CommandError(f"bootstrap_whatsapp_channel: {exc}") from exc
        item = declared_channel(descriptor, CHANNEL_REF)
        if item is None:
            self.stdout.write(
                f"Instância '{descriptor['instance']['ref']}' não declara o canal '{CHANNEL_REF}': nada a fazer."
            )
            return
        overrides = _declared_overrides(item)

        dry_run = bool(options["dry_run"])
        if dry_run:
            self.stdout.write("Simulação: nada será gravado.")
        with transaction.atomic():
            # Vitrine antes do canal: o save do canal com o ponteiro também alinha
            # (receiver), e aqui o comando quer relatar item por item.
            self._ensure_listing(overrides)
            self._ensure_channel(item, overrides)
            if dry_run:
                transaction.set_rollback(True)

    # ── Canal ─────────────────────────────────────────────────────────

    def _ensure_channel(self, item: dict, overrides: dict) -> None:
        channel = Channel.objects.filter(ref=CHANNEL_REF).first()
        if channel is None:
            config = item.get("config", {})
            self.stdout.write(f"Canal '{CHANNEL_REF}': criado (ativo, config do descritor).")
            Channel.objects.create(
                ref=CHANNEL_REF,
                shop=Shop.objects.order_by("pk").first(),
                name=config.get("name", ""),
                commerce_policy=config.get("commerce_policy", "order"),
                is_active=True,
                display_order=config.get("display_order", 0),
                config=overrides,
            )
            return

        changes: list[str] = []
        if not channel.is_active:
            channel.is_active = True
            changes.append("is_active=True")

        config = dict(channel.config or {})
        for aspect, key in REQUIRED_KEYS:
            section = config.get(aspect)
            if not isinstance(section, dict):
                section = {}
            if key not in section:
                value = overrides[aspect][key]
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

    def _ensure_listing(self, overrides: dict) -> None:
        channel = Channel.objects.filter(ref=CHANNEL_REF).first()
        config = dict(channel.config or {}) if channel else {}
        pricing = config.get("pricing") if isinstance(config.get("pricing"), dict) else {}
        if channel is not None and "listing_from" in pricing:
            source_ref = listing_mirror.source_ref_from_config(config)
            if not source_ref:
                self.stdout.write(f"Vitrine '{LISTING_REF}': própria (pricing.listing_from vazio), não espelha.")
                return
        else:
            source_ref = listing_mirror.source_ref_from_config(overrides)

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
