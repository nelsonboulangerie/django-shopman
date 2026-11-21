"""O identificador da corrida no bloco ``courier`` passa a se chamar ``ride_ref`` (M1b-a, #2552).

Era ``id_mch``, o nome do campo da TaOn, e a corrida da casa (``CASA-…``) também morava
nele. Pela regra do campo de terceiro (CLAUDE.md), o nome da TaOn vive só na porta dela
(``adapters/courier_machine.py`` e o webhook); dentro da casa é ``ride_ref``. Sem alias:
esta migração reescreve o que está gravado.

O que muda: ``Order.data["courier"]["id_mch"]``, o mesmo campo em cada tentativa
arquivada (``attempts``) e o ``payload`` dos eventos do pedido que o guardavam. A volta
desfaz exatamente isso.
"""

from django.db import migrations

OLD, NEW = "id_mch", "ride_ref"


def _rename_block(block, old, new):
    if not isinstance(block, dict):
        return block, False
    changed = False
    block = dict(block)
    if old in block:
        block[new] = block.pop(old)
        changed = True
    attempts = block.get("attempts")
    if isinstance(attempts, list):
        renamed = []
        for attempt in attempts:
            if isinstance(attempt, dict) and old in attempt:
                attempt = dict(attempt)
                attempt[new] = attempt.pop(old)
                changed = True
            renamed.append(attempt)
        block["attempts"] = renamed
    return block, changed


def _rename(apps, old, new):
    Order = apps.get_model("orderman", "Order")
    OrderEvent = apps.get_model("orderman", "OrderEvent")
    for pk, data in Order.objects.filter(data__has_key="courier").values_list("pk", "data").iterator():
        block, changed = _rename_block((data or {}).get("courier"), old, new)
        if changed:
            data = dict(data)
            data["courier"] = block
            Order.objects.filter(pk=pk).update(data=data)
    for pk, payload in OrderEvent.objects.filter(payload__has_key=old).values_list("pk", "payload").iterator():
        payload = dict(payload)
        payload[new] = payload.pop(old)
        OrderEvent.objects.filter(pk=pk).update(payload=payload)


def forwards(apps, schema_editor):
    _rename(apps, OLD, NEW)


def backwards(apps, schema_editor):
    _rename(apps, NEW, OLD)


class Migration(migrations.Migration):

    dependencies = [
        ("orderman", "0008_order_customer_ref_index"),
        ("shop", "0128_atalhos_da_nota_com_escopo"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
