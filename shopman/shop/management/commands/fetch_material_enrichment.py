"""Prepara rascunhos de insumo por GTIN, sem aceitar nenhum campo."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from shopman.buyman.models import Material
from shopman.offerman import gtin_is_valid

from shopman.shop.services import material_enrichment
from shopman.shop.services.gtin_enrichment import SOURCE_NFE, build_suggestion

FREE_DAILY_LIMIT = 25


class Command(BaseCommand):
    help = (
        "Consulta fontes por GTIN para insumos. O padrão é dry-run; --stage grava "
        "somente o rascunho pendente."
    )

    def add_arguments(self, parser):
        parser.add_argument("--sku", action="append", default=[], help="Limita a estes SKUs.")
        parser.add_argument("--limit", type=int, default=FREE_DAILY_LIMIT)
        parser.add_argument("--refetch", action="store_true", help="Refaz quem já tem rascunho.")
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--stage", action="store_true", help="Grava somente o rascunho pendente.")
        mode.add_argument(
            "--dry-run",
            action="store_true",
            help="Só mostra o resultado (é o padrão; ainda consome consulta externa).",
        )

    def handle(self, *args, **options):
        queryset = Material.objects.filter(is_active=True)
        if options["sku"]:
            queryset = queryset.filter(sku__in=options["sku"])

        targets: list[tuple[Material, str]] = []
        invalid: list[str] = []
        for material in queryset.order_by("sku"):
            current = material_enrichment.draft(material)
            gtin = str((material.metadata or {}).get("gtin") or current.get("gtin") or "").strip()
            if not gtin:
                continue
            if not gtin_is_valid(gtin):
                invalid.append(f"{material.sku}={gtin}")
                continue
            consulted = set(current.get("sources") or []) - {SOURCE_NFE}
            if (consulted or current.get("notes")) and not options["refetch"]:
                continue
            targets.append((material, gtin))

        for item in invalid:
            self.stderr.write(self.style.ERROR(f"GTIN inválido, não consultado: {item}"))

        if not targets:
            self.stdout.write("Nada a buscar: nenhum insumo elegível com GTIN válido.")
            return

        limit = max(options["limit"], 0)
        if len(targets) > limit:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(targets)} insumos elegíveis; consultando {limit}. "
                    f"A cota grátis da Cosmos é {FREE_DAILY_LIMIT}/dia."
                )
            )
            targets = targets[:limit]

        found = empty = 0
        for material, gtin in targets:
            suggestion = build_suggestion(gtin)
            if suggestion.is_empty():
                empty += 1
            else:
                found += 1
            sources = "+".join(suggestion.sources) or "sem retorno"
            self.stdout.write(
                f"{material.sku} {gtin} {sources} "
                f"campos={','.join(suggestion.fields) or 'nenhum'}"
            )
            if options["stage"]:
                material.metadata = material_enrichment.merge_into_metadata(
                    material.metadata, suggestion
                )
                material.save(update_fields=["metadata", "updated_at"])

        mode = "rascunhos preparados" if options["stage"] else "dry-run, nada gravado"
        self.stdout.write(self.style.SUCCESS(f"{found} com dados; {empty} sem retorno; {mode}."))
        if options["stage"]:
            self.stdout.write(
                "Nenhum campo foi aceito. Revise cada insumo no Admin antes de aplicar."
            )
