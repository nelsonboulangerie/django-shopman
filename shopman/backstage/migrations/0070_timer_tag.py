import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('backstage', '0069_kds_ticket_items_help'),
    ]

    operations = [
        migrations.CreateModel(
            name='TimerTag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ref', models.SlugField(max_length=48, unique=True, verbose_name='ref')),
                ('label', models.CharField(help_text='O que o padeiro lê no chip. Curto: cabe num toque de olho.', max_length=40, verbose_name='rótulo')),
                ('normalized_label', models.CharField(editable=False, help_text='Derivado do rótulo. Existe para impedir duas etiquetas com o mesmo nome.', max_length=40, verbose_name='rótulo comparável')),
                ('minutes', models.PositiveSmallIntegerField(help_text='O tempo que um toque no chip dispara. O operador ainda pode somar depois.', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(999)], verbose_name='duração (min)')),
                ('origin', models.CharField(choices=[('admin', 'Cadastrada pelo gestor'), ('operator', 'Criada no fournil')], default='admin', help_text='O que veio do fournil é o que vale a pena revisar aqui.', max_length=16, verbose_name='origem')),
                ('position', models.PositiveSmallIntegerField(default=0, help_text='Menor primeiro. O que a casa dispara todo dia fica no começo da fileira.', verbose_name='ordem')),
                ('is_active', models.BooleanField(default=True, help_text='Etiqueta inativa some da tela do fournil e libera o nome.', verbose_name='ativa')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='criada em')),
            ],
            options={
                'verbose_name': 'etiqueta de timer',
                'verbose_name_plural': 'etiquetas de timer',
                'ordering': ['position', 'label'],
                'constraints': [models.UniqueConstraint(condition=models.Q(('is_active', True)), fields=('normalized_label',), name='timer_tag_unique_active_label', violation_error_message='Já existe uma etiqueta ativa com este nome. Edite a que existe ou desative-a antes de criar outra.')],
            },
        ),
    ]
