"""Os atalhos da nota da cozinha ganham "vale para" (decisão do dono, 21/11/2026).

Saem da lista de textos da loja (``Shop.kitchen_note_tags``) para um modelo próprio,
``KitchenNoteTag``, com as categorias e os produtos a que cada um se aplica. Os
atalhos que a loja já tinha vêm para cá na mesma ordem, sem escopo (valem para
todos, como antes); o campo antigo sai.
"""

from django.db import migrations, models


def copy_tags(apps, schema_editor):
    Shop = apps.get_model("shop", "Shop")
    KitchenNoteTag = apps.get_model("shop", "KitchenNoteTag")
    for shop in Shop.objects.all():
        for position, label in enumerate(shop.kitchen_note_tags or []):
            label = " ".join(str(label or "").split())[:60]
            if label:
                KitchenNoteTag.objects.get_or_create(label=label, defaults={"position": position})


def restore_tags(apps, schema_editor):
    Shop = apps.get_model("shop", "Shop")
    KitchenNoteTag = apps.get_model("shop", "KitchenNoteTag")
    labels = list(KitchenNoteTag.objects.order_by("position", "label").values_list("label", flat=True))
    Shop.objects.update(kitchen_note_tags=labels)


class Migration(migrations.Migration):

    dependencies = [
        ('offerman', '0006_remove_product_is_batch_produced'),
        ('shop', '0127_avisar_o_cliente_notification_templates'),
    ]

    operations = [
        migrations.CreateModel(
            name='KitchenNoteTag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(help_text='O texto que entra na nota, como "Bem assado".', max_length=60, unique=True, verbose_name='atalho')),
                ('position', models.PositiveIntegerField(default=0, help_text='A ordem dos atalhos no pedido.', verbose_name='ordem')),
                ('collections', models.ManyToManyField(blank=True, help_text='O atalho aparece no pedido que tem algum produto destas categorias.', related_name='+', to='offerman.collection', verbose_name='categorias')),
                ('products', models.ManyToManyField(blank=True, help_text='O atalho aparece no pedido que tem algum destes produtos. Sem categoria e sem produto, vale para todos.', related_name='+', to='offerman.product', verbose_name='produtos')),
            ],
            options={
                'verbose_name': 'atalho da nota da cozinha',
                'verbose_name_plural': 'atalhos da nota da cozinha',
                'ordering': ('position', 'label'),
            },
        ),
        migrations.RunPython(copy_tags, restore_tags),
        migrations.RemoveField(
            model_name='shop',
            name='kitchen_note_tags',
        ),
    ]
