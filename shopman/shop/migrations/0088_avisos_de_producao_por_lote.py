# Avisos de produção ao operador falam de lote, aproveitamento, abrir e fechar.
#
# O UX-PROD-AF (PR #1433) trocou no seed o texto de dois modelos de mensagem:
# "Yield baixo na produção X" virou "Aproveitamento baixo no lote X", e "Produção X não
# foi iniciada" virou "Lote X não foi aberto". O seed já nasce com o texto novo; esta
# migração leva o mesmo texto ao banco vivo sem reseed.
#
# Só reescreve o campo (assunto ou mensagem) que ainda carrega EXATAMENTE o texto antigo
# do seed: o que o lojista editou no Admin fica como está. A versão operacional sobe junto
# com o texto, para que um formulário do Admin aberto antes não grave por cima sem aviso.
# Reversível pela mesma tabela.

from django.db import migrations
from django.db.models import F

TEMPLATES = {
    # event: {campo: (antes, depois)}
    "production_low_yield": {
        "subject": (
            "Yield baixo na produção {work_order_ref}",
            "Aproveitamento baixo no lote {work_order_ref}",
        ),
        "body": (
            "A produção *{work_order_ref}* ({output_sku}) fechou com yield de {yield_percent}%.\n\n"
            "Vale conferir a perda no relatório de produção.",
            "O lote *{work_order_ref}* ({output_sku}) fechou com aproveitamento de {yield_percent}%.\n\n"
            "Vale conferir a perda no relatório de produção.",
        ),
    },
    "production_forgotten": {
        "subject": (
            "Produção {work_order_ref} não foi iniciada",
            "Lote {work_order_ref} não foi aberto",
        ),
        "body": (
            "A produção *{work_order_ref}* ({output_sku}) planejada para {target_date} nunca foi iniciada.\n\n"
            "Conclua, reagende ou estorne no planejamento.",
            "O lote *{work_order_ref}* ({output_sku}) planejado para {target_date} nunca foi aberto.\n\n"
            "Abra, reagende ou cancele no planejamento.",
        ),
    },
}


def _rewrite(apps, direction):
    NotificationTemplate = apps.get_model("shop", "NotificationTemplate")
    for event, fields in TEMPLATES.items():
        for field, (old, new) in fields.items():
            source, target = (old, new) if direction == "forwards" else (new, old)
            NotificationTemplate.objects.filter(event=event, **{field: source}).update(
                **{field: target}, version=F("version") + 1
            )


def forwards(apps, schema_editor):
    _rewrite(apps, "forwards")


def backwards(apps, schema_editor):
    _rewrite(apps, "backwards")


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0087_nomes_kanfa_com_ponto_medio"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
