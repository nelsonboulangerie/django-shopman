"""Prazo de aceite da loja online: 5 min no dia, 60 na encomenda (dono, 09/11/2026).

Emenda da ADR-036. O seed cobre bancos novos; este é o banco vivo. No canal
``web`` com ``auto_cancel``:

- ``timeout_minutes`` 30 → 5, só se ainda estiver no valor de fábrica da ``0094``
  (30); ajuste feito à mão no Admin fica;
- ``preorder_timeout_minutes`` = 60 quando o canal ainda não declara um.

Em TODO canal ``auto_cancel`` sai o ``stale_new_alert_minutes``: o aviso de pedido
parado agora sai a 1/3 do prazo do próprio pedido, e o ``ChannelConfig.validate``
recusa a chave nesse modo. Idempotente. O reverse é inerte.
"""

from django.db import migrations

WEB_CHANNEL_REF = "web"
FACTORY_TIMEOUT_MINUTES = 30
SAME_DAY_TIMEOUT_MINUTES = 5
PREORDER_TIMEOUT_MINUTES = 60


def forwards(apps, schema_editor):
    Channel = apps.get_model("shop", "Channel")
    for channel in Channel.objects.all():
        config = dict(channel.config or {})
        confirmation = dict(config.get("confirmation") or {})
        if confirmation.get("mode") != "auto_cancel":
            continue
        changed = False
        if "stale_new_alert_minutes" in confirmation:
            confirmation.pop("stale_new_alert_minutes")
            changed = True
        if channel.ref == WEB_CHANNEL_REF:
            if confirmation.get("timeout_minutes") == FACTORY_TIMEOUT_MINUTES:
                confirmation["timeout_minutes"] = SAME_DAY_TIMEOUT_MINUTES
                changed = True
            if "preorder_timeout_minutes" not in confirmation:
                confirmation["preorder_timeout_minutes"] = PREORDER_TIMEOUT_MINUTES
                changed = True
        if changed:
            config["confirmation"] = confirmation
            channel.config = config
            channel.save(update_fields=["config"])


class Migration(migrations.Migration):
    dependencies = [("shop", "0113_recusa_usa_a_lista_unica_de_motivos")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
