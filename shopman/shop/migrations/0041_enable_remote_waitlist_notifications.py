"""Ativa a fermata somente nos canais remotos próprios da loja.

O seed é a fonte para bancos novos, mas o release do App Platform não o
executa — e não deve executá-lo sobre um banco que já recebe pedidos. Esta
migração leva a mesma política, de forma estreita e idempotente, aos canais
existentes sem tocar catálogo, estoque, clientes ou pedidos.

O rollback desliga novas entradas na fila, mas preserva a cadeia de entrega
real. Voltar a herdar ``console`` faria outras notificações transacionais
parecerem entregues sem sair do processo, portanto não é uma reversão segura.
Reservas já aceitas continuam sendo honradas pelo lifecycle mesmo com
``enabled=False``.
"""

from django.db import migrations

REMOTE_CHANNEL_REFS = ("web", "whatsapp")

WAITLIST_POLICY = {
    "enabled": True,
    "horizon_days": 2,
    "confirmation_minutes": 15,
    "release_policy": "serve_next",
    "charge_at": "confirmation",
    "price_frozen": True,
}

NOTIFICATION_POLICY = {
    "backend": "manychat",
    "fallback_chain": ["sms", "email"],
}


def forwards(apps, schema_editor):
    Channel = apps.get_model("shop", "Channel")
    for channel in Channel.objects.filter(ref__in=REMOTE_CHANNEL_REFS).iterator():
        config = dict(channel.config or {})
        config["waitlist"] = dict(WAITLIST_POLICY)
        config["notifications"] = {
            **dict(config.get("notifications") or {}),
            **NOTIFICATION_POLICY,
        }
        channel.config = config
        channel.save(update_fields=["config"])


def backwards(apps, schema_editor):
    Channel = apps.get_model("shop", "Channel")
    for channel in Channel.objects.filter(ref__in=REMOTE_CHANNEL_REFS).iterator():
        config = dict(channel.config or {})
        waitlist = dict(config.get("waitlist") or WAITLIST_POLICY)
        waitlist["enabled"] = False
        config["waitlist"] = waitlist
        channel.config = config
        channel.save(update_fields=["config"])


class Migration(migrations.Migration):
    dependencies = [("shop", "0040_quality_grade_labels")]

    operations = [migrations.RunPython(forwards, backwards)]
