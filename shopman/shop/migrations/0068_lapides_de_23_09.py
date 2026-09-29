"""As oito lápides da leva de 23/09/2026 — o que a loja responde nesses endereços.

A curadoria apagou oito produtos no mesmo dia em que os códigos mudaram.
Apagado não deixa rastro: sem esta lista, o endereço que o Google indexou
responderia 404 mudo, e não "saiu do cardápio, veja a prateleira de onde ele
veio". As coleções vieram da sessão que apagou, com o catálogo ainda na mão.

`COMBO-PETIT-DEJ` fica sem coleção de propósito: ele era o único item de
"Combos", que ficou vazia.

Daqui para a frente a lápide nasce no mesmo `atomic()` do delete, via
`shop.services.retired_urls.record` — esta migração é só a dívida de hoje.
"""

from django.db import migrations

LAPIDES = [
    ("COAD", "bebidas-quentes", "Café Coado"),
    ("CE", "bebidas-geladas", "Coffee Float"),
    ("PU", "doces", "Purin à la Mode"),
    ("TJ", "doces", "Tea Jelly"),
    ("PG", "salgados", "Pain Grillé"),
    ("TABUA", "salgados", "Tábua de Iguarias da Casa"),
    ("GL", "mercearia", "Geleia St. Dalfour (mini) — substituída por duas geleias novas"),
    ("COMBO-PETIT-DEJ", "", "Combo Petit Déjeuner — a coleção Combos ficou vazia"),
]


def semeia(apps, schema_editor):
    RetiredProduct = apps.get_model("shop", "RetiredProduct")
    Product = apps.get_model("offerman", "Product")
    vivos = set(Product.objects.values_list("sku", flat=True))
    for sku, collection_ref, note in LAPIDES:
        # Produto que voltou a existir não tem lápide: a página dele responde.
        if sku in vivos:
            continue
        RetiredProduct.objects.update_or_create(
            sku=sku,
            defaults={"collection_refs": collection_ref, "note": note},
        )


def remove(apps, schema_editor):
    RetiredProduct = apps.get_model("shop", "RetiredProduct")
    RetiredProduct.objects.filter(sku__in=[sku for sku, _c, _n in LAPIDES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0067_lapide_do_produto_apagado"),
        ("offerman", "0001_initial"),
    ]

    operations = [migrations.RunPython(semeia, remove)]
