# A abertura da gaveta deixa de ser só "sem venda": o tablet abre a gaveta do
# Balcão para guardar o dinheiro de uma venda, e o porquê mora no payload
# (``purpose``). Só o rótulo muda; nenhuma linha muda.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cashman', '0006_alter_terminal_metadata'),
    ]

    operations = [
        migrations.AlterField(
            model_name='entry',
            name='kind',
            field=models.CharField(choices=[('float_in', 'Fundo de troco'), ('sale', 'Venda'), ('cod_settled', 'Acerto de entrega'), ('account_settled', 'Acerto de conta'), ('cash_in', 'Entrada de caixa'), ('refund', 'Devolução'), ('cash_out', 'Saída de caixa'), ('courier_out', 'Troco levado pelo entregador'), ('courier_in', 'Troco de volta do entregador'), ('count', 'Contagem de fechamento'), ('count_correction', 'Correção da contagem'), ('drawer_open', 'Gaveta aberta'), ('drawer_unlock', 'Trava da gaveta liberada'), ('change_requested', 'Troco pedido'), ('change_served', 'Troco atendido'), ('change_cancelled', 'Pedido de troco cancelado'), ('receipt_result', 'Resultado do comprovante'), ('note', 'Anotação')], max_length=24, verbose_name='tipo'),
        ),
    ]
