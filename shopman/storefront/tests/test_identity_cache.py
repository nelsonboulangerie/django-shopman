from types import SimpleNamespace
from unittest.mock import MagicMock


def test_authenticated_customer_is_resolved_once_per_request(monkeypatch):
    from shopman.shop.services import auth as auth_service
    from shopman.storefront.identity import get_authenticated_customer

    customer = object()
    resolver = MagicMock(return_value=customer)
    monkeypatch.setattr(auth_service, "customer_by_uuid", resolver)
    request = SimpleNamespace(customer=SimpleNamespace(uuid="customer-uuid"))

    assert get_authenticated_customer(request) is customer
    assert get_authenticated_customer(request) is customer
    resolver.assert_called_once_with("customer-uuid")


def test_anonymous_customer_miss_is_cached_per_request(monkeypatch):
    from shopman.shop.services import auth as auth_service
    from shopman.storefront.identity import get_authenticated_customer

    resolver = MagicMock()
    monkeypatch.setattr(auth_service, "customer_by_uuid", resolver)
    request = SimpleNamespace(customer=None)

    assert get_authenticated_customer(request) is None
    assert get_authenticated_customer(request) is None
    resolver.assert_not_called()


def test_dynamic_proxy_attribute_is_not_mistaken_for_cached_customer(monkeypatch):
    from shopman.shop.services import auth as auth_service
    from shopman.storefront.identity import get_authenticated_customer

    resolver = MagicMock()
    monkeypatch.setattr(auth_service, "customer_by_uuid", resolver)
    request = MagicMock()
    request.customer = None

    assert get_authenticated_customer(request) is None
    assert get_authenticated_customer(request) is None
    resolver.assert_not_called()
