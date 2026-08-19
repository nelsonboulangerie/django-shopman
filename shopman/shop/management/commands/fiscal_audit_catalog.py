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
    python manage.py fiscal_audit_catalog --strict   # pré-requisito do flip

``--strict`` é o **pré-requisito documentado** para ligar o porteiro
(procedimento em ``docs/reference/settings.md``, seção "Ligar o porteiro fiscal
do catálogo"). Por isso ele exige as duas coisas, não uma: nenhum incompleto
**e** pelo menos um canal de venda ativo. Auditoria que não varreu nada não
prova nada — sem essa segunda condição bastaria rodar o gate contra um banco sem
canal configurado para colher um verde que não significa "pronto para emitir".
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
            help=(
                "exit code 1 quando houver produto incompleto OU quando não houver canal "
                "de venda ativo para auditar (gate de deploy/CI)"
            ),
        )

    def handle(self, *args, **options):
        from shopman.shop.services.fiscal_catalog import (
            incomplete_published_products,
            selling_channel_refs,
        )

        channels = sorted(selling_channel_refs())
        rows = incomplete_published_products()
        # "Pronto para ligar o porteiro" exige ter varrido algo e não ter achado
        # nada. As duas condições, porque só a segunda é satisfeita à toa.
        ready = bool(channels) and not rows

        if options["json"]:
            self.stdout.write(
                json.dumps(
                    {
                        "channels": channels,
                        "ready_to_enforce": ready,
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
            message = (
                "Nenhum canal de venda ativo — a auditoria não varreu nada, "
                "logo não atesta nada."
            )
            if options["strict"]:
                self.stderr.write(self.style.ERROR(f"❌ {message}"))
            else:
                self.stdout.write(message)
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

        if options["strict"] and not ready:
            raise SystemExit(1)
