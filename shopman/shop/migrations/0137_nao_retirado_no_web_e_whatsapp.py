"""Liga o "Não retirado" no web e no WhatsApp do banco vivo (#2694).

Palavra do dono, 22/11/2026: "Ligar o Não retirado para web e WhatsApp no ar: Sim
(mas VOCÊ aplica, não eu)" (DEV-2026-071). O WP-G11 escreveu a transição
``ready → cancelled`` desses dois canais em ``config/instances/nelson.json``, mas o
descritor só chega ao banco pelo seed, e o app vivo seguia sem ela: o Gestor
respondia "Este canal não permite encerrar um pedido pronto como não retirado."

Só a transição ``ready → cancelled``, e o banco fica igual ao descritor:

- canal com ``lifecycle.transitions``: acrescenta ``cancelled`` a ``ready`` se faltar,
  sem tocar no resto;
- canal sem o mapa (usava o padrão do pedido): grava o mapa do descritor, que é o
  padrão do pedido mais ``cancelled`` em ``ready``;
- canal que já tem a transição: nada; canal que não existe (banco de teste): nada.

Vale para pedido criado depois do deploy: o ciclo do canal é copiado para o
snapshot do pedido no commit. Idempotente. O reverse é inerte.
"""

from django.db import migrations

CHANNEL_REFS = ("web", "whatsapp")

#: O mapa do descritor para os dois canais: ``Order.DEFAULT_TRANSITIONS`` com
#: ``cancelled`` em ``ready``. Congelado aqui (migração não importa o modelo vivo).
TRANSITIONS = {
    "new": ["accepted", "cancelled"],
    "accepted": ["preparing", "ready", "cancelled"],
    "preparing": ["ready", "cancelled"],
    "ready": ["preparing", "dispatched", "completed", "cancelled"],
    "dispatched": ["delivered", "returned"],
    "delivered": ["completed", "returned"],
    "completed": ["returned"],
    "cancelled": [],
    "returned": [],
}


def forwards(apps, schema_editor):
    Channel = apps.get_model("shop", "Channel")
    for channel in Channel.objects.filter(ref__in=CHANNEL_REFS):
        config = dict(channel.config or {})
        lifecycle = dict(config.get("lifecycle") or {})
        transitions = lifecycle.get("transitions")
        if isinstance(transitions, dict) and transitions:
            ready = list(transitions.get("ready") or [])
            if "cancelled" in ready:
                continue
            transitions = {**transitions, "ready": [*ready, "cancelled"]}
        else:
            transitions = {status: list(targets) for status, targets in TRANSITIONS.items()}
        lifecycle["transitions"] = transitions
        config["lifecycle"] = lifecycle
        channel.config = config
        channel.save(update_fields=["config"])


class Migration(migrations.Migration):
    dependencies = [("shop", "0136_concierge_motor_por_classe")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
