"""A paleta da marca ganha a cor do texto de promoção (``promotion``), por tema (OC-30).

O texto de promoção da loja ("Semana do Pão -15%", desconto da sacola e do pedido) usava
a cor de ação (``primary``). No tema escuro da Nelson o primary (154 79 86) dá 3,05:1 sobre
o fundo e reprova o AA a 14 px; a escala Burgundy da marca já tem o tom que passa, o 300
(185 123 130: 5,22:1 no fundo, 4,82:1 no cartão).

Esta migração grava ``promotion`` nas paletas já salvas que ainda não a têm:

- tema claro: o próprio ``primary`` da loja (nada muda na tela);
- tema escuro: o Burgundy-300 quando a paleta escura é a da Nelson (``primary`` 154 79 86,
  o valor que a ``shop.0100`` gravou); em qualquer outra paleta, o ``primary`` escuro dela,
  para que a loja não mude de cor sem quem cuida da marca escolher.

Loja sem paleta continua sem (a loja usa a neutra). Idempotente; o reverse é inerte.
"""

from django.db import migrations

NELSON_DARK_PRIMARY = "154 79 86"
BURGUNDY_300 = "185 123 130"


def add_promotion(apps, schema_editor):
    Shop = apps.get_model("shop", "Shop")
    for shop in Shop.objects.all():
        palette = shop.brand_palette
        if not isinstance(palette, dict) or not palette:
            continue
        changed = False
        light = palette.get("light")
        if isinstance(light, dict) and "promotion" not in light and light.get("primary"):
            light["promotion"] = light["primary"]
            changed = True
        dark = palette.get("dark")
        if isinstance(dark, dict) and "promotion" not in dark and dark.get("primary"):
            dark["promotion"] = BURGUNDY_300 if dark["primary"] == NELSON_DARK_PRIMARY else dark["primary"]
            changed = True
        if changed:
            shop.brand_palette = palette
            shop.save(update_fields=["brand_palette"])


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0138_canais_remotos_esperam_a_cozinha"),
    ]

    operations = [
        migrations.RunPython(add_promotion, migrations.RunPython.noop),
    ]
