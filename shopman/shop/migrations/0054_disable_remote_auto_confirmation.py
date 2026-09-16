"""Desliga o autoaceite dos canais remotos já persistidos.

O seed cobre bancos novos, mas não roda em todo deploy. A migração é estreita:
altera apenas web/WhatsApp que ainda estejam explicitamente em auto_confirm,
preserva todas as demais chaves e nunca toca configuração manual/customizada.
O reverse é intencionalmente inerte: rollback não deve reativar aceite automático.
"""

from django.db import migrations

REMOTE_CHANNEL_REFS = ("web", "whatsapp")


def forwards(apps, schema_editor):
    Channel = apps.get_model("shop", "Channel")
    for channel in Channel.objects.filter(ref__in=REMOTE_CHANNEL_REFS).iterator():
        config = dict(channel.config or {})
        confirmation = dict(config.get("confirmation") or {})
        if confirmation.get("mode") != "auto_confirm":
            continue
        confirmation["mode"] = "manual"
        config["confirmation"] = confirmation
        channel.config = config
        channel.save(update_fields=["config"])


class Migration(migrations.Migration):
    dependencies = [("shop", "0053_marketing_delivery_identity")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
