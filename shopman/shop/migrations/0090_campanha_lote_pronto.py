# A campanha do lote se chama "Lote pronto", não "Fornada pronta".
#
# SPEC4 (v4, item 8): "lote, não fornada, nos apps de operador". O nome da campanha
# aparece no Marketing (fila de decisões, revisão, Agendados, Ajustes > Campanhas),
# que é app de operador. "Fornada" continua sendo a palavra da loja para o cliente
# (o texto do anúncio, o modelo "Saiu do forno"): esta migração não toca em conteúdo
# de anúncio nem em histórico de disparo, só no NOME da campanha.
#
# O seed já nasce com o nome novo; esta migração leva o mesmo nome ao banco vivo. Só
# renomeia a campanha que ainda carrega EXATAMENTE o nome antigo do seed (renomeada à
# mão fica como está), e só quando o nome novo está livre (``Campaign.name`` é a chave
# do ``update_or_create`` do seed). Reversível pela mesma regra.

from django.db import migrations

OLD = "Fornada pronta"
NEW = "Lote pronto"


def _rename(apps, before: str, after: str) -> None:
    Campaign = apps.get_model("shop", "Campaign")
    if Campaign.objects.filter(name=after).exists():
        return
    Campaign.objects.filter(name=before).update(name=after)


def forward(apps, schema_editor):
    _rename(apps, OLD, NEW)


def backward(apps, schema_editor):
    _rename(apps, NEW, OLD)


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0089_avisos_da_cozinha"),
    ]

    operations = [migrations.RunPython(forward, backward)]
