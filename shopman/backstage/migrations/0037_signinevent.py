import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('backstage', '0036_audit_stock_permission'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SignInEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('username', models.CharField(db_index=True, max_length=150, verbose_name='usuário')),
                ('method', models.CharField(choices=[('password', 'senha'), ('pin', 'PIN'), ('badge', 'crachá'), ('otp', 'código de verificação'), ('unknown', 'desconhecido')], db_index=True, default='unknown', max_length=20, verbose_name='método')),
                ('outcome', models.CharField(choices=[('success', 'entrou'), ('failed', 'recusado'), ('revoked', 'revogado')], db_index=True, default='success', max_length=10, verbose_name='resultado')),
                ('station_ref', models.CharField(blank=True, db_index=True, max_length=80, verbose_name='estação')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, verbose_name='IP')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='quando')),
                ('notified', models.BooleanField(default=False, verbose_name='avisado')),
                ('data', models.JSONField(blank=True, default=dict, verbose_name='contexto')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sign_in_events', to=settings.AUTH_USER_MODEL, verbose_name='operador')),
            ],
            options={
                'verbose_name': 'acesso de operador',
                'verbose_name_plural': 'acessos de operador',
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['user', '-created_at'], name='backstage_s_user_id_eeadef_idx'), models.Index(fields=['outcome', '-created_at'], name='backstage_s_outcome_453223_idx')],
            },
        ),
    ]
