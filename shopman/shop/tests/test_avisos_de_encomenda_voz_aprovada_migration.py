"""A 0082 troca o texto semeado dos avisos de Encomendas pelo aprovado — e só ele."""
from __future__ import annotations

import importlib

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("shop", "0081_order_updated_notification_template")]
AFTER = [("shop", "0082_avisos_de_encomenda_na_voz_aprovada")]


@pytest.mark.django_db(transaction=True)
def test_texto_semeado_vira_o_aprovado_e_o_curado_fica():
    from shopman.shop.notification_copy import CUSTOMER_COPY

    rescheduled = importlib.import_module("shopman.shop.migrations.0080_order_rescheduled_notification_template")

    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE)
    Template = executor.loader.project_state(BEFORE).apps.get_model("shop", "NotificationTemplate")
    # Independe do que o teste anterior deixou no banco: cria/regrava as duas linhas.
    Template.objects.update_or_create(
        event="order_rescheduled", defaults={"subject": rescheduled.SUBJECT, "body": rescheduled.BODY},
    )
    Template.objects.update_or_create(
        event="order_updated", defaults={"subject": "Assunto da loja", "body": "Corpo aprovado pela loja"},
    )

    executor = MigrationExecutor(connection)
    executor.migrate(AFTER)
    Template = executor.loader.project_state(AFTER).apps.get_model("shop", "NotificationTemplate")

    assert Template.objects.get(event="order_rescheduled").body == CUSTOMER_COPY["order_rescheduled"]["body"]
    assert Template.objects.get(event="order_updated").body == "Corpo aprovado pela loja"

    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE)
    Template = executor.loader.project_state(BEFORE).apps.get_model("shop", "NotificationTemplate")
    assert Template.objects.get(event="order_rescheduled").body == rescheduled.BODY
