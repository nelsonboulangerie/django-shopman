"""O resto do rename: nomes de índice e os textos que o Django rastreia.

Índice do Django carrega o nome da tabela no próprio nome (`shop_broadc_…`), e a
0029 renomeou os modelos sem tocar nisso — então o schema ficaria falando
`broadc` para tabelas que hoje são `campaign` e `announcement`. Não é cosmético:
sem estes renames, `makemigrations --check` acusa drift para sempre, e o gate de
migrations do projeto (`scripts/check_migrations.py`) fica vermelho.

Junto vêm os textos que o Django versiona:

- `Campaign.notify_users` — o help_text citava "gerenciar broadcast";
- `UserNotification.category` — a escolha `broadcast` virou `campaign`;
- `UserNotification.action_data` — o help_text citava `broadcast_post_id`.

Os **dados** dessas duas colunas de `UserNotification` já foram convertidos na
0030; aqui só o schema/choices acompanha.

Refs ADR-020 §1, plano F2.
"""

from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0030_campaign_rename_persisted_strings"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="announcement",
            new_name="shop_announ_status_ee232f_idx",
            old_name="shop_broadc_status_21e56f_idx",
        ),
        migrations.RenameIndex(
            model_name="announcement",
            new_name="shop_announ_expires_b2b531_idx",
            old_name="shop_broadc_expires_a3fe63_idx",
        ),
        migrations.RenameIndex(
            model_name="announcement",
            new_name="shop_announ_publish_232a90_idx",
            old_name="shop_broadc_publish_ebcbc7_idx",
        ),
        migrations.RenameIndex(
            model_name="campaign",
            new_name="shop_campai_trigger_545705_idx",
            old_name="shop_broadc_trigger_a01f8c_idx",
        ),
    ]
