"""Produz relatório local para revisão humana, sem escrita de catálogo ou HTTP."""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from shopman.shop.services.ifood_catalog_review import build_ifood_catalog_review, validate_review_snapshot


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON com chave repetida.")
        result[key] = value
    return result


def _json_decimal(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError("Tipo não serializável no relatório.")


def _reject_constant(value):
    raise ValueError("JSON com número não finito.")


class Command(BaseCommand):
    help = "Prepara revisão local de snapshot iFood completo e produtos ainda não validados."

    def add_arguments(self, parser):
        parser.add_argument("--snapshot", required=True, help="Envelope JSON local com categorias e respostas completas.")
        parser.add_argument("--channel", required=True, help="Ref do canal local para mostrar ofertas sem alterá-las.")

    def handle(self, *args, **options):
        from shopman.offerman.models import ListingItem, Product

        from shopman.shop.models import Channel

        try:
            with Path(options["snapshot"]).open("rb") as stream:
                raw = stream.read(20 * 1024 * 1024 + 1)
            if len(raw) > 20 * 1024 * 1024:
                raise CommandError("Snapshot excede o limite de 20 MiB.")
            # Preços mantêm precisão decimal, sem arredondamento binário.
            snapshot = json.loads(raw.decode("utf-8"), parse_float=Decimal, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
            validate_review_snapshot(snapshot)
        except (OSError, UnicodeError, ValueError, TypeError, RecursionError):
            raise CommandError("Snapshot inválido ou incompleto. Confira o contrato do guia de revisão.") from None
        try:
            channel = Channel.objects.filter(ref=options["channel"]).first()
            if channel is None:
                raise CommandError("Canal local não encontrado.")
            products = list(Product.objects.only("sku", "name", "short_description", "long_description",
                "image_url", "base_price_q", "is_published", "is_sellable").order_by("sku"))
            local = {p.sku: {"sku": p.sku, "name": p.name, "short_description": p.short_description,
                "long_description": p.long_description, "image_url": p.image_url,
                "base_price_q": p.base_price_q, "is_published": p.is_published,
                "is_sellable": p.is_sellable, "review_status": "unreviewed", "offers": []} for p in products}
            for offer in ListingItem.objects.filter(listing__ref=channel.ref).select_related("product").order_by("product__sku", "min_qty"):
                if offer.product.sku not in local:
                    raise CommandError("O catálogo local mudou durante a leitura. Prepare um novo relatório.")
                local[offer.product.sku]["offers"].append({"min_qty": str(offer.min_qty), "price_q": offer.price_q,
                    "is_published": offer.is_published, "is_sellable": offer.is_sellable})
            result = build_ifood_catalog_review(snapshot=snapshot, products=products, local_details=local)
        except DatabaseError:
            raise CommandError("Não foi possível consultar o catálogo local.") from None
        result["source_file_sha256"] = hashlib.sha256(raw).hexdigest()
        result["local_channel_ref"] = channel.ref
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False, default=_json_decimal))
