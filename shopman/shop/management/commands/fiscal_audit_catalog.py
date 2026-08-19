"""fiscal_audit_catalog — quais vendáveis publicados estão fiscalmente incompletos?

A pergunta que precisa de resposta ANTES do primeiro dia de emissão obrigatória,
não a cada nota recusada. Varre os produtos publicados+vendáveis em vitrine ativa
de canal de venda e lista quem ainda não pode virar item de nota (perfil + NCM;
CEST na revenda), pela mesma função que o porteiro de publicação e o builder
usam (``fiscalman.validate_for_emission``).

Não escreve nada e não depende de adapter fiscal nem da chave do porteiro
(``SHOPMAN_FISCAL_REQUIRE_CLASSIFICATION_ON_PUBLISH``): serve justamente para
saber o que aconteceria ao ligar a chave.

    python manage.py fiscal_audit_catalog
    python manage.py fiscal_audit_catalog --json     # para script/CI
    python manage.py fiscal_audit_catalog --strict   # sai 1 se houver incompleto

Saída vazia == catálogo publicado pronto para emitir.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Lista os vendáveis publicados sem classificação fiscal completa (NFC-e)."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="saída em JSON")
        parser.add_argument(
            "--strict",
            action="store_true",
            help="exit code 1 quando houver produto incompleto (para gate de deploy/CI)",
        )

    def handle(self, *args, **options):
        from shopman.shop.services.fiscal_catalog import (
            incomplete_published_products,
            selling_channel_refs,
        )

        channels = sorted(selling_channel_refs())
        rows = incomplete_published_products()

        if options["json"]:
            self.stdout.write(
                json.dumps(
                    {
                        "channels": channels,
                        "incomplete": [
                            {
                                "sku": row.sku,
                                "name": row.name,
                                "listing_refs": list(row.listing_refs),
                                "errors": list(row.errors),
                            }
                            for row in rows
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif not channels:
            self.stdout.write("Nenhum canal de venda ativo — nada publicado emite nota.")
        elif not rows:
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Todo vendável publicado em {', '.join(channels)} tem classificação fiscal completa."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠️  {len(rows)} vendável(is) publicado(s) sem classificação fiscal completa:"
                )
            )
            for row in rows:
                self.stdout.write(f"  {row.sku} · {row.name} · vitrines: {', '.join(row.listing_refs)}")
                for error in row.errors:
                    self.stdout.write(f"      {error}")
            self.stdout.write(
                "  Classifique em Admin → Produtos → Fiscal (perfil + NCM; CEST na revenda)."
            )

        if options["strict"] and rows:
            raise SystemExit(1)
