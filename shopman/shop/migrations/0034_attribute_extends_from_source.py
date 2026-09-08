"""O vocabulário de alérgeno nasce da CADEIA DE INSUMOS, não da lei.

A lista fechada que a 0033 introduziu tinha um defeito grave: um insumo que
declarasse alérgeno fora dela fazia o `dietary_from_recipe` **explodir**, e o
produto ficava sem alérgeno nenhum — o oposto exato do que a lista existia para
proteger.

O caso real desta casa é a **pimenta preta**: a ANVISA não a lista, a casa a
usa, e já houve reação. Um alérgeno que o insumo conhece precisa correr toda a
cadeia até o rótulo, e nenhuma lista pode barrá-lo no meio.

Com este campo, valor vindo da FICHA amplia o vocabulário (marcado para
revisão no Admin) em vez de ser recusado. Valor digitado à MÃO continua sendo
recusado: ali o erro provável é de digitação, não um alérgeno novo do mundo.
"""

from django.db import migrations, models


def liga_alergenos(apps, schema_editor):
    AttributeDefinition = apps.get_model("shop", "AttributeDefinition")
    AttributeDefinition.objects.filter(ref="alergenos").update(extends_from_source=True)


def desliga_alergenos(apps, schema_editor):
    AttributeDefinition = apps.get_model("shop", "AttributeDefinition")
    AttributeDefinition.objects.filter(ref="alergenos").update(extends_from_source=False)


class Migration(migrations.Migration):
    dependencies = [("shop", "0033_rename_legacy_attribute_keys")]

    operations = [
        migrations.AddField(
            model_name="attributedefinition",
            name="extends_from_source",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Valor vindo da FICHA TÉCNICA que não está nas opções é ACEITO e "
                    "vira opção nova, para revisão. Só para atributo cujo vocabulário "
                    "nasce da cadeia de insumos, como alérgenos."
                ),
                verbose_name="a cadeia pode ampliar",
            ),
        ),
        # Só `alergenos`: `dieta` é vocabulário da casa e fecha de propósito.
        migrations.RunPython(liga_alergenos, desliga_alergenos),
    ]
