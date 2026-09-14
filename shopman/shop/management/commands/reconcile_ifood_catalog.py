"""Reconcilia um snapshot local sem alterar cadastro ou consultar o iFood."""

import json
from dataclasses import asdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from shopman.shop.services.ifood_catalog_reconciliation import reconcile_ifood_inventory


class Command(BaseCommand):
    help = "Compare inventário JSON iFood com SKUs canônicos, somente leitura."

    def add_arguments(self, parser):
        parser.add_argument("--inventory", required=True, help="Arquivo JSON de categorias com itens.")
        parser.add_argument("--merchant-id", required=True, help="Loja de origem do snapshot.")
        parser.add_argument("--catalog-id", required=True, help="Catálogo de origem do snapshot.")
        parser.add_argument("--context", required=True, help="Contexto de origem, por exemplo DEFAULT.")

    def handle(self, *args, **options):
        from shopman.offerman.models import Product

        try:
            path = Path(options["inventory"])
            if not path.is_file():
                raise CommandError("Inventário deve ser um arquivo JSON local existente.")
            categories = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, RecursionError):
            raise CommandError("Não foi possível ler o inventário como JSON UTF-8 válido.") from None

        scope = {
            "merchant_id": options["merchant_id"],
            "catalog_id": options["catalog_id"],
            "context": options["context"],
            "categories": categories,
        }
        try:
            # Valida entrada antes de consultar o cadastro; não inspeciona credenciais.
            reconcile_ifood_inventory(**scope, products=[])
            products = list(Product.objects.only("sku", "name").order_by("sku"))
            result = reconcile_ifood_inventory(**scope, products=products)
        except ValueError as exc:
            raise CommandError(str(exc)) from None
        except DatabaseError:
            raise CommandError("Não foi possível consultar os produtos canônicos.") from None
        self.stdout.write(json.dumps(asdict(result), ensure_ascii=False, indent=2))
