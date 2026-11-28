"""A paleta da marca do storefront vira dado da loja: ``Shop.brand_palette`` (A7-1).

Até aqui a paleta morava em ``shopman/shop/brand_tokens.py`` como código do produto,
e toda loja vestia a marca da Nelson. O orquestrador passa a só montar tokens a partir
de ``Shop.brand_palette``.

Para que o storefront no ar não mude uma cor, esta migração grava no banco, nas lojas
que ainda não têm paleta, a paleta exata que o código emitia (cópia congelada abaixo:
migração representa um momento do banco). Idempotente: loja com paleta gravada não é
tocada. O reverse é inerte.
"""

from django.db import migrations, models

FROZEN_PALETTE = {   'light': {   'background': '245 233 194',
                 'foreground': '59 42 30',
                 'card': '252 246 241',
                 'card_foreground': '59 42 30',
                 'popover': '252 246 241',
                 'popover_foreground': '59 42 30',
                 'primary': '124 58 64',
                 'primary_foreground': '247 239 224',
                 'secondary': '232 216 203',
                 'secondary_foreground': '59 42 30',
                 'muted': '238 223 212',
                 'muted_foreground': '110 90 72',
                 'accent': '239 226 201',
                 'accent_foreground': '59 42 30',
                 'destructive': '180 51 37',
                 'destructive_foreground': '255 255 255',
                 'success': '62 125 68',
                 'success_foreground': '255 255 255',
                 'warning': '194 112 28',
                 'warning_foreground': '255 255 255',
                 'info': '63 110 140',
                 'info_foreground': '255 255 255',
                 'border': '222 201 187',
                 'input': '222 201 187',
                 'ring': '107 80 25',
                 'header': '124 58 64',
                 'header_foreground': '247 239 224',
                 'footer': '48 57 30',
                 'footer_foreground': '255 255 255',
                 'help': '66 82 42',
                 'help_foreground': '255 255 255',
                 'ink': '83 29 34',
                 'ink_foreground': '247 239 224',
                 'bottomnav': '245 231 221',
                 'cta': '139 107 46',
                 'cta_foreground': '255 255 255',
                 'surface': '252 246 241',
                 'surface_hover': '238 223 212',
                 'foreground_muted': '110 90 72',
                 'border_strong': '200 178 160',
                 'primary_hover': '106 49 55',
                 'secondary_hover': '222 201 187',
                 'accent_hover': '230 214 184',
                 'error': '180 51 37',
                 'error_foreground': '255 255 255'},
    'dark': {   'background': '34 22 16',
                'foreground': '240 230 210',
                'card': '43 29 22',
                'card_foreground': '240 230 210',
                'popover': '43 29 22',
                'popover_foreground': '240 230 210',
                'primary': '154 79 86',
                'primary_foreground': '247 239 224',
                'secondary': '58 42 32',
                'secondary_foreground': '240 230 210',
                'muted': '51 36 26',
                'muted_foreground': '194 174 150',
                'accent': '58 42 32',
                'accent_foreground': '240 230 210',
                'destructive': '224 106 94',
                'destructive_foreground': '43 29 22',
                'success': '126 178 110',
                'success_foreground': '34 22 16',
                'warning': '224 154 74',
                'warning_foreground': '34 22 16',
                'info': '111 160 192',
                'info_foreground': '34 22 16',
                'border': '70 53 40',
                'input': '70 53 40',
                'ring': '212 165 63',
                'header': '124 58 64',
                'header_foreground': '247 239 224',
                'footer': '38 45 24',
                'footer_foreground': '255 255 255',
                'help': '54 66 35',
                'help_foreground': '255 255 255',
                'ink': '83 29 34',
                'ink_foreground': '247 239 224',
                'bottomnav': '43 29 22',
                'cta': '150 116 52',
                'cta_foreground': '250 246 237',
                'surface': '43 29 22',
                'surface_hover': '58 42 32',
                'foreground_muted': '194 174 150',
                'border_strong': '90 70 50',
                'primary_hover': '168 90 97',
                'secondary_hover': '70 53 40',
                'accent_hover': '70 53 40',
                'error': '224 106 94',
                'error_foreground': '43 29 22'}}


def forwards(apps, schema_editor):
    Shop = apps.get_model("shop", "Shop")
    for shop in Shop.objects.all():
        if not shop.brand_palette:
            shop.brand_palette = FROZEN_PALETTE
            shop.save(update_fields=["brand_palette"])
    # ``Shop.load`` guarda a loja em cache; o modelo histórico não o esvazia.
    from django.core.cache import cache

    cache.delete("shop_singleton")


class Migration(migrations.Migration):
    dependencies = [("shop", "0099_happy_hour_params_explicit")]

    operations = [
        migrations.AddField(
            model_name="shop",
            name="brand_palette",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Cores do storefront por papel (canais 'R G B'), nos modos claro e escuro.",
                verbose_name="paleta da marca",
            ),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
