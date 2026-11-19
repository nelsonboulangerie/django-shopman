"""Tira a etiqueta "Entrega" dos endereços que o pedido de entrega gravou com ela (#2775).

Todo endereço que um pedido de entrega gravava sozinho no cadastro do cliente nascia
com `label="other"` e `label_custom="Entrega"` (escrito por `shop/services/customer.py`
e por `shop/services/checkout.py`). A etiqueta repetia o canal e não distinguia um
endereço do outro: o cliente do iFood ficava com três endereços chamados "Entrega".
Desde #2775 esses endereços nascem sem etiqueta; esta migração limpa os que já existem.

O filtro é a etiqueta EXATA que os dois escritores gravavam (decisão da coordenação,
19/11/2026): `label="other"` e `label_custom="Entrega"`. O endereço não guarda origem,
então um "Entrega" exato que alguém digitou à mão também perde a etiqueta (fica sem
etiqueta, e o endereço continua lá). Variações ("entrega", "Entrega ", "ENTREGA") não
saem de nenhum escritor do sistema, só da mão de alguém, e por isso ficam como estão.

O que ela NÃO faz: não apaga endereço, não junta duplicados, não toca em outro campo
(rua, coordenada, `place_id`, padrão). `QuerySet.update` também não mexe no
`updated_at`, que é a revisão que o Gestor confere ao editar.

Mora aqui, no orquestrador que gravou a etiqueta, e não no guestman: é dado
contextual do shop, e o Core não ganha migração por isso.

Roda sobre dado real de cliente (a loja está em produção) e escreve no log do deploy
quantos endereços tocou, como as outras migrações de dados do shop (0102, 0104).

Idempotente: na segunda vez o filtro não acha nada. A volta é `noop` declarado: depois
da limpeza não há como saber quais endereços sem etiqueta eram "Entrega", e devolver a
etiqueta a todos os sem etiqueta seria inventar dado.
"""

from django.db import migrations

MIGRATION_NAME = "shop.0123_endereco_de_entrega_sem_etiqueta"
SYSTEM_LABEL = "Entrega"


def drop_system_delivery_label(apps, schema_editor) -> int:
    """Tira a etiqueta e diz no log do deploy quantos endereços a perderam."""
    CustomerAddress = apps.get_model("guestman", "CustomerAddress")
    touched = CustomerAddress.objects.filter(label="other", label_custom=SYSTEM_LABEL).update(label_custom="")
    print(f"\n  {MIGRATION_NAME}: {touched} endereços perderam a etiqueta \"{SYSTEM_LABEL}\" e ficaram sem etiqueta.")
    return touched


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0122_channel_addons"),
        ("guestman", "0008_price_tier_vira_grupo_de_clientes"),
    ]

    operations = [
        migrations.RunPython(drop_system_delivery_label, migrations.RunPython.noop),
    ]
