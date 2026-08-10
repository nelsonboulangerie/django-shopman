"""`tv` deixa de ser plataforma de anúncio (ADR-020 §10).

A coluna precisa de limpeza, não só o help_text: linhas que ainda listem `tv` fariam o
painel avisar "plataforma desconhecida pelo sistema" para algo que nós removemos — o gestor
levaria a culpa por uma decisão nossa.
"""

from django.db import migrations, models


def _drop_tv(apps, schema_editor):
    for model_name in ("Campaign", "Announcement"):
        model = apps.get_model("shop", model_name)
        for row in model.objects.all().iterator():
            platforms = row.platforms or []
            if "tv" not in platforms:
                continue
            row.platforms = [p for p in platforms if p != "tv"]
            row.save(update_fields=["platforms"])


def _noop(apps, schema_editor):
    """Sem volta: `tv` não era destino, era sucesso falso. Recriá-la seria o bug."""


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0007_shop_brand_voice'),
    ]

    operations = [
        migrations.AlterField(
            model_name='campaign',
            name='platforms',
            field=models.JSONField(default=list, help_text='["instagram", "google_business", "facebook", "whatsapp"]', verbose_name='plataformas'),
        ),
        migrations.RunPython(_drop_tv, _noop),
    ]
