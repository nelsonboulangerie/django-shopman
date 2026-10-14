"""Loja online paga ao pedir (decisão do dono, 14/10/2026, L1=1 e L2=1).

O seed cobre bancos novos; este é o banco vivo. O canal ``web`` passa de
"paga depois do aceite" para "paga ao pedir, com prazo de aceite":

- ``payment.timing``: ``post_commit`` → ``at_commit`` (o Pix/cartão nasce no
  pedido);
- ``confirmation.mode``: ``manual`` → ``auto_cancel`` com ``timeout_minutes`` 30
  (de loja aberta): a loja que não aceita a tempo cancela, e o dinheiro volta.

Estreita como a ``0054``: só troca o que ainda está no valor de fábrica
(``post_commit`` / ``manual``) e preserva todas as outras chaves; configuração
feita à mão no Admin fica. Idempotente. O reverse é inerte.
"""

from django.db import migrations

WEB_CHANNEL_REF = "web"
ACCEPT_DEADLINE_MINUTES = 30


def forwards(apps, schema_editor):
    Channel = apps.get_model("shop", "Channel")
    channel = Channel.objects.filter(ref=WEB_CHANNEL_REF).first()
    if channel is None:
        return
    config = dict(channel.config or {})
    payment = dict(config.get("payment") or {})
    confirmation = dict(config.get("confirmation") or {})
    changed = False
    if payment.get("timing", "post_commit") == "post_commit":
        payment["timing"] = "at_commit"
        config["payment"] = payment
        changed = True
    if confirmation.get("mode") == "manual":
        confirmation["mode"] = "auto_cancel"
        confirmation["timeout_minutes"] = ACCEPT_DEADLINE_MINUTES
        config["confirmation"] = confirmation
        changed = True
    if changed:
        channel.config = config
        channel.save(update_fields=["config"])


class Migration(migrations.Migration):
    dependencies = [("shop", "0093_xepa_so_no_balcao")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
