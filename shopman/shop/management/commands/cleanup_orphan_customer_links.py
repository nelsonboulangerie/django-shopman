"""
Management command: cleanup_orphan_customer_links

Repara (ou remove) vínculos `doorman.CustomerUser` que apontam para um
`guestman.Customer` que não existe mais.

Por que isso acontece: o vínculo guarda o `uuid` do Customer. Quando os clientes
são recriados — reseed, reset de base, migração de dados — os uuids mudam e os
logins antigos ficam apontando para o vazio. O login continua funcionando, mas
`user_can_access_order` passa a devolver False para sempre, e o cliente perde
silenciosamente o canal SSE do acompanhamento (cai no poll) sem nenhum aviso.

Reparo: quando o vínculo registrou o telefone em `metadata["phone"]`, dá para
reencontrar o Customer atual por telefone e religar. Vínculos antigos, criados
antes de o telefone passar a ser gravado, não têm como ser religados — para
esses só resta remover, e o cliente refaz o vínculo no próximo login.

Uso:
    python manage.py cleanup_orphan_customer_links --dry-run
    python manage.py cleanup_orphan_customer_links
    python manage.py cleanup_orphan_customer_links --delete-unrepairable
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Religa (por telefone) ou remove vínculos CustomerUser órfãos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Apenas relata, sem escrever nada.",
        )
        parser.add_argument(
            "--delete-unrepairable",
            action="store_true",
            help=(
                "Remove os vínculos que não dá para religar (sem telefone no "
                "metadata). O cliente refaz o vínculo no próximo login."
            ),
        )

    def handle(self, *args, **options):
        from shopman.doorman.models import CustomerUser
        from shopman.guestman.models import Customer

        seco = options.get("dry_run", False)
        remover = options.get("delete_unrepairable", False)

        ativos = set(
            Customer.objects.filter(is_active=True).values_list("uuid", flat=True)
        )
        por_telefone = {
            phone: uuid
            for uuid, phone in Customer.objects.filter(is_active=True).values_list("uuid", "phone")
            if phone
        }

        religados = 0
        sem_reparo = []
        total = 0

        for link in CustomerUser.objects.all().iterator():
            total += 1
            if link.customer_id in ativos:
                continue

            phone = str((link.metadata or {}).get("phone") or "").strip()
            destino = por_telefone.get(phone) if phone else None

            if destino is not None:
                religados += 1
                if not seco:
                    link.customer_id = destino
                    link.save(update_fields=["customer_id"])
                    logger.info(
                        "customer_link_repaired user=%s phone=%s", link.user_id, phone,
                    )
                continue

            sem_reparo.append(link.pk)

        self.stdout.write(f"vínculos analisados: {total}")
        self.stdout.write(self.style.SUCCESS(f"religados por telefone: {religados}"))
        self.stdout.write(f"órfãos sem reparo possível: {len(sem_reparo)}")

        if sem_reparo and remover:
            if not seco:
                CustomerUser.objects.filter(pk__in=sem_reparo).delete()
            self.stdout.write(
                self.style.WARNING(f"removidos: {len(sem_reparo)} (refazem no próximo login)")
            )
        elif sem_reparo:
            self.stdout.write(
                "use --delete-unrepairable para removê-los; sem isso ficam como estão."
            )

        if seco:
            self.stdout.write(self.style.WARNING("dry-run: nada foi escrito."))
