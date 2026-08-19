"""Um pedido entra uma vez no livro de um turno, por tipo.

A idempotência da venda era um `exists()` antes do insert em
`shop/services/pos.py::_record_sale` — TOCTOU clássico: entre a leitura e a
gravação cabe o segundo submit do PDV (retry de rede), e duas linhas `sale` do
mesmo pedido dobram o dinheiro esperado do turno. Agora a unicidade é do banco,
como a do turno aberto; o `exists()` fica como fast-path de mensagem amigável.
"""

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cashman', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='entry',
            constraint=models.UniqueConstraint(condition=models.Q(('kind', 'sale'), models.Q(('order_ref', ''), _negated=True)), fields=('shift', 'order_ref'), name='cashman_entry_one_sale_per_order_uq'),
        ),
        migrations.AddConstraint(
            model_name='entry',
            constraint=models.UniqueConstraint(condition=models.Q(('kind', 'cod_settled'), models.Q(('order_ref', ''), _negated=True)), fields=('shift', 'order_ref'), name='cashman_entry_one_cod_settled_per_order_uq'),
        ),
    ]
