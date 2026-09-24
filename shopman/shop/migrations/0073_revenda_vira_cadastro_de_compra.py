"""A revenda deixa de ser marca no produto e vira cadastro de compra do mesmo SKU.

Até aqui, "a casa compra este produto pronto" era a marca
``Product.metadata['purchase']['resale']``, e o Compras recebia a nota apontando
a linha para o produto. Isso deixava a revenda sem custo por fornecedor, sem
conversão, sem mínimo, sem pedido e sem contagem — tudo que pendura no
cadastro de compra (``buyman.Material``).

Decisão do dono (24/09/2026): *comprável* é ter cadastro no Compras; *vendável*
é decisão explícita. A coisa comprada que também se vende tem os dois
cadastros com o mesmo SKU, e o mesmo estoque.

Esta migração, para cada produto com a marca:

1. cria o ``Material`` do mesmo SKU (nome, unidade e validade do produto), ou
   reativa o que existia inativo — exceto quando há ficha ativa produzindo o
   SKU (é produzido aqui; o estoque entra pela Produção);
2. apaga a marca (zero resíduo);

e reescreve o de-para de nota dos fornecedores que apontava para o produto
(``{"productSku": X}``) para apontar para o cadastro de compra
(``{"materialSku": X}``) — mesmo SKU, mesma coisa.

O estoque não se move: ele já é do SKU, e o SKU é o mesmo.
"""

from django.db import migrations
from shopman.utils.units import normalize

MATERIAL_UNITS = {"un", "kg", "g", "l", "ml"}
INVOICE_PRODUCT_MAP_KEYS = ("invoice_product_map", "nfe_product_map", "invoiceProducts", "nfeProducts")


def _without_resale_mark(metadata):
    metadata = dict(metadata)
    purchase = dict(metadata.get("purchase") or {})
    purchase.pop("resale", None)
    if purchase:
        metadata["purchase"] = purchase
    else:
        metadata.pop("purchase", None)
    return metadata


def _rewrite_map(mapping):
    changed = False
    rewritten = {}
    for code, entry in mapping.items():
        if isinstance(entry, dict) and not entry.get("materialSku"):
            sku = entry.get("productSku") or entry.get("product_sku")
            if sku:
                entry = {"materialSku": sku, "conversionLabel": entry.get("conversionLabel") or ""}
                changed = True
        rewritten[code] = entry
    return rewritten, changed


def forward(apps, schema_editor):
    Product = apps.get_model("offerman", "Product")
    Material = apps.get_model("buyman", "Material")
    Recipe = apps.get_model("craftsman", "Recipe")
    Supplier = apps.get_model("buyman", "Supplier")

    produced = set(Recipe.objects.filter(is_active=True).values_list("output_sku", flat=True))
    for product in Product.objects.filter(metadata__purchase__resale=True):
        if product.sku not in produced:
            unit = normalize(product.unit)
            if unit not in MATERIAL_UNITS:
                raise RuntimeError(
                    f"{product.sku}: unidade '{product.unit}' não serve para o cadastro de compra. "
                    "Acerte a unidade do produto e rode a migração de novo."
                )
            material = Material.objects.filter(sku=product.sku).first()
            if material is None:
                Material.objects.create(
                    sku=product.sku,
                    name=product.name,
                    unit=unit,
                    shelf_life_days=product.shelf_life_days,
                )
            elif not material.is_active:
                material.is_active = True
                material.save(update_fields=["is_active", "updated_at"])
        product.metadata = _without_resale_mark(product.metadata or {})
        product.save(update_fields=["metadata"])

    for supplier in Supplier.objects.all():
        metadata = dict(supplier.metadata or {})
        purchase = dict(metadata.get("purchase") or {})
        changed = False
        for scope in (purchase, metadata):
            for key in INVOICE_PRODUCT_MAP_KEYS:
                if isinstance(scope.get(key), dict):
                    scope[key], touched = _rewrite_map(scope[key])
                    changed = changed or touched
        if changed:
            if purchase:
                metadata["purchase"] = purchase
            supplier.metadata = metadata
            supplier.save(update_fields=["metadata"])


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0072_pao_pede_mercearia"),
        ("offerman", "0003_collection_metadata"),
        ("buyman", "0011_alter_material_sku"),
        ("craftsman", "0013_remove_recipeitem_craft_recipeitem_usable_pct_range_and_more"),
    ]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
