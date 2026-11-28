"""A identidade da sessão vem do resolver CONFIGURADO, e a falha grita.

``identity_by_customer_ref`` instanciava ``IdentityResolver()`` do Guestman
direto: trocar ``DOORMAN["IDENTITY_RESOLVER_CLASS"]`` não mudava esta porta, e
uma exceção virava ``None`` com ``logger.debug`` (laudo de soberania, WP-4).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from shopman.shop.services import auth


class _Resolver:
    def __init__(self, identity=None, error=None):
        self.identity = identity
        self.error = error
        self.calls = []

    def get(self, subject_id, *, purpose):
        self.calls.append((subject_id, purpose))
        if self.error:
            raise self.error
        return self.identity


def _customer():
    return SimpleNamespace(uuid=uuid4())


def test_uses_the_configured_resolver():
    customer = _customer()
    identity = SimpleNamespace(is_active=True)
    resolver = _Resolver(identity=identity)
    with (
        patch.object(auth, "customer_by_ref", return_value=customer),
        patch("shopman.doorman.conf.get_identity_resolver", return_value=resolver),
    ):
        assert auth.identity_by_customer_ref("CUST-1") is identity
    assert resolver.calls == [(customer.uuid, "session")]


def test_inactive_identity_is_no_identity():
    resolver = _Resolver(identity=SimpleNamespace(is_active=False))
    with (
        patch.object(auth, "customer_by_ref", return_value=_customer()),
        patch("shopman.doorman.conf.get_identity_resolver", return_value=resolver),
    ):
        assert auth.identity_by_customer_ref("CUST-1") is None


def test_resolver_failure_closes_and_is_logged():
    resolver = _Resolver(error=RuntimeError("guestman fora"))
    with (
        patch.object(auth, "customer_by_ref", return_value=_customer()),
        patch("shopman.doorman.conf.get_identity_resolver", return_value=resolver),
        patch.object(auth, "logger") as logger,
    ):
        assert auth.identity_by_customer_ref("CUST-1") is None
    logger.warning.assert_called_once()
    assert logger.warning.call_args.args[0].startswith("auth.identity_by_customer_ref failed")
    assert logger.warning.call_args.kwargs["exc_info"] is True
