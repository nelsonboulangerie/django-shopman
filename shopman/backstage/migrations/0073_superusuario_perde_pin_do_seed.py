"""Apaga o PIN e o crachá que o seed antigo deixou nas contas superusuárias.

Por quê: o seed antigo dava o PIN ``1234`` a TODO usuário, o dono incluído. Entre
o #935 e o #1022 o superusuário não destravava o balcão, então aquele PIN ficou
dormindo. O #1022 devolveu ao superusuário o destrave por PIN e a assinatura de
"Quem autoriza?" — e com isso o ``1234`` do seed voltou a abrir o PDV como dono.

Nenhum PIN de superusuário que existe hoje pode ter sido escolhido pelo dono:

- entre o #935 e o #1022 superusuário não destravava, logo não trocava PIN;
- ``reset_operator_pin`` recusa alvo superusuário;
- o Admin não deixa criar credencial à mão.

Então TODO ``PinCredential`` de superusuário é resíduo do seed, e apagar o
registro inteiro (PIN e crachá) é o conserto. O dono cadastra o dele pelo Admin,
em "Credenciais PIN → Criar ou trocar meu PIN".

É migração de DADOS (``RunPython``), não de schema: nenhuma coluna muda, e a
trava ``migration_safety`` a classifica como aditiva, corretamente — o que ela
apaga é credencial vazada, não dado de que o código em voo dependa. O reverso é
noop: o PIN apagado não volta (nem deve voltar).
"""

from django.db import migrations


def apagar_pin_de_superusuario(apps, schema_editor):
    PinCredential = apps.get_model("doorman", "PinCredential")
    PinCredential.objects.filter(user__is_superuser=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("backstage", "0072_placar_do_de_para"),
        ("doorman", "0005_verificationcode_delivery_started_at"),
    ]

    operations = [
        migrations.RunPython(apagar_pin_de_superusuario, migrations.RunPython.noop),
    ]
