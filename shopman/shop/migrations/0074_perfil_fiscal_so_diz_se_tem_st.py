"""O perfil fiscal passa a responder uma pergunta só: a tributação tem ST ou não.

Eram três perfis — ``own_production``, ``resale_common`` e ``resale`` — e os
dois primeiros só diferiam no CEST: um o recusava, o outro o levava. Mas o
CEST não é tributação, é **identificação da mercadoria** no catálogo de
segmentos do Conv. ICMS 142/2018, e a lei manda informá-lo sempre que o item
estiver listado, com ou sem ST (cl. 20ª, I; RICMS/PR, Anexo X, art. 1º).
O CEST virou atributo do produto; o perfil ficou com a tributação:

- ``own_production`` e ``resale_common`` → ``standard`` (102/5102);
- ``resale`` → ``tax_substitution`` (500/5405).

Pré-go-live: sem alias, sem resíduo (decisão do dono, 24/09/2026).
"""

from django.db import migrations

RENAMED = {"own_production": "standard", "resale_common": "standard", "resale": "tax_substitution"}


def forward(apps, schema_editor):
    Product = apps.get_model("offerman", "Product")
    for product in Product.objects.filter(metadata__has_key="fiscal").only("pk", "metadata"):
        metadata = dict(product.metadata or {})
        fiscal = metadata.get("fiscal")
        if not isinstance(fiscal, dict) or fiscal.get("profile") not in RENAMED:
            continue
        metadata["fiscal"] = {**fiscal, "profile": RENAMED[fiscal["profile"]]}
        Product.objects.filter(pk=product.pk).update(metadata=metadata)


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0073_revenda_vira_cadastro_de_compra"),
        ("offerman", "0004_is_sellable_decisao_de_vender"),
    ]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
