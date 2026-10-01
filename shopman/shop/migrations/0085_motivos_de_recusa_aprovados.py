"""Motivos de recusa e cancelamento: a lista que o dono aprovou em 01/10/2026 (D4).

Duas coisas, nenhuma de esquema:

1. ``Shop.cancellation_presets`` ganha a validação (motivo não termina em
   pontuação, porque o cliente lê ``Motivo: <motivo>.``) e o ``help_text`` que
   documenta o formato com grupo. ``AlterField`` sem SQL.
2. O banco que ainda tem a lista que o ``seed`` gravava (os quatro motivos de
   antes, com "Problema técnico no preparo") ou lista nenhuma passa para a lista
   aprovada, com os grupos. Se o operador já editou a lista no Admin, a
   migração não toca: a lista dele é a decisão mais nova.

A lista nova está escrita aqui por extenso, e não importada do ``seed``, porque
migração é história e não pode mudar quando o ``seed`` mudar. O teste
``test_cancellation_presets`` confere que as duas são iguais hoje.
"""

from django.db import migrations, models

import shopman.shop.models.shop

PREVIOUS_SEED_PRESETS = [
    "Item indisponível no momento",
    "Sem um dos ingredientes hoje",
    "Problema técnico no preparo",
    "Fora do horário de atendimento",
]

APPROVED_PRESETS = [
    {"label": "Item indisponível no momento", "group": "Produto"},
    {"label": "Sem um dos ingredientes hoje", "group": "Produto"},
    {"label": "Pagamento não aprovado", "group": "Pagamento"},
    {"label": "Pagamento não confirmado no prazo", "group": "Pagamento"},
    {"label": "Endereço fora da nossa área de entrega", "group": "Endereço e contato"},
    {"label": "Não conseguimos falar com você", "group": "Endereço e contato"},
    {"label": "Alta demanda neste horário", "group": "Capacidade"},
    {"label": "Sem entregador disponível neste horário", "group": "Capacidade"},
    {"label": "Fora do horário de atendimento", "group": "Horário"},
    {"label": "Você pediu o cancelamento", "group": "Cliente"},
    {"label": "Pedido em duplicidade", "group": "Duplicidade"},
]


def apply_approved_presets(apps, schema_editor):
    Shop = apps.get_model("shop", "Shop")
    for shop in Shop.objects.all():
        current = shop.cancellation_presets or []
        if current and list(current) != PREVIOUS_SEED_PRESETS:
            continue
        shop.cancellation_presets = APPROVED_PRESETS
        shop.save(update_fields=["cancellation_presets"])


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0084_producao_concluida_no_marketing"),
    ]

    operations = [
        migrations.AlterField(
            model_name="shop",
            name="cancellation_presets",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Justificativas padrão que o operador injeta com um toque ao recusar ou cancelar "
                    "um pedido no gestor. O texto escolhido é enviado ao cliente como \"Motivo: "
                    "<texto>.\", então escreva na voz da loja e sem pontuação no fim. Cada item é um "
                    "texto, ou um texto com grupo (o cabeçalho sob o qual o Gestor o mostra). A ordem "
                    "é a da tela.\nExemplo:\n[\n"
                    '  {"label": "Item indisponível no momento", "group": "Produto"},\n'
                    '  {"label": "Pagamento não aprovado", "group": "Pagamento"},\n'
                    '  "Fora do horário de atendimento"\n]'
                ),
                validators=[shopman.shop.models.shop.validate_cancellation_presets],
                verbose_name="motivos de cancelamento/recusa",
            ),
        ),
        migrations.RunPython(apply_approved_presets, migrations.RunPython.noop),
    ]
