"""MKT-002+ — contrato de consentimento e supressão do Marketing."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from shopman.guestman import ConsentService
from shopman.guestman.models import Customer

from shopman.shop.services import audience

pytestmark = pytest.mark.django_db


def test_global_optout_suppresses_active_stock_alert_subscription() -> None:
    """A assinatura específica nunca ressuscita um canal globalmente revogado."""

    customer = Customer.objects.create(
        ref="CLI-MKT-OPTOUT",
        first_name="Ana",
        phone="+5543999001001",
    )
    ConsentService.revoke_consent(customer.ref, "whatsapp")

    with patch(
        "shopman.shop.adapters.audience_sources.pending_alert_contacts",
        return_value=[(customer.phone, customer.ref)],
    ):
        resolved = audience.resolve({"alerts": True}, sku="SKU-TESTE")

    assert resolved.total == 0
    assert resolved.all_recipients() == ()
