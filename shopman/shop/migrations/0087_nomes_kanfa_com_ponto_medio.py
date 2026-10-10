# Nomes dos chás Kãnfa com ponto médio, e o hint do defeito "Contaminado" sem travessão.
#
# Decisão do dono (03/10/2026): nos nomes de produto, o travessão que separa o produto
# da embalagem vira ponto médio ("Chalosofia Kãnfa · Lata 50g"), o separador que a casa
# já usa. O hint do "Contaminado" é texto de defeito, não nome: ganha a pontuação do
# sentido ("Matéria estranha: não vende").
#
# O seed já nasce com o texto novo; esta migração leva o mesmo texto ao banco vivo.
# Só reescreve a linha que ainda carrega EXATAMENTE o texto antigo do seed: nome ou
# hint editado à mão fica como está. O nome do produto é também o do cadastro de compra
# do mesmo SKU (``buyman.Material``, criado a partir do produto), e os dois andam juntos
# pela mesma regra. Reversível pela mesma tabela.

from django.db import migrations

# sku: tipo e gramatura da embalagem; o nome antigo é "<produto> — <embalagem>".
KANFA = {
    "CHA-ACONCHEGO-KANFA-L50": ("Aconchego Chai Kãnfa", "Lata 50g"),
    "CHA-ACONCHEGO-KANFA-P50": ("Aconchego Chai Kãnfa", "Pouch 50g"),
    "CHA-INTIMIDADE-KANFA-L50": ("Intimidade Kãnfa", "Lata 50g"),
    "CHA-INTIMIDADE-KANFA-P50": ("Intimidade Kãnfa", "Pouch 50g"),
    "CHA-INTUICAO-KANFA-L70": ("Intuição Chai Kãnfa", "Lata 70g"),
    "CHA-INTUICAO-KANFA-P50": ("Intuição Chai Kãnfa", "Pouch 50g"),
    "CHA-MAMA-KANFA-L70": ("Mama Chai Kãnfa", "Lata 70g"),
    "CHA-MAMA-KANFA-P50": ("Mama Chai Kãnfa", "Pouch 50g"),
    "CHA-NAMASTE-KANFA-L70": ("Namastê Chai Kãnfa", "Lata 70g"),
    "CHA-NAMASTE-KANFA-P50": ("Namastê Chai Kãnfa", "Pouch 50g"),
    "CHA-CHALOSOFIA-KANFA-L50": ("Chalosofia Kãnfa", "Lata 50g"),
    "CHA-CHALOSOFIA-KANFA-P50": ("Chalosofia Kãnfa", "Pouch 50g"),
    "CHA-VITAL-KANFA-L70": ("Vital Chai Kãnfa", "Lata 70g"),
    "CHA-VITAL-KANFA-P50": ("Vital Chai Kãnfa", "Pouch 50g"),
}

NAMES = {sku: (f"{name} — {pack}", f"{name} · {pack}") for sku, (name, pack) in KANFA.items()}

HINTS = {
    # ref: (antes, depois)
    "contaminated": ("Matéria estranha — não vende", "Matéria estranha: não vende"),
}


def _rewrite(apps, direction):
    pick = (lambda pair: pair) if direction == "forwards" else (lambda pair: pair[::-1])
    for app_label, model_name in (("offerman", "Product"), ("buyman", "Material")):
        model = apps.get_model(app_label, model_name)
        for sku, pair in NAMES.items():
            source, target = pick(pair)
            model.objects.filter(sku=sku, name=source).update(name=target)
    QualityDefect = apps.get_model("shop", "QualityDefect")
    for ref, pair in HINTS.items():
        source, target = pick(pair)
        QualityDefect.objects.filter(ref=ref, hint=source).update(hint=target)


def forwards(apps, schema_editor):
    _rewrite(apps, "forwards")


def backwards(apps, schema_editor):
    _rewrite(apps, "backwards")


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0086_superficie_central"),
        ("offerman", "0004_is_sellable_decisao_de_vender"),
        ("buyman", "0011_alter_material_sku"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
