from __future__ import annotations

from datetime import UTC, datetime, time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_invoice_conversion_requirement_distinguishes_base_units_packages_and_declared_conversion():
    from shopman.shop.adapters import purchase_invoice_nfe

    package = SimpleNamespace(unit="CX", quantity=1)
    base_unit = SimpleNamespace(unit="KG", quantity=1)

    assert purchase_invoice_nfe._requires_conversion(package, material=None, conversion=None) is True
    assert purchase_invoice_nfe._requires_conversion(base_unit, material=None, conversion=None) is False
    assert purchase_invoice_nfe._requires_conversion(package, material=None, conversion=object()) is False


def test_allowed_hosts_safety_is_fail_closed_only_outside_debug(settings):
    from shopman.shop import checks

    settings.DEBUG = True
    settings.ALLOWED_HOSTS = []
    assert checks.check_allowed_hosts(None) == []

    settings.DEBUG = False
    for unsafe in ([], ["*"]):
        settings.ALLOWED_HOSTS = unsafe
        assert [message.id for message in checks.check_allowed_hosts(None)] == ["SHOPMAN_E002"]

    settings.ALLOWED_HOSTS = ["shop.example.test"]
    assert checks.check_allowed_hosts(None) == []


def test_publication_canary_requires_an_enabled_isolated_runtime(settings):
    from django.core.management.base import CommandError

    from shopman.shop.management.commands import run_marketing_publication_canary

    settings.SHOPMAN_MARKETING_PUBLICATION_CANARY_ENABLED = False
    settings.SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED = False
    settings.SHOPMAN_MARKETING_DELIVERY_CONSUMER_ENABLED = False
    with pytest.raises(CommandError, match="canário público está desligado"):
        run_marketing_publication_canary._require_isolated_runtime()

    settings.SHOPMAN_MARKETING_PUBLICATION_CANARY_ENABLED = True
    settings.SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED = True
    with pytest.raises(CommandError, match="consumer global da outbox"):
        run_marketing_publication_canary._require_isolated_runtime()

    settings.SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED = False
    settings.SHOPMAN_MARKETING_DELIVERY_CONSUMER_ENABLED = True
    with pytest.raises(CommandError, match="consumer global de entrega"):
        run_marketing_publication_canary._require_isolated_runtime()

    settings.SHOPMAN_MARKETING_DELIVERY_CONSUMER_ENABLED = False
    run_marketing_publication_canary._require_isolated_runtime()


def test_probe_host_safety_accepts_only_internal_probes_and_uses_a_concrete_host(settings):
    from shopman.shop import middleware

    settings.ALLOWED_HOSTS = ["*", ".example.test", "api.example.test"]
    assert middleware._canonical_allowed_host() == "api.example.test"
    assert middleware._is_app_platform_probe_host("100.127.25.212:8000") is True
    assert middleware._is_app_platform_probe_host("203.0.113.20") is False

    settings.ALLOWED_HOSTS = ["*", ".example.test"]
    assert middleware._canonical_allowed_host() == "localhost"


def test_catalog_external_write_authorization_is_explicit_and_fail_closed(settings):
    from shopman.shop.adapters import catalog_projection_ifood

    merchant = "00000000-0000-4000-8000-000000000001"
    settings.SHOPMAN_IFOOD_CATALOG_WRITE_POLICY = {
        "environment": "test",
        "merchant_allowlist": [merchant],
    }

    catalog_projection_ifood.ensure_catalog_write_allowed({"merchant_id": merchant})

    settings.SHOPMAN_IFOOD_CATALOG_WRITE_POLICY["merchant_allowlist"] = []
    with pytest.raises(catalog_projection_ifood.IFoodCatalogWriteBlocked, match="política explícita"):
        catalog_projection_ifood.ensure_catalog_write_allowed({"merchant_id": merchant})


def test_fiscal_explicit_request_resolvers_read_only_the_current_sale():
    from shopman.shop import fiscal_resolvers

    tax_request = SimpleNamespace(data={"fiscal": {"tax_id": "12345678909"}})
    receipt_request = SimpleNamespace(data={"receipt": {"channels": ["email"]}})
    customer_profile_only = SimpleNamespace(data={"customer": {"tax_id": "12345678909"}, "fiscal": {}, "receipt": {}})

    assert fiscal_resolvers.on_request_or_tax_id(tax_request) is True
    assert fiscal_resolvers.on_request_or_tax_id(receipt_request) is True
    assert fiscal_resolvers.on_request_or_tax_id(customer_profile_only) is False
    assert fiscal_resolvers.on_requested_receipt(receipt_request) is True
    assert fiscal_resolvers.on_requested_receipt(customer_profile_only) is False


def test_fiscal_debug_safety_blocks_emission_only_in_debug(settings):
    from shopman.shop import fiscal_resolvers

    settings.DEBUG = False
    assert fiscal_resolvers.not_in_debug(SimpleNamespace()) is True

    settings.DEBUG = True
    assert fiscal_resolvers.not_in_debug(SimpleNamespace()) is False


def test_operator_agreed_delivery_fee_requires_value_and_operator_signature():
    from shopman.shop import modifiers

    signed = {
        "delivery_fee_override_q": "900",
        "pos": {"delivery_fee_agreed": {"by": "marina", "at": "2026-10-17T10:00:00-03:00"}},
    }

    assert modifiers.operator_agreed_delivery_fee_q(signed) == 900
    assert modifiers.operator_agreed_delivery_fee_q({"delivery_fee_override_q": 900}) is None
    assert (
        modifiers.operator_agreed_delivery_fee_q({"delivery_fee_override_q": "invalid", "pos": signed["pos"]}) is None
    )


def test_temporal_offer_parses_and_evaluates_an_overnight_window(monkeypatch):
    from shopman.shop import modifiers
    from shopman.shop.rules import engine

    params = {"start": "23:00", "end": "01:00", "discount_percent": 20}
    monkeypatch.setattr(engine, "get_channel_rule_params", lambda rule, channel: params)
    monkeypatch.setattr(modifiers, "_discount_label", lambda key, fallback: "Happy Hour")
    monkeypatch.setattr(modifiers.timezone, "localtime", lambda value: value)
    now = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)

    assert modifiers._parse_time("invalid", "17:30") == time(17, 30)
    assert modifiers.in_time_window(time(23), time(1), time(23, 30)) is True
    assert modifiers.in_time_window(time(23), time(1), time(12)) is False

    offer = modifiers.time_window_offer("pdv", now=now)

    assert offer is not None
    assert offer.active is True
    assert offer.start == time(23)
    assert offer.end == time(1)
    assert offer.discount_percent == 20
    assert offer.label == "Happy Hour"
    assert offer.seen_at == now


@pytest.mark.parametrize(
    ("retryable", "expected_error"),
    [(True, "DirectiveTransientError"), (False, "DirectiveTerminalError")],
)
def test_ifood_interruption_handler_classifies_merchant_failures(monkeypatch, retryable, expected_error):
    from shopman.orderman import exceptions

    from shopman.shop.handlers.ifood_merchant import IFoodMerchantInterruptionHandler
    from shopman.shop.services import ifood_merchant

    apply = MagicMock(side_effect=ifood_merchant.MerchantAPIError("merchant failed", retryable=retryable))
    monkeypatch.setattr(ifood_merchant, "apply_interruption", apply)
    handler = IFoodMerchantInterruptionHandler()
    error = getattr(exceptions, expected_error)

    handler.handle(message=SimpleNamespace(payload={}), ctx={})
    apply.assert_not_called()
    with pytest.raises(error, match="merchant failed"):
        handler.handle(message=SimpleNamespace(payload={"interruption_pk": 17}), ctx={})
    apply.assert_called_once_with(17)


def test_production_lifecycle_receiver_routes_known_action_and_ignores_unknown(monkeypatch):
    from shopman.shop import production_lifecycle

    dispatch = MagicMock()
    monkeypatch.setattr(production_lifecycle, "dispatch_production", dispatch)
    work_order = SimpleNamespace(ref="WO-1")

    production_lifecycle.on_production_changed_receiver(
        sender=object(),
        product_ref="PAO-1",
        date=None,
        work_order=work_order,
        action="finished",
    )
    production_lifecycle.on_production_changed_receiver(
        sender=object(),
        product_ref="PAO-1",
        date=None,
        work_order=work_order,
        action="unknown",
    )

    dispatch.assert_called_once_with(work_order, "on_finished")


def test_purchase_policy_resolves_shop_overrides_and_typed_minimums(monkeypatch):
    from shopman.shop.models import Shop
    from shopman.shop.purchase_policy import PurchasePolicy, resolve_purchase_policy

    shop = SimpleNamespace(
        defaults={
            "purchase": {
                "consumption_window_days": "21",
                "review_period_days": -3,
                "safety_days": "invalid",
            }
        }
    )
    monkeypatch.setattr(Shop, "load", lambda: shop)

    policy = resolve_purchase_policy()

    assert isinstance(policy, PurchasePolicy)
    assert policy.consumption_window_days == 21
    assert policy.review_period_days == 0
    assert policy.safety_days == 2


def test_pos_discount_threshold_honors_shop_override_and_explicit_zero(monkeypatch):
    from shopman.shop.models import Shop
    from shopman.shop.services import pos

    shop = SimpleNamespace(defaults={"pos": {"discount_approval_threshold_q": "750"}})
    monkeypatch.setattr(Shop, "load", lambda: shop)
    assert pos.discount_approval_threshold_q() == 750

    shop.defaults["pos"]["discount_approval_threshold_q"] = 0
    assert pos.discount_approval_threshold_q() == 0


def test_pos_fiscal_toggle_follows_the_shop_configuration(monkeypatch):
    from shopman.shop.models import Shop
    from shopman.shop.services import pos

    shop = SimpleNamespace(defaults={"pos": {"fiscal_toggle": True}})
    monkeypatch.setattr(Shop, "load", lambda: shop)
    assert pos.fiscal_toggle_enabled() is True

    shop.defaults = {"pos": {}}
    assert pos.fiscal_toggle_enabled() is False


def test_delivery_geography_uses_the_highest_priority_matching_zone(monkeypatch):
    from shopman.shop.models import DeliveryZone
    from shopman.shop.services import promotions

    expected = SimpleNamespace(ref="centro", priority=100)
    match = MagicMock(return_value=expected)
    monkeypatch.setattr(DeliveryZone, "match", match)

    assert promotions.match_delivery_zone("86000-000", "Centro") is expected
    match.assert_called_once_with(postal_code="86000-000", neighborhood="Centro")


def test_whatsapp_access_link_discards_unsafe_return_destinations(monkeypatch):
    from shopman.doorman.services import link_state

    from shopman.shop.services import whatsapp_verify

    stored: list[dict] = []

    def store_state(state):
        stored.append(dict(state))
        return f"NB-{len(stored)}"

    monkeypatch.setattr(link_state, "store_state", store_state)
    monkeypatch.setattr(whatsapp_verify, "_wa_number", lambda: "5543999999999")
    monkeypatch.setattr(whatsapp_verify, "_access_message_text", lambda code: code)
    monkeypatch.setattr(whatsapp_verify, "_access_deep_link", lambda code, number: f"{number}/{code}")

    whatsapp_verify.start_access_link(next_path="https://evil.example/phish")
    whatsapp_verify.start_access_link(next_path="//evil.example/phish")
    whatsapp_verify.start_access_link(next_path="/finalizar")

    assert stored == [{}, {}, {}]


def test_ifood_cancellation_enqueue_keeps_an_existing_request_pending(monkeypatch):
    from shopman.shop.services import ifood_cancellation

    order = SimpleNamespace()
    monkeypatch.setattr(ifood_cancellation, "is_pending", lambda candidate: candidate is order)

    assert ifood_cancellation.enqueue_locked(order, reason="Sem estoque", actor="operador", extra_data=None)


def test_ifood_cancellation_refusal_reason_uses_known_and_descriptive_fields():
    from shopman.shop.services import ifood_cancellation

    assert ifood_cancellation.refusal_reason({"description": "  Pedido já saiu  "}) == "Pedido já saiu"
    assert ifood_cancellation.refusal_reason({"merchantReason": "  Loja fechada  "}) == "Loja fechada"
    assert ifood_cancellation.refusal_reason(["invalid"]) == ""
