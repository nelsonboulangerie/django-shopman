"""O ``webhook_failed`` fecha quando o MESMO provedor volta a entregar (#3096).

Os dois avisos da primeira rodada da ponte (maquininha 17/11, assinatura em base64
corrigida em 19/11; iFood 07/11, 500 sem reincidência) ficavam abertos para sempre:
nada no domínio os encerrava. O fato que os desmente é uma entrega bem-sucedida
do mesmo provedor.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from shopman.backstage.models import OperatorAlert
from shopman.shop.services import observability
from shopman.shop.tests.test_machine_webhook import MACHINE, _client, _url

pytestmark = pytest.mark.django_db


def _failed(provider, reason="processing_failed"):
    observability.record_webhook_failure(provider=provider, reason=reason, status_code=500)
    return OperatorAlert.objects.get(type="webhook_failed", message__startswith=f"Webhook {provider} falhou")


def _open(alert):
    alert.refresh_from_db()
    return alert.resolved_at is None


def test_success_closes_only_the_same_provider():
    ifood = _failed("ifood")
    machine = _failed("machine", "signature_mismatch")

    assert observability.record_webhook_success("ifood") == 1
    assert not _open(ifood)
    ifood.refresh_from_db()
    assert ifood.resolved_by == "sistema: webhook ifood voltou a entregar"
    assert _open(machine), "outro provedor: a falha dele continua de pé"


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_a_signed_machine_delivery_closes_the_signature_alert():
    alert = _failed("machine", "signature_mismatch")
    response = _client().post(_url(), {"data": []}, format="json")
    assert response.status_code == 200
    assert not _open(alert)
