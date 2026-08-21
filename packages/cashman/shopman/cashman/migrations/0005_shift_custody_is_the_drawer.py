"""A custódia passa a ser da GAVETA, não da pessoa.

Duas mudanças, e a ordem importa: a constraint sai ANTES do rename, senão o
`AlterField`/`RenameField` teria de carregar junto um índice parcial que aponta
para a coluna velha.

Por que: um balcão é uma gaveta com várias mãos. "Um turno aberto por operador"
obrigava a fechar e contar o caixa a cada troca de operador — ritual que a loja
não faz e não vai fazer. Quem agiu continua registrado, por lançamento, em
`Entry.operator`.

`RenameField` preserva os dados (não é drop+add): o turno aberto no staging
continua sendo o mesmo turno, com o mesmo dono de abertura.
"""

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("cashman", "0004_account_settled"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="shift",
            name="cashman_shift_open_operator_uq",
        ),
        migrations.RenameField(
            model_name="shift",
            old_name="operator",
            new_name="opened_by",
        ),
        migrations.AlterField(
            model_name="shift",
            name="opened_by",
            field=models.ForeignKey(
                help_text=(
                    "Quem abriu a gaveta e declarou o fundo de troco. NÃO é dono da "
                    "custódia nem responde sozinho pela diferença: quem agiu está em "
                    "cada Entry."
                ),
                on_delete=models.PROTECT,
                related_name="shifts_opened",
                to=settings.AUTH_USER_MODEL,
                verbose_name="aberto por",
            ),
        ),
    ]
