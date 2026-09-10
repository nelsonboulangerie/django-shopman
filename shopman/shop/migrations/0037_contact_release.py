import uuid

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0036_devolve_lactose_e_vegetariano'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContactRelease',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('kind', models.CharField(choices=[('phone', 'WhatsApp'), ('email', 'e-mail'), ('cpf', 'CPF/CNPJ')], max_length=20, verbose_name='tipo de contato')),
                ('value', models.CharField(help_text='O valor normalizado, exatamente como estava gravado.', max_length=255, verbose_name='contato liberado')),
                ('released_from_ref', models.CharField(max_length=50, verbose_name='cadastro de origem')),
                ('released_from_name', models.CharField(blank=True, max_length=200, verbose_name='nome do cadastro de origem')),
                ('released_pk', models.CharField(blank=True, max_length=64, verbose_name='registro apagado')),
                ('was_primary', models.BooleanField(default=False, verbose_name='era o contato principal')),
                ('merge_audit_id', models.UUIDField(blank=True, null=True, verbose_name='unificação afetada')),
                ('actor', models.CharField(blank=True, max_length=200, verbose_name='quem liberou')),
                ('released_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='liberado em')),
            ],
            options={
                'verbose_name': 'contato liberado',
                'verbose_name_plural': 'contatos liberados',
                'ordering': ['-released_at'],
                'indexes': [
                    models.Index(fields=['released_from_ref'], name='shop_release_from_ref'),
                    models.Index(fields=['merge_audit_id'], name='shop_release_merge'),
                ],
            },
        ),
    ]
