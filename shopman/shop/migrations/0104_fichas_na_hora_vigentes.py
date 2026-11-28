"""As fichas montadas na venda viram vigentes e "Na hora" (ADR-040, dono 20/10/2026).

Até aqui a marca era ``Recipe.meta["made_to_order"]`` numa ficha INATIVA: o seed
desligava café, chá e croque para tirá-los do planejamento, e isso sobrepunha
"ficha arquivada" com "montada na venda". Agora:

- ``Recipe.is_active`` volta a querer dizer só vigente × arquivada;
- o modo de produção é o campo ``Recipe.production_mode`` (``craftsman.0019``):
  "Em lote" (o padrão) ou "Na hora".

O que esta migração faz no banco já semeado (o alpha):

- as fichas desta lista (as mesmas 21 que o seed monta na venda) ganham o modo
  "Na hora" e, se estavam inativas SÓ por isso, voltam a vigentes. Se o SKU já
  tem outra ficha vigente, a ficha fica como está (a constraint de uma vigente
  por SKU não se viola) e o log diz qual;
- ``made_to_order`` e ``made_to_order_marked_by`` saem do ``meta`` de TODAS as
  fichas: não há legado antes do go-live;
- a estação de preparo Lanches recebe a coleção Doces, como no seed: o pain
  perdu é "Na hora" e, agora que a estação só recebe item do tipo dela, sem a
  coleção ele ficaria sem estação. O doce de lote continua separação (o reverse
  não tira a coleção: ela pode ter sido escolhida no Admin).

Idempotente. O reverse devolve a lista ao estado da ``shop.0102``: inativa, com
a marca no ``meta``, e o modo de volta a "Em lote".

A lista é a do seed (seção 2b); ``backstage/tests/test_ficha_feita_na_hora.py``
reprova se as duas divergirem.
"""

from django.db import migrations

MIGRATION_NAME = "shop.0104_fichas_na_hora_vigentes"
BATCH = "batch"
MADE_TO_ORDER = "made_to_order"
OLD_META_KEYS = ("made_to_order", "made_to_order_marked_by")
LANCHES_STATION_REF = "lanches"
DOCES_COLLECTION_REF = "doces"

#: Montagem (croques, sanduíches, pain perdu) e bebida: o que se faz quando o
#: cliente pede. As 21 fichas "Na hora" do seed.
MADE_TO_ORDER_RECIPE_REFS = (
    "queijo-quente", "croque-monsieur", "croque-madame", "croque-complet",
    "jambon-beurre", "pain-perdu",
    "espresso", "espresso-macchiato", "cappuccino", "mochaccino", "mocha",
    "caffe-latte", "chocolate-quente",
    "cha-camille", "cha-rouge", "cha-sophie", "cha-bleu", "cha-hibisco",
    "soft-chai-citrico", "vienna-gelado", "cha-tonica-frutas-vermelhas",
)


def forward(apps, schema_editor):
    Recipe = apps.get_model("craftsman", "Recipe")
    cleaned = 0
    for recipe in Recipe.objects.all().only("pk", "meta"):
        meta = dict(recipe.meta or {})
        if not any(key in meta for key in OLD_META_KEYS):
            continue
        for key in OLD_META_KEYS:
            meta.pop(key, None)
        recipe.meta = meta
        recipe.save(update_fields=["meta"])
        cleaned += 1

    activated, kept_archived = [], []
    found = 0
    for recipe in Recipe.objects.filter(ref__in=MADE_TO_ORDER_RECIPE_REFS).order_by("ref"):
        found += 1
        fields = []
        if recipe.production_mode != MADE_TO_ORDER:
            recipe.production_mode = MADE_TO_ORDER
            fields.append("production_mode")
        if not recipe.is_active:
            other = (
                Recipe.objects.filter(output_sku=recipe.output_sku, is_active=True)
                .exclude(pk=recipe.pk)
                .values_list("ref", flat=True)
                .first()
            )
            if other:
                kept_archived.append(f"{recipe.ref} ({recipe.output_sku} já tem {other})")
            else:
                recipe.is_active = True
                fields.append("is_active")
                activated.append(recipe.ref)
        if fields:
            recipe.save(update_fields=fields)
    KDSInstance = apps.get_model("backstage", "KDSInstance")
    Collection = apps.get_model("offerman", "Collection")
    lanches = KDSInstance.objects.filter(ref=LANCHES_STATION_REF, type="prep").first()
    doces = Collection.objects.filter(ref=DOCES_COLLECTION_REF).first()
    station_note = "estação Lanches ausente"
    if lanches is not None and doces is not None:
        if lanches.collections.filter(pk=doces.pk).exists():
            station_note = "Lanches já tinha Doces"
        else:
            lanches.collections.add(doces)
            station_note = "Lanches passou a receber Doces"

    missing = len(MADE_TO_ORDER_RECIPE_REFS) - found
    print(
        f"\n  {MIGRATION_NAME}: {found} fichas Na hora ({len(activated)} voltaram a vigentes), "
        f"{len(kept_archived)} ficaram arquivadas porque o SKU já tem outra vigente "
        f"{kept_archived or ''}, {missing} ausentes; marca antiga limpa em {cleaned} fichas; {station_note}."
    )
    return {"activated": activated, "kept_archived": kept_archived, "cleaned": cleaned}


def backward(apps, schema_editor):
    Recipe = apps.get_model("craftsman", "Recipe")
    for recipe in Recipe.objects.filter(ref__in=MADE_TO_ORDER_RECIPE_REFS, production_mode=MADE_TO_ORDER):
        recipe.production_mode = BATCH
        recipe.is_active = False
        recipe.meta = {**dict(recipe.meta or {}), "made_to_order": True}
        recipe.save(update_fields=["production_mode", "is_active", "meta"])


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0103_catalogimageupload"),
        ("craftsman", "0019_recipe_production_mode"),
        ("backstage", "0093_kdsticket_inicio_do_preparo"),
        ("offerman", "0005_historicalproduct_is_active_product_is_active"),
    ]

    operations = [migrations.RunPython(forward, backward)]
