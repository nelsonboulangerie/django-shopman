"""As fichas feitas na hora ganham a marca no banco já semeado (ADR-040).

O #1942 ligou a baixa de insumo na venda do item feito na hora, mas a marca
``Recipe.meta["made_to_order"] = true`` nasceu só no seed: no banco que já
existia nenhuma ficha a tem, e a venda não baixa nada. Reseed não é o caminho
(pede a palavra do dono); esta migração escreve a mesma marca nas MESMAS fichas
que o seed marca, pelo ``ref``.

Regras:

- só a marca: nenhum outro campo da ficha muda;
- ficha que não existe fica de fora, sem erro (banco novo, ficha apagada);
- ficha ATIVA fica de fora: ficha ativa é fornada (``craft.suggest`` a lê), e
  marcá-la faria a venda baixar o que a fornada já baixa;
- ficha que já tem a marca fica como está (idempotente);
- a ficha que ESTA migração marcou leva ``made_to_order_marked_by`` com o nome
  dela, e o reverse desmarca só essas. A marca que veio do seed ou do Admin
  sobrevive ao reverse.

A lista é a do seed (seção 2b); ``backstage/tests/test_ficha_feita_na_hora.py``
reprova se as duas divergirem.
"""

from django.db import migrations

MIGRATION_NAME = "shop.0102_fichas_feitas_na_hora"
MARK_KEY = "made_to_order"
MARKED_BY_KEY = "made_to_order_marked_by"

#: Montagem (croques, sanduíches, pain perdu) e bebida: o que se faz quando o
#: cliente pede. As 21 fichas que o seed marca.
MADE_TO_ORDER_RECIPE_REFS = (
    "queijo-quente", "croque-monsieur", "croque-madame", "croque-complet",
    "jambon-beurre", "pain-perdu",
    "espresso", "espresso-macchiato", "cappuccino", "mochaccino", "mocha",
    "caffe-latte", "chocolate-quente",
    "cha-camille", "cha-rouge", "cha-sophie", "cha-bleu", "cha-hibisco",
    "soft-chai-citrico", "vienna-gelado", "cha-tonica-frutas-vermelhas",
)


def mark(apps, schema_editor):
    Recipe = apps.get_model("craftsman", "Recipe")
    marked, already, active = [], [], []
    for recipe in Recipe.objects.filter(ref__in=MADE_TO_ORDER_RECIPE_REFS).order_by("ref"):
        meta = dict(recipe.meta or {})
        if meta.get(MARK_KEY) is True:
            already.append(recipe.ref)
            continue
        if recipe.is_active:
            active.append(recipe.ref)
            continue
        meta[MARK_KEY] = True
        meta[MARKED_BY_KEY] = MIGRATION_NAME
        recipe.meta = meta
        recipe.save(update_fields=["meta"])
        marked.append(recipe.ref)
    missing = len(MADE_TO_ORDER_RECIPE_REFS) - len(marked) - len(already) - len(active)
    print(
        f"\n  {MIGRATION_NAME}: {len(marked)} fichas marcadas como feitas na hora, "
        f"{len(already)} já marcadas, {len(active)} ativas deixadas de fora "
        f"{active or ''}, {missing} ausentes (de {len(MADE_TO_ORDER_RECIPE_REFS)})."
    )
    return marked


def unmark(apps, schema_editor):
    Recipe = apps.get_model("craftsman", "Recipe")
    for recipe in Recipe.objects.filter(ref__in=MADE_TO_ORDER_RECIPE_REFS):
        meta = dict(recipe.meta or {})
        if meta.get(MARKED_BY_KEY) != MIGRATION_NAME:
            continue
        meta.pop(MARK_KEY, None)
        meta.pop(MARKED_BY_KEY, None)
        recipe.meta = meta
        recipe.save(update_fields=["meta"])


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0101_confirmado_diz_a_data_da_encomenda"),
        ("craftsman", "0017_abertura_fechamento_labels"),
    ]

    operations = [migrations.RunPython(mark, unmark)]
