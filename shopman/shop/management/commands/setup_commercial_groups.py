"""Instala os grupos comerciais canônicos que precisam existir no banco vivo.

O ``seed`` só descreve bancos descartáveis. Produção não é resemeada a cada
deploy, portanto dados operacionais obrigatórios precisam de uma porta
idempotente no release. Este comando cria o que ainda não existe e, depois
disso, respeita toda edição feita pelo gestor.
"""

from __future__ import annotations

from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

GROUPS = (
    {
        "ref": "staff",
        "name": "Equipe",
        "legacy_names": {"Funcionarios", "Funcionários", "Staff"},
        "discount_kind": "equipe",
        "savings_message": "Hoje você economizou {amount} por ser da Equipe",
        "discount_percent": 30,
        "fulfillment_types": ["pickup"],
    },
    {
        "ref": "alianca-francesa",
        "name": "Aliança Francesa",
        "legacy_names": set(),
        "discount_kind": "parceiro",
        "savings_message": "Hoje você economizou {amount} por ser da Aliança Francesa",
        "discount_percent": 15,
        "fulfillment_types": [],
    },
)


@transaction.atomic
def ensure_commercial_groups() -> list[tuple[str, str]]:
    """Cria os defaults ausentes sem transformar deploy em dono da tela.

    A presença de ``grupo-<ref>`` é a fronteira: depois que a promoção existe,
    inclusive pausada, o operador já assumiu o cadastro e nenhum deploy volta a
    ligá-la ou a trocar percentual, nome, escopo ou mensagem.
    """
    from shopman.guestman.models import PriceTier

    from shopman.shop.models import Promotion

    now = timezone.now()
    open_end = timezone.make_aware(datetime(2099, 12, 31, 23, 59, 59))
    outcomes: list[tuple[str, str]] = []

    for definition in GROUPS:
        ref = definition["ref"]
        promotion_ref = f"grupo-{ref}"
        tier, tier_created = PriceTier.objects.get_or_create(
            ref=ref,
            defaults={
                "name": definition["name"],
                "metadata": {
                    "discount_kind": definition["discount_kind"],
                    "rounding": 50,
                    "savings_message": definition["savings_message"],
                },
            },
        )

        # Promoção presente significa que o cadastro já passou às mãos do
        # gestor. Até promoção pausada é decisão explícita e deve sobreviver ao
        # deploy seguinte.
        if Promotion.objects.filter(ref=promotion_ref).exists():
            outcomes.append((ref, "preservado"))
            continue

        changed_fields: list[str] = []
        metadata = dict(tier.metadata or {})
        for key, value in (
            ("discount_kind", definition["discount_kind"]),
            ("rounding", 50),
            ("savings_message", definition["savings_message"]),
        ):
            if key not in metadata:
                metadata[key] = value
                if "metadata" not in changed_fields:
                    changed_fields.append("metadata")
        if tier.name in definition["legacy_names"]:
            tier.name = definition["name"]
            changed_fields.append("name")
        if metadata != (tier.metadata or {}):
            tier.metadata = metadata
        if changed_fields:
            tier.save(update_fields=[*changed_fields, "updated_at"])

        Promotion.objects.create(
            ref=promotion_ref,
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
    help = "Cria os grupos comerciais canônicos ausentes sem sobrescrever edições do gestor."

    def handle(self, *args, **options):
        for ref, outcome in ensure_commercial_groups():
            self.stdout.write(f"  Grupo comercial {ref}: {outcome}")
        self.stdout.write(self.style.SUCCESS("setup_commercial_groups: OK"))
