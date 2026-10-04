# O pulso da gaveta pedido pelo tablet vai pelo relay de impressão
# (services/drawer_pulse.py): só um tipo novo de trabalho, nenhuma linha muda.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('backstage', '0083_seating_spot_plan'),
    ]

    operations = [
        migrations.AlterField(
            model_name='printjob',
            name='kind',
            field=models.CharField(choices=[('production_weighing', 'Pesagem cega'), ('production_preparation', 'Etiqueta de preparo'), ('order_danfe', 'DANFE da entrega'), ('kitchen_ticket', 'Via Cozinha'), ('drawer_pulse', 'Pulso de gaveta')], max_length=40, verbose_name='tipo'),
        ),
    ]
