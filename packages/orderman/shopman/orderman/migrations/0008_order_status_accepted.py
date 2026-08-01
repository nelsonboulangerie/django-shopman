"""`confirmed` vira `accepted` — no enum, na coluna de carimbo e nos dados.

A tela já dizia "Aceitar"/"Pedido aceito" e o dado ainda dizia `confirmed`.
Enquanto os dois discordarem, alguém lê `confirmed` e entende "pagamento
confirmado" — que foi exatamente a leitura errada que originou a mudança.

Feito antes do go-live de propósito: sem consumidor externo (o iFood fala
`confirm` pelo adapter, que traduz) e com dados descartáveis. Depois do corte, o
mesmo rename exigiria alias temporário e janela de manutenção (ADR-015).

`RenameField` em vez de remover+adicionar: os carimbos de hora existentes são
preservados. E o status viaja dentro de JSONField (`OrderEvent.payload`), então
o texto lá também é reescrito — um sed no Python não alcança dado gravado.
"""

from django.db import migrations, models


def _reescrever(apps, *, de: str, para: str) -> None:
    Order = apps.get_model("orderman", "Order")
    Order.objects.filter(status=de).update(status=para)

    # A FASE do lifecycle é derivada do status (`phase = f"on_{order.status}"`) e
    # fica gravada em `Order.data["lifecycle"]`. Sem reescrever aqui, o pedido
    # antigo parece nunca ter passado pela fase e o sweep de pedidos presos a
    # redispararia — refazendo hold, ticket de KDS e início de pagamento.
    fase_de, fase_para = f"on_{de}", f"on_{para}"
    for pedido in Order.objects.filter(data__icontains=fase_de).iterator():
        dados = pedido.data if isinstance(pedido.data, dict) else None
        if not dados:
            continue
        ciclo = dados.get("lifecycle")
        if isinstance(ciclo, dict) and fase_de in ciclo:
            ciclo[fase_para] = ciclo.pop(fase_de)
            pedido.data = dados
            pedido.save(update_fields=["data"])

    OrderEvent = apps.get_model("orderman", "OrderEvent")
    for evento in OrderEvent.objects.iterator():
        payload = evento.payload if isinstance(evento.payload, dict) else None
        if not payload:
            continue
        mudou = False
        for chave in ("new_status", "old_status", "status", "from_status", "to_status"):
            if payload.get(chave) == de:
                payload[chave] = para
                mudou = True
        if mudou:
            evento.payload = payload
            evento.save(update_fields=["payload"])


def para_accepted(apps, schema_editor):
    _reescrever(apps, de="confirmed", para="accepted")


def voltar_para_confirmed(apps, schema_editor):
    _reescrever(apps, de="accepted", para="confirmed")


class Migration(migrations.Migration):

    dependencies = [
        ("orderman", "0007_alter_directive_options_alter_session_options_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="order",
            old_name="confirmed_at",
            new_name="accepted_at",
        ),
        migrations.AlterField(
            model_name="order",
            name="accepted_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="aceito em"),
        ),
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("new", "novo"),
                    ("accepted", "aceito"),
                    ("preparing", "em preparo"),
                    ("ready", "pronto"),
                    ("dispatched", "despachado"),
                    ("delivered", "entregue"),
                    ("completed", "concluído"),
                    ("cancelled", "cancelado"),
                    ("returned", "devolvido"),
                ],
                db_index=True,
                default="new",
                max_length=32,
                verbose_name="status",
            ),
        ),
        migrations.RunPython(para_accepted, voltar_para_confirmed),
    ]
