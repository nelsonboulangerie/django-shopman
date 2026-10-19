"""Instala os grupos comerciais que o descritor da Instância declara.

O ``seed`` só descreve bancos descartáveis. Produção não é resemeada a cada
deploy, portanto dados operacionais obrigatórios precisam de uma porta
idempotente no release. Este comando cria o que ainda não existe e, depois
disso, respeita toda edição feita pelo gestor.

Quais grupos, com que desconto e que mensagem é dado da Instância: a seção
``bootstrap.customer_groups`` do descritor (``SHOPMAN_INSTANCE_DESCRIPTOR``).
Uma Instância que não declara grupo nenhum não ganha grupo nenhum.
"""

from __future__ import annotations

from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

#: As chaves de ``config`` de cada item de ``bootstrap.customer_groups``.
CUSTOMER_GROUP_FIELDS = frozenset({
    "name", "discount_kind", "rounding", "savings_message", "discount_percent", "fulfillment_types",
})


def promotion_ref(group_ref: str) -> str:
    return f"grupo-{group_ref}"


@transaction.atomic
def ensure_commercial_groups(items: list[dict]) -> list[tuple[str, str]]:
    """Cria os grupos declarados ausentes sem transformar deploy em dono da tela.

    A presença de ``grupo-<ref>`` é a fronteira: depois que a promoção existe,
    inclusive pausada, o operador já assumiu o cadastro e nenhum deploy volta a
    ligá-la ou a trocar percentual, nome, escopo ou mensagem.
    """
    from shopman.guestman.models import PriceTier

    from shopman.shop.models import Promotion

    now = timezone.now()
    open_end = timezone.make_aware(datetime(2099, 12, 31, 23, 59, 59))
    outcomes: list[tuple[str, str]] = []

    for item in items:
        ref = item["ref"]
        definition = item.get("config", {})
        if set(definition) != CUSTOMER_GROUP_FIELDS:
            raise ValueError(f"customer group {ref} requires {sorted(CUSTOMER_GROUP_FIELDS)}")
        tier, tier_created = PriceTier.objects.get_or_create(
            ref=ref,
            defaults={
                "name": definition["name"],
                "metadata": {
                    "discount_kind": definition["discount_kind"],
                    "rounding": definition["rounding"],
                    "savings_message": definition["savings_message"],
                },
            },
        )

        # Promoção presente significa que o cadastro já passou às mãos do
        # gestor. Até promoção pausada é decisão explícita e deve sobreviver ao
        # deploy seguinte.
        if Promotion.objects.filter(ref=promotion_ref(ref)).exists():
            outcomes.append((ref, "preservado"))
            continue

        # O ref é conhecido, mas outro nome revela um cadastro próprio que
        # antecede este bootstrap. Conceder desconto a ele por inferência seria
        # uma mudança financeira silenciosa.
        if not tier_created and tier.name != definition["name"]:
            outcomes.append((ref, "preservado-sem-desconto"))
            continue

        metadata = dict(tier.metadata or {})
        for key in ("discount_kind", "rounding", "savings_message"):
            metadata.setdefault(key, definition[key])
        if metadata != (tier.metadata or {}):
            tier.metadata = metadata
            tier.save(update_fields=["metadata", "updated_at"])

        Promotion.objects.create(
            ref=promotion_ref(ref),
            name=definition["name"],
            type=Promotion.PERCENT,
            value=definition["discount_percent"],
            valid_from=now,
            valid_until=open_end,
            customer_segments=[ref],
            fulfillment_types=definition["fulfillment_types"],
            is_active=True,
        )
        outcomes.append((ref, "criado" if tier_created else "reparado"))

    return outcomes


class Command(BaseCommand):
    help = "Cria os grupos comerciais que o descritor da Instância declara, sem sobrescrever edições do gestor."

    def handle(self, *args, **options):
        from config.instance_descriptors import UnsafeDescriptor, configured_descriptor

        try:
            items = configured_descriptor()["bootstrap"]["customer_groups"]
            outcomes = ensure_commercial_groups(items)
        except (OSError, KeyError, ValueError, UnsafeDescriptor) as exc:
            raise CommandError(f"setup_commercial_groups: {exc}") from exc
        for ref, outcome in outcomes:
            self.stdout.write(f"  Grupo comercial {ref}: {outcome}")
        self.stdout.write(self.style.SUCCESS("setup_commercial_groups: OK"))
