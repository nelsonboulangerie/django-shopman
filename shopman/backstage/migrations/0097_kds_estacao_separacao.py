"""A estação "Encomendas" da Cozinha passa a se chamar "Separação" (decisão do dono, 21/11/2026).

"Encomendas" é o nome da lista de encomendas do Gestor, e o cartão do Gestor dizia
"Aguardando Encomendas" para o pedido que esperava esta estação, que é de separação
(tipo ``picking``). O nome passa a dizer o que ela faz, e o ref (o caminho da bancada
no kds-nuxt, ``/<ref>``) acompanha, em inglês: ``preorders`` vira ``picking``.

Pré go-live, rota renomeada não ganha redirect. Conservadora, como a ``0094``: só
renomeia o ref quando o novo ainda não existe, e só troca o nome que ainda é o do seed
("Encomendas"): nome curado pela loja fica.
"""

from django.db import migrations

OLD_REF, NEW_REF = "preorders", "picking"
OLD_NAME, NEW_NAME = "Encomendas", "Separação"


def _move(apps, old_ref, new_ref, old_name, new_name):
    KDSInstance = apps.get_model("backstage", "KDSInstance")
    if KDSInstance.objects.filter(ref=new_ref).exists():
        return
    station = KDSInstance.objects.filter(ref=old_ref).first()
    if station is None:
        return
    station.ref = new_ref
    fields = ["ref"]
    if station.name == old_name:
        station.name = new_name
        fields.append("name")
    station.save(update_fields=fields)


def forwards(apps, schema_editor):
    _move(apps, OLD_REF, NEW_REF, OLD_NAME, NEW_NAME)


def backwards(apps, schema_editor):
    _move(apps, NEW_REF, OLD_REF, NEW_NAME, OLD_NAME)


class Migration(migrations.Migration):

    dependencies = [
        ("backstage", "0096_alter_supportticket_type"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
