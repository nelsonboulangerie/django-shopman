"""Merge das duas folhas 0053 independentes.

As migrações de identidade de Marketing e de confirmação manual alteram
superfícies distintas. Esta migração não executa dados ou DDL; apenas torna a
ordem de aplicação explícita para o release do Django.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0053_disable_remote_auto_confirmation"),
        ("shop", "0053_marketing_delivery_identity"),
    ]

    operations = []
