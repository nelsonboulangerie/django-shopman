from __future__ import annotations

import importlib

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from shopman.shop.notification_copy import CUSTOMER_COPY

migration = importlib.import_module("shopman.shop.migrations.0092_avisos_de_estorno_e_devolucao")

BEFORE = [("shop", "0091_digital_do_dispositivo_do_operador")]
AFTER = [("shop", "0092_avisos_de_estorno_e_devolucao")]


def test_migracao_grava_a_mesma_frase_da_fonte_unica():
    assert migration.REFUND_SUBJECT == CUSTOMER_COPY["payment_refunded"]["subject"]
    assert migration.REFUND_BODY == CUSTOMER_COPY["payment_refunded"]["body"]
    assert migration.RETURN_SUBJECT == CUSTOMER_COPY["order_returned"]["subject"]
    assert migration.RETURN_BODY == CUSTOMER_COPY["order_returned"]["body"]


@pytest.mark.django_db(transaction=True)
def test_migracao_troca_o_texto_de_fabrica_cria_a_devolucao_e_preserva_o_curado():
    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE)
    Old = executor.loader.project_state(BEFORE).apps.get_model("shop", "NotificationTemplate")
    Old.objects.filter(event__in=["payment_refunded", "order_returned"]).delete()
    Old.objects.create(
        event="payment_refunded",
        subject=migration.REFUND_OLD_SUBJECT,
        body=migration.REFUND_OLD_BODIES[1],
        is_active=True,
    )

    executor = MigrationExecutor(connection)
    executor.migrate(AFTER)
    New = executor.loader.project_state(AFTER).apps.get_model("shop", "NotificationTemplate")
    refund = New.objects.get(event="payment_refunded")
    assert (refund.subject, refund.body) == (migration.REFUND_SUBJECT, migration.REFUND_BODY)
    returned = New.objects.get(event="order_returned")
    assert returned.body == migration.RETURN_BODY

    # Texto reescrito no Admin não é tocado.
    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE)
    Old = executor.loader.project_state(BEFORE).apps.get_model("shop", "NotificationTemplate")
    assert not Old.objects.filter(event="order_returned").exists()
    Old.objects.filter(event="payment_refunded").update(subject="Curado", body="Corpo curado")

    executor = MigrationExecutor(connection)
    executor.migrate(AFTER)
    New = executor.loader.project_state(AFTER).apps.get_model("shop", "NotificationTemplate")
    curated = New.objects.get(event="payment_refunded")
    assert (curated.subject, curated.body) == ("Curado", "Corpo curado")
