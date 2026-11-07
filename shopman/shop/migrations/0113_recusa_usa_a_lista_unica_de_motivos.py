"""A recusa usa a lista única de motivos (beta 06/11/2026).

O "Recusar pedido" do Gestor tinha a sua própria lista de motivos prontos
(``Shop.cancellation_presets``, editável no Admin), diferente da lista do
"Cancelar pedido" (``services/cancel_reasons``). Agora as duas ações usam a
mesma lista, com a frase revisada que o cliente lê, e o campo sai.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0112_motivos_de_recusa_com_chave"),
    ]

    operations = [
        migrations.RemoveField(model_name="shop", name="cancellation_presets"),
    ]
