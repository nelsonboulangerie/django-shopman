"""O tablet acompanha o pulso da gaveta no PostgreSQL real (alpha, 10/10/2026).

No alpha, ``GET pos/cash/drawer-pulse/<ref>/`` voltava 400 a cada segundo:
``reconcile_job_state`` travava o trabalho com ``select_for_update()`` junto de um
``select_related`` do terminal, que é FK anulável, e o PostgreSQL recusa ``FOR
UPDATE`` no lado anulável do OUTER JOIN. O SQLite ignora ``FOR UPDATE`` e o
teste de sempre (``test_drawer_pulse_tolerance``) passava. Aqui, cada estado final
do pulso é lido pelo endpoint, no banco de produção.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from shopman.backstage.models import PrintAttempt, PrintJob
from shopman.backstage.services import print_jobs
from shopman.backstage.tests.pos_test_runtime import bind_station
from shopman.backstage.tests.test_drawer_pulse_tolerance import _cash_sale, credential, operator, shift  # noqa: F401

requires_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="FOR UPDATE no lado anulável de um OUTER JOIN só falha no PostgreSQL",
)

pytestmark = [pytest.mark.django_db, requires_postgres]


@pytest.mark.parametrize(
    ("outcome", "state"),
    [("expired", "expired"), ("spooled", "sent"), ("lease_lost", "uncertain")],
)
def test_o_tablet_le_o_pulso_ate_o_fim(client, shift, operator, credential, outcome, state):  # noqa: F811
    _cash_sale(shift, operator)
    client.force_login(operator)
    bind_station(client, shift.terminal.ref)
    opened = client.post(
        reverse("api-backstage-pos-cash-drawer-open"),
        data={"purpose": "sale", "order_ref": "M6-1012", "via": "relay"},
        content_type="application/json",
    )
    assert opened.status_code == 200, opened.content
    ref = opened.json()["pulse"]["ref"]

    if outcome == "expired":
        PrintJob.objects.filter(ref=ref).update(expires_at=timezone.now() - timedelta(seconds=1))
    else:
        job, attempt, lease = print_jobs.claim_next_job(credential=credential, telemetry={})
        if outcome == "spooled":
            print_jobs.acknowledge_job(
                credential=credential,
                job_ref=job.ref,
                status="spooled",
                spooler_job_id="cups-1",
                detail="",
                payload_sha256=job.payload_sha256,
                lease_token=lease,
                telemetry={},
            )
        else:
            PrintAttempt.objects.filter(pk=attempt.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))

    response = client.get(reverse("api-backstage-pos-cash-drawer-pulse", args=[ref]))

    assert response.status_code == 200, response.content
    assert response.json()["pulse"]["state"] == state
