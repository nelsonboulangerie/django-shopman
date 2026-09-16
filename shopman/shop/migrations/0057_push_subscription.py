import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0056_concierge_message_observation_controls'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='usernotification',
            name='category',
            field=models.CharField(choices=[('campaign', 'campanha'), ('production', 'produção'), ('order', 'pedidos'), ('purchase', 'compras'), ('report', 'relatórios'), ('sign_in', 'acesso'), ('system', 'sistema')], default='system', max_length=32, verbose_name='categoria'),
        ),
        migrations.CreateModel(
            name='PushSubscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('endpoint', models.TextField(unique=True, verbose_name='endereço de entrega')),
                ('p256dh', models.TextField(verbose_name='chave pública do aparelho')),
                ('auth', models.TextField(verbose_name='segredo de autenticação do aparelho')),
                ('surface_ref', models.CharField(choices=[('hub', 'Central'), ('orders', 'Pedidos'), ('pos', 'PDV'), ('production', 'Produção'), ('marketing', 'Marketing'), ('purchase', 'Compras'), ('bi', 'BI')], max_length=32, verbose_name='surface')),
                ('device_label', models.CharField(max_length=120, verbose_name='aparelho')),
                ('categories', models.JSONField(default=list, verbose_name='categorias')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='criada em')),
                ('last_success_at', models.DateTimeField(blank=True, null=True, verbose_name='último sucesso em')),
                ('failures', models.PositiveSmallIntegerField(default=0, verbose_name='falhas consecutivas')),
                ('disabled_at', models.DateTimeField(blank=True, null=True, verbose_name='removida em')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='push_subscriptions', to=settings.AUTH_USER_MODEL, verbose_name='usuário')),
            ],
            options={
                'verbose_name': 'assinatura Web Push',
                'verbose_name_plural': 'assinaturas Web Push',
                'ordering': ['-created_at', '-pk'],
                'indexes': [models.Index(fields=['user', 'disabled_at'], name='shop_pushsu_user_id_ec8a92_idx'), models.Index(fields=['surface_ref', 'disabled_at'], name='shop_pushsu_surface_c1c309_idx')],
            },
        ),
    ]
