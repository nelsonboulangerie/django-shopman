"""Leva a margem de segurança padrão (2 unidades) aos canais remotos já gravados.

Decisão do dono (22/09/2026): "Margem padrão fica em 2 unidades, configurável,
claro." O seed escreve ``stock.safety_margin`` nos canais remotos de bancos
novos, mas o release não roda o seed — e os canais existentes nunca tiveram a
chave, então herdavam o 0 do ``ChannelConfig`` e a margem não protegia nada.

Estreita e idempotente: só grava onde a chave está AUSENTE. Valor que alguém
já tenha escolhido no Admin — inclusive 0 — é preservado. O PDV fica de fora:
o balcão nunca tem margem.

O reverse é inerte de propósito: voltar a margem para 0 reabre a disputa
balcão × pedido remoto pela última unidade; quem quiser isso ajusta no Admin.
"""

from django.db import migrations

REMOTE_CHANNEL_REFS = ("web", "whatsapp", "ifood")
REMOTE_SAFETY_MARGIN = 2


def forwards(apps, schema_editor):
    Channel = apps.get_model("shop", "Channel")
    for channel in Channel.objects.filter(ref__in=REMOTE_CHANNEL_REFS).iterator():
        config = dict(channel.config or {})
        stock = dict(config.get("stock") or {})
        if "safety_margin" in stock:
            continue
        stock["safety_margin"] = REMOTE_SAFETY_MARGIN
        config["stock"] = stock
        channel.config = config
        channel.save(update_fields=["config"])


class Migration(migrations.Migration):
    dependencies = [("shop", "0063_ifood_merchant")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
