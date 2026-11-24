"""As palavras-chave dos produtos, que a Concierge usa para achar o produto chamado por
outro nome (dono, 24/11/2026: "Folhado de maçã se refere claramente ao Chausson").

Sem ``--write`` só lê: quantos produtos publicados têm palavras-chave, quais não têm, e o
que a proposta (``concierge/keywords_proposal.json``) acrescentaria ou tiraria em cada um.
Com ``--write`` grava a proposta. No ar, ``--write`` só com a aprovação do dono.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

PROPOSAL = Path(__file__).resolve().parents[2] / "concierge" / "keywords_proposal.json"


class Command(BaseCommand):
    help = "Levanta as palavras-chave dos produtos e mostra (ou grava, com --write) a proposta da Concierge."

    def add_arguments(self, parser):
        parser.add_argument("--proposal", default=str(PROPOSAL), help="Arquivo da proposta (JSON).")
        parser.add_argument("--write", action="store_true", help="Grava a proposta. Sem isto, só mostra.")

    def handle(self, *args, **options):
        from shopman.offerman.models import Product

        proposal = json.loads(Path(options["proposal"]).read_text(encoding="utf-8"))["products"]
        products = list(Product.objects.filter(is_published=True).prefetch_related("keywords").order_by("sku"))
        tagged = {product.sku: sorted(tag.name for tag in product.keywords.all()) for product in products}
        without = [product for product in products if not tagged[product.sku]]
        out = self.stdout.write
        out(f"{len(products)} produto(s) publicado(s): {len(products) - len(without)} com palavras-chave, "
            f"{len(without)} sem.")
        for product in without:
            out(f"  sem palavras-chave: {product.sku} | {product.name}")

        by_sku = {product.sku: product for product in products}
        changes = 0
        with transaction.atomic():
            for sku, entry in proposal.items():
                product = by_sku.get(sku)
                if product is None:
                    out(f"  {sku}: não está publicado aqui, nada a fazer")
                    continue
                have = set(tagged[sku])
                add = [word for word in entry.get("add", ()) if word not in have]
                remove = [word for word in entry.get("remove", ()) if word in have]
                if not add and not remove:
                    continue
                changes += 1
                out(f"  {sku} | {product.name}: + {', '.join(add) or '-'}  |  - {', '.join(remove) or '-'}")
                if options["write"]:
                    if add:
                        product.keywords.add(*add)
                    if remove:
                        product.keywords.remove(*remove)
        verb = "gravado(s)" if options["write"] else "mudaria(m); nada gravado (use --write)"
        out(f"{changes} produto(s) {verb}.")
