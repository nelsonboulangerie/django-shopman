"""Cobertura e validação local do enriquecimento de insumos."""

from __future__ import annotations

import json
from dataclasses import asdict

from django.core.management.base import BaseCommand, CommandError

from shopman.shop.services.material_enrichment import coverage_report


class Command(BaseCommand):
    help = "Mede perfis de insumo, receitas deriváveis e receitas a uma declaração de derivar."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Emite JSON estável.")
        parser.add_argument("--strict", action="store_true", help="Falha se houver dado inválido.")

    def handle(self, *args, **options):
        report = coverage_report()
        if options["json"]:
            self.stdout.write(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))
        else:
            self.stdout.write(
                f"Insumos usados em fichas com perfil declarado: "
                f"{report.declared_materials}/{report.recipe_materials}."
            )
            self.stdout.write(
                f"Receitas deriváveis: {report.derivable_recipes}/{report.recipes}. "
                f"Rascunhos pendentes: {report.staged_materials}."
            )
            if report.one_missing:
                self.stdout.write("Receitas a um insumo de derivar:")
                for row in report.one_missing:
                    self.stdout.write(
                        f"  {row.ref} ({row.output_sku}): {', '.join(row.missing_materials)}"
                    )
            if report.invalid:
                self.stderr.write("Dados inválidos:")
                for issue in report.invalid:
                    self.stderr.write(f"  {issue}")
        if options["strict"] and report.invalid:
            raise CommandError(f"{len(report.invalid)} problema(s) de validação.")
