from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.exceptions import APIException
from shopman.cashman import services as cash
from shopman.cashman.models import Terminal

from shopman.backstage.api.operations import (
    _open_cash_shift_for_request,
    _pos_payload_with_runtime,
    _terminal_do_pedido,
)
from shopman.backstage.station_trust import station_ref
from shopman.backstage.tests.pos_test_runtime import bind_station

pytestmark = pytest.mark.django_db


@pytest.fixture
def drawers():
    user = get_user_model().objects.create_user("station-operator")
    terminals = [Terminal.objects.create(ref=ref) for ref in ("A", "B")]
    return [cash.open_shift(operator=user, terminal=terminal, float_q=0) for terminal in terminals]


def test_request_station_selects_original_drawer_and_discards_forged_shift(drawers):
    request = SimpleNamespace(data={"cash_shift_id": drawers[0].pk}, COOKIES={})
    with patch("shopman.backstage.station_trust.station_ref", return_value="B"):
        assert _open_cash_shift_for_request(request).pk == drawers[1].pk
        payload = _pos_payload_with_runtime(request, request.data)
    assert payload["cash_shift_id"] == drawers[1].pk
    assert payload["pos_terminal_ref"] == "B"


def test_body_cannot_select_a_different_station(drawers):
    request = SimpleNamespace(data={"terminal_ref": "A"}, COOKIES={})
    with patch("shopman.backstage.station_trust.station_ref", return_value="B"):
        with pytest.raises(APIException):
            _terminal_do_pedido(request)


def test_ambiguous_revoked_or_inactive_station_cannot_choose_drawer(client, drawers):
    first = bind_station(client, "A")
    second = bind_station(client, "B")
    request = SimpleNamespace(data={}, COOKIES={k: v.value for k,v in client.cookies.items()}, META={})
    assert station_ref(request) == ""
    second.revoke()
    assert station_ref(request) == "A"
    Terminal.objects.filter(ref="A").update(is_active=False)
    with pytest.raises(APIException):
        _terminal_do_pedido(request)
    first.revoke()
    assert station_ref(request) == ""
