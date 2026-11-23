"""Canal remoto só fica "Em preparo" quando a Cozinha começa (#3165).

Decisão da coordenação em 22/11/2026, reversível: como já é no canal ``web``, o
WhatsApp e o iFood passam a declarar ``fulfillment.prep_start="operator"``. O
ticket nasce no aceite e o pedido segue "Aceito" até o "Iniciar preparo" do posto
(ou o atalho do Gestor, que é o mesmo ato). Antes, no padrão ``auto``, o aceite já
escrevia "Em preparo" com o ticket ainda pendente: o Gestor e o cliente liam que a
Cozinha tinha começado quando ela não tinha.

O seed cobre bancos novos (``config/instances/nelson.json``); este é o banco vivo.
Estreita como a ``0094``: só escreve onde o canal não declara ``prep_start``
(o valor de fábrica); o que foi escolhido à mão no Admin fica. Idempotente. O
reverse é inerte.
"""

from django.db import migrations

REMOTE_CHANNEL_REFS = ("whatsapp", "ifood")


def forwards(apps, schema_editor):
    Channel = apps.get_model("shop", "Channel")
    for channel in Channel.objects.filter(ref__in=REMOTE_CHANNEL_REFS):
        config = dict(channel.config or {})
        fulfillment = dict(config.get("fulfillment") or {})
        if "prep_start" in fulfillment:
            continue
        fulfillment["prep_start"] = "operator"
        config["fulfillment"] = fulfillment
        channel.config = config
        channel.save(update_fields=["config"])


class Migration(migrations.Migration):
    dependencies = [("shop", "0137_nao_retirado_no_web_e_whatsapp")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
