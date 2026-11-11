"""O link de acesso só sai pelo WhatsApp depois do COMMIT (ADR-025).

O receiver do orquestrador (`handlers/access_link.py`) manda o link pelo ManyChat.
Com o `send` dentro da transação, um rollback de quem chamou `create_token`
deixava enviada uma mensagem com link para um token que nunca existiu.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.db import transaction
from shopman.doorman.conf import get_adapter
from shopman.doorman.models import AccessLink
from shopman.doorman.services.access_link import AccessLinkService
from shopman.guestman.models import Customer

pytestmark = pytest.mark.django_db

ENTREGA = {"deliver": "manychat", "deliver_to": "123456"}


class _Desfaz(Exception):
    pass


@pytest.fixture
def cliente():
    customer = Customer.objects.create(
        ref="ROLLBACK-001", first_name="Ana", phone="5543999990001"
    )
    return get_adapter().identity(customer.uuid, purpose="session")


@pytest.fixture
def notify():
    with patch("shopman.shop.notifications.notify") as mock:
        mock.return_value.success = True
        yield mock


def test_rollback_de_quem_chamou_nao_envia_nada(cliente, notify, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        with pytest.raises(_Desfaz):
            with transaction.atomic():
                result = AccessLinkService.create_token(cliente, metadata=ENTREGA)
                assert result.success
                assert not notify.called, "enviou antes do COMMIT"
                raise _Desfaz

    assert callbacks == []
    assert not notify.called, "mensagem enviada para um token que o rollback apagou"
    assert not AccessLink.objects.filter(customer_id=cliente.subject_id).exists()


def test_depois_do_commit_o_link_sai_uma_vez(cliente, notify, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        result = AccessLinkService.create_token(cliente, metadata=ENTREGA)
        assert not notify.called, "enviou antes do COMMIT"

    assert result.success
    assert notify.call_count == 1
    assert notify.call_args.kwargs["context"]["access_url"] == result.url
