"""Motivos de recusa com a chave da lista única de motivos (beta 06/11/2026).

A recusa pelo Gestor gravava o texto do motivo pronto e nenhuma chave: tudo saía
``other``, e o histórico do pedido dizia "Cancelado · Outro motivo" para quem
escolheu "Você pediu o cancelamento". Cada motivo pronto da lista aprovada (D4)
ganha ``reason_key``, a chave de ``services/cancel_reasons`` que a recusa grava.

Só os motivos com o texto da lista aprovada ganham chave, e só quando ainda não
têm uma. Motivo escrito pelo operador no Admin fica como está (sai ``other``).

A lista está escrita aqui por extenso, e não importada do ``seed``, porque
migração é história. ``test_cancellation_presets`` confere que ela e o ``seed``
são iguais hoje.
"""

from django.db import migrations, models

import shopman.shop.models.shop

APPROVED_PRESETS = [
    {"label": "Item indisponível no momento", "group": "Produto", "reason_key": "out_of_stock"},
    {"label": "Sem um dos ingredientes hoje", "group": "Produto", "reason_key": "out_of_stock"},
    {"label": "Pagamento não aprovado", "group": "Pagamento", "reason_key": "payment_not_confirmed"},
    {"label": "Pagamento não confirmado no prazo", "group": "Pagamento", "reason_key": "payment_not_confirmed"},
    {"label": "Endereço fora da nossa área de entrega", "group": "Endereço e contato", "reason_key": "cannot_deliver"},
    {"label": "Não conseguimos falar com você", "group": "Endereço e contato", "reason_key": "other"},
    {"label": "Alta demanda neste horário", "group": "Capacidade", "reason_key": "other"},
    {"label": "Sem entregador disponível neste horário", "group": "Capacidade", "reason_key": "cannot_deliver"},
    {"label": "Fora do horário de atendimento", "group": "Horário", "reason_key": "store_closing"},
    {"label": "Você pediu o cancelamento", "group": "Cliente", "reason_key": "customer_request"},
    {"label": "Pedido em duplicidade", "group": "Duplicidade", "reason_key": "other"},
]

KEY_BY_LABEL = {item["label"]: item["reason_key"] for item in APPROVED_PRESETS}


def with_reason_keys(presets):
    """A lista gravada, com a chave nos motivos da lista aprovada que ainda não têm."""
    result = []
    for item in presets or []:
        if isinstance(item, str) and item.strip() in KEY_BY_LABEL:
            item = {"label": item.strip(), "reason_key": KEY_BY_LABEL[item.strip()]}
        elif isinstance(item, dict) and "reason_key" not in item:
            key = KEY_BY_LABEL.get(str(item.get("label") or "").strip())
            if key:
                item = {**item, "reason_key": key}
        result.append(item)
    return result


def add_reason_keys(apps, schema_editor):
    Shop = apps.get_model("shop", "Shop")
    for shop in Shop.objects.all():
        current = shop.cancellation_presets or []
        updated = with_reason_keys(current)
        if updated != current:
            shop.cancellation_presets = updated
            shop.save(update_fields=["cancellation_presets"])


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0111_cancelamento_conforme_solicitacao"),
    ]

    operations = [
        migrations.AlterField(
            model_name="shop",
            name="cancellation_presets",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Justificativas padrão que o operador injeta com um toque ao recusar "
                    "ou cancelar um pedido no gestor. O texto escolhido é enviado ao "
                    'cliente como "Motivo: <texto>.", então escreva na voz da loja e sem '
                    "pontuação no fim. Cada item é um texto, ou um texto com grupo (o "
                    "cabeçalho sob o qual o Gestor o mostra). A ordem é a da tela. "
                    '"reason_key" (opcional) liga o motivo à lista única de motivos '
                    "(out_of_stock, cannot_deliver, customer_request, payment_not_confirmed, "
                    "store_closing, other): é o motivo que o histórico e o acompanhamento do "
                    "pedido registram.\n"
                    "Exemplo:\n"
                    "[\n"
                    '  {"label": "Item indisponível no momento", "group": "Produto", "reason_key": "out_of_stock"},\n'
                    '  {"label": "Pagamento não aprovado", "group": "Pagamento", "reason_key": "payment_not_confirmed"},\n'
                    '  "Fora do horário de atendimento"\n'
                    "]"
                ),
                validators=[shopman.shop.models.shop.validate_cancellation_presets],
                verbose_name="motivos de cancelamento/recusa",
            ),
        ),
        migrations.RunPython(add_reason_keys, migrations.RunPython.noop),
    ]
