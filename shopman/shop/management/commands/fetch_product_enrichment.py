"""Busca sugestão de catálogo por GTIN para os produtos de revenda.

Grava em ``Product.metadata['enrichment']`` como rascunho `pending`. **Não
altera o produto** — quem aceita é gente, pela ação do Admin.

Uso:
    python manage.py fetch_product_enrichment            # até 25 (cota grátis)
    python manage.py fetch_product_enrichment --sku GL
    python manage.py fetch_product_enrichment --limit 5 --dry-run
    python manage.py fetch_product_enrichment --refetch  # refaz quem já tem
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from shopman.offerman import get_social_attributes
from shopman.offerman.models import Product

from shopman.shop.services.product_enrichment import build_suggestion

# O plano Basic da Cosmos dá 25 consultas/dia, de graça. O teto padrão é esse
# de propósito: quem roda sem pensar não estoura a cota nem descobre isso por
# um HTTP 429 no meio do lote.
COTA_DIARIA_GRATIS = 25


class Command(BaseCommand):
    help = "Sugestão de catálogo (foto, NCM, alérgeno) por GTIN — grava como rascunho."

    def add_arguments(self, parser):
        parser.add_argument("--sku", action="append", default=[], help="Limita a estes SKUs.")
        parser.add_argument("--limit", type=int, default=COTA_DIARIA_GRATIS)
        parser.add_argument("--refetch", action="store_true", help="Refaz quem já tem rascunho.")
        parser.add_argument("--dry-run", action="store_true", help="Mostra e não grava.")

    def handle(self, *args, **opts):
        skus, limite = opts["sku"], opts["limit"]
        refetch, dry = opts["refetch"], opts["dry_run"]

        qs = Product.objects.filter(sku__in=skus) if skus else Product.objects.all()

        alvos = []
        for p in qs.order_by("sku"):
            gtin = get_social_attributes(p).gtin
            if not gtin:
                continue
            # Aceito não se mexe: reconsultar sobrescreveria a decisão de quem
            # conferiu o rótulo com o pote na mão.
            atual = (p.metadata or {}).get("enrichment") or {}
            if atual.get("status") == "accepted" and not refetch:
                continue
            if atual.get("status") == "pending" and not refetch:
                continue
            alvos.append((p, gtin))

        if not alvos:
            self.stdout.write("Nada a buscar: nenhum produto com GTIN pendente.")
            self._dica_gtin(qs)
            return

        if len(alvos) > limite:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(alvos)} produtos elegíveis; buscando {limite} "
                    f"(cota grátis da Cosmos é {COTA_DIARIA_GRATIS}/dia). "
                    "Rode de novo amanhã ou use --limit."
                )
            )
            alvos = alvos[:limite]

        achou = vazio = 0
        for produto, gtin in alvos:
            s = build_suggestion(gtin)
            if s.is_empty():
                vazio += 1
                self.stdout.write(f"  {produto.sku:14} {gtin:15} nada encontrado")
                continue
            achou += 1
            fontes = "+".join(s.sources) or "—"
            self.stdout.write(
                f"  {produto.sku:14} {gtin:15} {fontes:22} "
                f"foto={'sim' if s.image_url else 'não':3} ncm={s.ncm or '—':10} "
                f"alérgenos={s.allergens or '—'}"
            )
            for nota in s.notes:
                self.stdout.write(self.style.WARNING(f"      ⚠️  {nota}"))
            if not dry:
                meta = dict(produto.metadata or {})
                meta["enrichment"] = s.to_metadata()
                produto.metadata = meta
                produto.save(update_fields=["metadata"])

        self.stdout.write("")
        acao = "encontrados (nada gravado, --dry-run)" if dry else "gravados como rascunho"
        self.stdout.write(self.style.SUCCESS(f"{achou} {acao}; {vazio} sem retorno."))
        if achou and not dry:
            self.stdout.write("Aceite no Admin: nada disso entra no produto sozinho.")

    def _dica_gtin(self, qs):
        """Sem GTIN não há o que consultar — dizer isso vale mais que o silêncio."""
        sem = [
            p.sku
            for p in qs.order_by("sku")
            if not get_social_attributes(p).gtin
        ]
        if sem:
            self.stdout.write(
                f"\n{len(sem)} produto(s) sem GTIN cadastrado — preencha em "
                "Admin → Produto → Social/PIM para que possam ser consultados:"
            )
            self.stdout.write("  " + " ".join(sem[:25]) + (" …" if len(sem) > 25 else ""))
