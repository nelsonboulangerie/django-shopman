"""O perfil fiscal volta a separar quem fez o que se vende: três perfis.

O ``standard`` (0074) juntava produção própria e revenda sem ST no mesmo CFOP
5102. Mas o CFOP é tributação da operação e diz quem produziu: produção do
estabelecimento é **5101**, mercadoria de terceiros é **5102**, e com ST
**5405** (24/09/2026). O CEST segue atributo do produto, em todos.

- ``standard`` → ``own_production`` quando o SKU tem ficha ativa (é produzido
  aqui) ou não tem cadastro de compra ativo (pão, bebida preparada, caixa
  presente); → ``resale`` quando é comprado pronto (cadastro de compra ativo e
  nenhuma ficha ativa produzindo o SKU);
- ``tax_substitution`` → ``resale_tax_substitution``.

Pré-go-live: zero resíduo, sem alias.
"""

from django.db import migrations


def forward(apps, schema_editor):
    Product = apps.get_model("offerman", "Product")
    Material = apps.get_model("buyman", "Material")
    Recipe = apps.get_model("craftsman", "Recipe")

    produced = set(Recipe.objects.filter(is_active=True).values_list("output_sku", flat=True))
    purchasable = set(Material.objects.filter(is_active=True).values_list("sku", flat=True))

    for product in Product.objects.filter(metadata__has_key="fiscal").only("pk", "sku", "metadata"):
        metadata = dict(product.metadata or {})
        fiscal = metadata.get("fiscal")
        if not isinstance(fiscal, dict):
            continue
        profile = fiscal.get("profile")
        if profile == "tax_substitution":
            new = "resale_tax_substitution"
        elif profile == "standard":
            bought_ready = product.sku in purchasable and product.sku not in produced
            new = "resale" if bought_ready else "own_production"
        else:
            continue
        metadata["fiscal"] = {**fiscal, "profile": new}
        Product.objects.filter(pk=product.pk).update(metadata=metadata)


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0074_perfil_fiscal_so_diz_se_tem_st"),
        ("offerman", "0004_is_sellable_decisao_de_vender"),
        ("buyman", "0011_alter_material_sku"),
        ("craftsman", "0013_remove_recipeitem_craft_recipeitem_usable_pct_range_and_more"),
    ]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
