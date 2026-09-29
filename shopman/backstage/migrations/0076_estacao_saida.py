"""A estação "Expedição" do KDS passa a se chamar "Saída" (decisão do dono, 26/09/2026).

"Expedição" é o fechamento de lote da Produção; a estação do KDS por onde o
pedido pronto sai ganha nome próprio. O ``type`` gravado continua
``expedition`` (identificador interno, em inglês) — muda o rótulo da escolha.

A estação que o seed criou (ref ``expedicao``) é renomeada aqui, e não por
reseed: o alpha tem dados vivos. Idempotente e conservadora:

- só renomeia quando ``expedicao`` existe e ``saida`` ainda não (se as duas
  existem, alguém já criou a nova à mão, e apagar a antiga seria decisão dele);
- o NOME só troca quando ainda é o do seed ("Expedição"): nome que o gestor
  escolheu no Admin é dele.
"""

from django.db import migrations, models

OLD_REF = "expedicao"
NEW_REF = "saida"
OLD_NAME = "Expedição"
NEW_NAME = "Saída"


def rename_station(apps, schema_editor):
    KDSInstance = apps.get_model("backstage", "KDSInstance")
    if KDSInstance.objects.filter(ref=NEW_REF).exists():
        return
    station = KDSInstance.objects.filter(ref=OLD_REF).first()
    if station is None:
        return
    station.ref = NEW_REF
    fields = ["ref"]
    if station.name == OLD_NAME:
        station.name = NEW_NAME
        fields.append("name")
    station.save(update_fields=fields)


def restore_station(apps, schema_editor):
    KDSInstance = apps.get_model("backstage", "KDSInstance")
    if KDSInstance.objects.filter(ref=OLD_REF).exists():
        return
    station = KDSInstance.objects.filter(ref=NEW_REF).first()
    if station is None:
        return
    station.ref = OLD_REF
    fields = ["ref"]
    if station.name == NEW_NAME:
        station.name = OLD_NAME
        fields.append("name")
    station.save(update_fields=fields)


class Migration(migrations.Migration):

    dependencies = [
        ("backstage", "0075_via_cozinha_impressa"),
    ]

    operations = [
        migrations.AlterField(
            model_name="kdsinstance",
            name="type",
            field=models.CharField(
                choices=[("prep", "Preparo"), ("picking", "Separação"), ("expedition", "Saída")],
                max_length=20,
                verbose_name="tipo",
            ),
        ),
        migrations.RunPython(rename_station, restore_station),
    ]
