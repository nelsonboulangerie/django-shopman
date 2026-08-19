"""Aplica a taxonomia de coleções decidida em 17/08 sem reseed.

O `seed` já produz essa taxonomia num ambiente vazio, mas rodá-lo onde há
operação de verdade injeta venda de demonstração junto. Este comando faz só a
mudança de catálogo, em ambiente que já roda:

- **"Balcão" sai.** Ela agrupava por ONDE o produto era vendido, não pelo que
  ele é, e por isso nunca classificou nada. Os 7 produtos vão para casas reais.
- **"Despensa" vira "Mercearia"** — renomeada NO LUGAR (ref e rótulo). Recriar
  perderia os 11 vínculos de produto, a ordem e qualquer referência à linha.
- **"Combos" nasce**, para o bundle que não é categoria de produto nenhuma.

Idempotente: rodar de novo não faz nada. Nenhum pedido, sessão ou movimento é
tocado — é catálogo, não operação.

⚠️ **Duas consequências, aceitas pelo dono:** os feeds (menu impresso, TVs)
exibem por coleção, então os 6 produtos que estavam escondidos em "Balcão"
passam a poder aparecer; e promoção é escopada por coleção — a "Semana do Pão"
dá 15% em Rústicos, que ganha quatro produtos.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

# A mesma taxonomia que o `_seed_catalog` produz. Um teste compara os dois
# resultados: se o seed mudar e isto não, o teste acusa antes de divergirem.
RENAME = ("despensa", "mercearia", "Mercearia")

NEW_COLLECTIONS = (
    # (ref, nome, ordem) — a ordem espelha a enumeração do seed.
    ("combos", "Combos", 8),
    ("mercearia", "Mercearia", 9),
)

MOVES = {
    # Três pães de casca e o pão de hambúrguer, que o dono classificou aqui
    # apesar da massa macia.
    "rusticos": ("FE", "TB", "MIB", "PH"),
    # Buns em pacote, massa enriquecida, na família dos pães japoneses.
    "finos": ("BBB2", "PHO4"),
    # Bundle não é categoria de produto.
    "combos": ("COMBO-PETIT-DEJ",),
}

RETIRE = ("balcao",)


class Command(BaseCommand):
    help = "Extingue 'Balcão', renomeia 'Despensa' para 'Mercearia' e cria 'Combos'."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Mostra o que seria feito, sem gravar nada.",
        )

    def handle(self, *args, **options):
        from shopman.offerman.models import Collection, CollectionItem

        dry_run = options["dry_run"]
        steps: list[str] = []
        warnings: list[str] = []

        with transaction.atomic():
            old_ref, new_ref, new_name = RENAME
            old = Collection.objects.filter(ref=old_ref).first()
            if old and not Collection.objects.filter(ref=new_ref).exists():
                steps.append(
                    f"renomear '{old_ref}' → '{new_ref}' no lugar "
                    f"({old.items.count()} produtos preservados)"
                )
                old.ref, old.name = new_ref, new_name
                old.save(update_fields=["ref", "name"])
            elif old:
                warnings.append(
                    f"'{old_ref}' e '{new_ref}' existem os dois — não mexi. Decida qual fica."
                )

            for ref, name, order in NEW_COLLECTIONS:
                if Collection.objects.filter(ref=ref).exists():
                    continue
                steps.append(f"criar coleção '{ref}' ({name})")
                Collection.objects.create(
                    ref=ref, name=name, sort_order=order, is_active=True
                )

            for target_ref, skus in MOVES.items():
                target = Collection.objects.filter(ref=target_ref).first()
                if target is None:
                    warnings.append(f"coleção destino '{target_ref}' não existe — pulei")
                    continue
                for sku in skus:
                    item = CollectionItem.objects.filter(
                        product__sku=sku
                    ).exclude(collection__ref=target_ref).select_related("collection").first()
                    if item is None:
                        continue
                    steps.append(f"mover {sku}: '{item.collection.ref}' → '{target_ref}'")
                    # Move o vínculo em vez de recriar: preserva is_primary e
                    # qualquer coisa pendurada na linha.
                    item.collection = target
                    item.sort_order = target.items.count()
                    item.save(update_fields=["collection", "sort_order"])

            for ref in RETIRE:
                collection = Collection.objects.filter(ref=ref).first()
                if collection is None:
                    continue
                left = collection.items.count()
                if left:
                    warnings.append(
                        f"'{ref}' ainda tem {left} produto(s) — NÃO apaguei. "
                        "Realoque-os antes, senão eles ficariam sem coleção nenhuma."
                    )
                    continue
                steps.append(f"aposentar coleção '{ref}' (vazia)")
                collection.delete()

            # O ensaio EXECUTA e desfaz, em vez de simular passo a passo. Na
            # primeira versão ele pulava as escritas, e aí cada passo seguinte
            # via o estado velho: o relatório dizia que criaria "Mercearia"
            # logo depois de dizer que renomearia "Despensa" para ela, e não
            # movia o combo porque a coleção destino "ainda não existia".
            # Relatório de ensaio que não reflete a execução é pior que nenhum.
            if dry_run:
                transaction.set_rollback(True)

        self._report(steps, warnings, dry_run=dry_run)

    def _report(self, steps, warnings, *, dry_run):
        if not steps and not warnings:
            self.stdout.write(self.style.SUCCESS(
                "Taxonomia já está aplicada — nada a fazer."
            ))
            return
        verb = "Faria" if dry_run else "Feito"
        self.stdout.write(self.style.SUCCESS(f"{verb} ({len(steps)} passo(s)):"))
        for step in steps:
            self.stdout.write(f"  · {step}")
        for warning in warnings:
            self.stdout.write(self.style.WARNING(f"  ⚠️ {warning}"))
        if dry_run:
            self.stdout.write("\n(--dry-run: nada gravado)")
            return
        self.stdout.write(
            "\nCatálogo apenas: nenhum pedido, sessão ou movimento foi tocado.\n"
            "⚠️ Os feeds exibem por coleção — confira o menu impresso e as TVs."
        )
