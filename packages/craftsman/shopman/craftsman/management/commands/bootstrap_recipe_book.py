"""Cria no inventário de receitas uma entry por ficha técnica que já existe.

Idempotente: ficha que já tem entry (mesmo ``ref``) é pulada. A ordem respeita a
dependência: a ficha de uma parte (LEVAIN, PASTA-AUTOLIZADA...) vira entry
antes da massa que a consome, para a massa apontar ``entry_ref`` que existe.

Uso:
    python manage.py bootstrap_recipe_book
    python manage.py bootstrap_recipe_book --dry-run
"""

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Cria uma entry no inventário de receitas para cada ficha técnica existente (idempotente)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra o que faria sem gravar nada.",
        )

    def handle(self, *args, **options):
        from shopman.craftsman.models import Recipe, RecipeEntry
        from shopman.craftsman.services.recipe_book import bootstrap_entry_from_recipe

        dry_run = options["dry_run"]
        recipes = list(Recipe.objects.order_by("pk").prefetch_related("items"))
        existing_refs = set(RecipeEntry.objects.values_list("ref", flat=True))

        created, skipped = 0, 0
        with transaction.atomic():
            for recipe in _dependency_order(recipes):
                if recipe.ref in existing_refs:
                    skipped += 1
                    continue
                entry = bootstrap_entry_from_recipe(recipe)
                if entry is None:
                    skipped += 1
                    # O motivo importa: sem unidade declarada, a ficha fica fora E
                    # quem a consome a vê como insumo opaco (a farinha dela não entra
                    # na base). O conserto é declarar `Recipe.meta["output_unit"]`.
                    reason = (
                        "inativa" if not recipe.is_active
                        else "sem unidade de saída declarada; defina Recipe.meta['output_unit'] "
                             "(as massas que a usam ficaram com ela como insumo opaco)"
                    )
                    self.stdout.write(f"  - {recipe.ref}: pulada ({reason})")
                    continue
                created += 1
                existing_refs.add(entry.ref)
                self.stdout.write(f"  + {recipe.ref}: entry criada (versão 1 publicada)")
            if dry_run:
                transaction.set_rollback(True)

        suffix = " (dry-run: nada gravado)" if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"Receitas: {created} criadas, {skipped} puladas{suffix}"))


def _dependency_order(recipes):
    """Fichas ordenadas para que quem produz um insumo venha antes de quem o consome."""
    by_output = {}
    for recipe in recipes:
        if recipe.is_active and recipe.output_sku:
            by_output.setdefault(recipe.output_sku, recipe)

    ordered, visited, visiting = [], set(), set()

    def visit(recipe):
        if recipe.pk in visited:
            return
        if recipe.pk in visiting:
            return  # ciclo: a ficha de baixo já está a caminho; a ordem por pk resolve o resto
        visiting.add(recipe.pk)
        for item in recipe.items.all():
            dependency = by_output.get(item.input_sku)
            if dependency is not None and dependency.pk != recipe.pk:
                visit(dependency)
        visiting.discard(recipe.pk)
        visited.add(recipe.pk)
        ordered.append(recipe)

    for recipe in recipes:
        visit(recipe)
    return ordered
