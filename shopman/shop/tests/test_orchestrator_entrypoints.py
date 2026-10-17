"""Direct contracts for orchestration entrypoints tracked by the manifest."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from django.test import override_settings
from django.utils import timezone

from shopman.shop.product_options import resolve_selection
from shopman.shop.production_lifecycle import dispatch_production
from shopman.shop.resale_markup import ResaleMarkup, resolve_resale_markup
from shopman.shop.rules.pricing import HappyHourRule
from shopman.shop.services.channel_switch import state_line
from shopman.shop.services.order_edit import (
    require_delivery_identity,
)
from shopman.shop.services.order_edit import (
    state_refusal as order_edit_state_refusal,
)
from shopman.shop.services.order_edit import (
    stock_refusal as order_edit_stock_refusal,
)
from shopman.shop.services.pos import (
    PosIntentError,
    _commit_refusal,
    _enforce_pix_payment_policy,
    _pix_payment_policy_error,
    _require_confirmed_pix_in_mixed,
    _require_contact_if_payment_link,
    _require_customer_if_scheduled,
    _require_delivery_coverage,
    _require_delivery_fiscal_identity,
    _require_delivery_minimum,
    _require_house_account_if_on_account,
    _require_open_shift,
    _require_order_mode_if_payment_link,
    pix_payment_policy_warning,
    resolve_or_create_customer,
    should_refresh_name,
)
from shopman.shop.services.pos_edit_session import schedule_refusal
from shopman.shop.services.reschedule import (
    state_refusal as reschedule_state_refusal,
)
from shopman.shop.services.reschedule import (
    stock_refusal as reschedule_stock_refusal,
)
from shopman.shop.services.stock import require_current_sellability
from shopman.shop.views.health import _check_required_workers


def test_product_option_selection_accepts_a_product_without_options():
    product = SimpleNamespace(name="Pão", metadata={})

    assert resolve_selection(product, []) == []


def test_production_lifecycle_dispatch_calls_the_selected_phase():
    work_order = SimpleNamespace(recipe=SimpleNamespace(meta={}))
    handler = MagicMock()

    with patch.dict(
        "shopman.shop.production_lifecycle._PRODUCTION_PHASE_HANDLERS",
        {"standard": {"on_started": handler}},
        clear=True,
    ):
        dispatch_production(work_order, "on_started")

    handler.assert_called_once_with(work_order)


def test_resale_markup_policy_exposes_its_value_and_resolves_store_defaults():
    configured = ResaleMarkup(default_pct=60, by_collection={"mercearia": 75})
    assert configured.pct_for("mercearia") == (75, "mercearia")

    with patch("shopman.shop.models.Shop.load", return_value=None):
        resolved = resolve_resale_markup()

    assert resolved == ResaleMarkup()


def test_pricing_rule_constructs_the_authoritative_happy_hour_policy():
    rule = HappyHourRule(discount_percent=15, start="16:00", end="17:00")

    assert rule.discount_percent == 15
    assert rule.start.hour == 16
    assert rule.end.hour == 17


def test_channel_switch_state_line_reports_an_inactive_unconfigured_channel():
    channel = SimpleNamespace(config={}, is_active=False)
    now = datetime(2026, 10, 17, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))

    assert state_line(channel, now=now) == "Desligado."


def test_order_edit_delivery_identity_accepts_a_pickup_order():
    order = SimpleNamespace(
        data={"fulfillment_type": "pickup"},
        channel_ref="web",
        ref="ORD-42",
    )

    require_delivery_identity(order, {}, total_q=1_000)


def test_order_edit_state_refusal_explains_a_cancelled_order():
    refusal = order_edit_state_refusal(SimpleNamespace(status="cancelled", channel_ref="web"))

    assert refusal[0] == "order_not_editable"


def test_order_edit_stock_refusal_preserves_the_stock_error():
    refusal = order_edit_stock_refusal(
        SimpleNamespace(),
        SimpleNamespace(code="stock_error", message="Estoque indisponível."),
        [],
    )

    assert refusal == "Estoque indisponível. Nada foi alterado."


def test_pos_commit_refusal_preserves_the_rule_dialect():
    refusal = _commit_refusal(SimpleNamespace(code="rule_refused", message="Revise a venda.", context={}))

    assert refusal.code == "rule_refused"
    assert refusal.message == "Revise a venda."


def test_pos_pix_policy_uses_one_evaluator_for_warning_and_enforcement():
    payload = {"payment_method": "cash", "items": []}

    assert _pix_payment_policy_error(payload) is None
    _enforce_pix_payment_policy(payload)


def test_pos_mixed_pix_gate_accepts_a_sale_without_pix():
    _require_confirmed_pix_in_mixed({"payment_tenders": []})


def test_pos_payment_link_eligibility_accepts_an_immediate_cash_sale():
    payload = {"payment_method": "cash", "sales_mode": "counter"}

    _require_order_mode_if_payment_link(payload)
    _require_contact_if_payment_link(payload)


def test_pos_scheduled_customer_gate_ignores_an_immediate_pickup():
    _require_customer_if_scheduled({"fulfillment_type": "pickup"})


def test_pos_delivery_fiscal_identity_gate_ignores_a_pickup():
    _require_delivery_fiscal_identity({"fulfillment_type": "pickup"}, channel_ref="counter")


def test_pos_delivery_minimum_gate_ignores_a_pickup():
    _require_delivery_minimum({"fulfillment_type": "pickup"})


def test_pos_delivery_coverage_gate_accepts_a_covered_address():
    delivery = SimpleNamespace(blocked=False, distance_km=1.5)
    with patch("shopman.shop.services.pos._resolve_delivery_fee", return_value=delivery):
        _require_delivery_coverage({"fulfillment_type": "delivery"})


def test_pos_house_account_gate_ignores_other_payment_methods():
    _require_house_account_if_on_account({}, payment_method="cash", tenders=[])


def test_pos_open_shift_gate_refuses_a_missing_shift():
    with pytest.raises(PosIntentError, match="Abra o caixa"):
        _require_open_shift({})


def test_pos_profile_refresh_distinguishes_placeholder_names():
    assert should_refresh_name(SimpleNamespace(first_name="Cliente", last_name="0042"))
    assert not should_refresh_name(SimpleNamespace(first_name="Ana", last_name="Silva"))
    with patch(
        "shopman.shop.services.pos._persist_customer_from_payload",
        return_value={"ref": "CUS-42"},
    ):
        resolved = resolve_or_create_customer(name="Ana Silva", operator_username="caixa")

    assert resolved == {"ref": "CUS-42"}


def test_pos_edit_schedule_refusal_accepts_a_valid_schedule():
    with patch("shopman.shop.services.pos._validate_schedule"):
        assert schedule_refusal({"delivery_date": "2026-10-18"}) == ""


def test_pos_pix_policy_warning_accepts_a_non_pix_sale():
    assert (
        pix_payment_policy_warning(
            {"payment_method": "cash", "items": []},
            total_q=0,
            payment_method="cash",
            tenders=[],
        )
        is None
    )


def test_reschedule_state_refusal_explains_a_cancelled_order():
    refusal = reschedule_state_refusal(SimpleNamespace(status="cancelled", channel_ref="web"))

    assert "cancelado" in refusal


def test_reschedule_stock_refusal_preserves_the_stock_error():
    refusal = reschedule_stock_refusal(
        SimpleNamespace(),
        SimpleNamespace(code="stock_error", message="Estoque indisponível."),
        datetime(2026, 10, 18).date(),
    )

    assert refusal == "Estoque indisponível. Nada foi alterado."


def test_stock_sellability_gate_accepts_an_unlisted_unknown_sku():
    adapter = MagicMock()
    with (
        patch("shopman.shop.services.stock._sku_known_to_catalog", return_value=False),
        patch(
            "shopman.shop.services.availability._sku_in_channel_listing",
            return_value=None,
        ),
    ):
        require_current_sellability(
            adapter,
            {"sku": "SKU-42", "name": "Pão"},
            "SKU-42",
            1,
            channel_ref="counter",
        )

    adapter.get_availability.assert_not_called()


@override_settings(
    SHOPMAN_REQUIRED_WORKERS=(),
    SHOPMAN_WORKER_STARTUP_GRACE_SECONDS=0,
)
def test_required_worker_readiness_accepts_an_empty_explicit_requirement():
    assert _check_required_workers(timezone.now()) == ("ok", None)
