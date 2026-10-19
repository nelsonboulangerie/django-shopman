from __future__ import annotations

from contextlib import nullcontext
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest


def test_active_subject_lock_rejects_a_missing_active_customer(monkeypatch):
    from shopman.guestman.models import Customer

    from shopman.shop.services import account

    query = MagicMock()
    query.filter.return_value = query
    query.first.return_value = None
    monkeypatch.setattr(Customer, "objects", SimpleNamespace(select_for_update=lambda: query))

    with pytest.raises(account.AccountUnavailable, match="customer_unavailable"):
        account.lock_active_customer(customer_ref="CUS-MISSING")

    assert query.filter.call_args_list == [call(is_active=True), call(ref="CUS-MISSING")]


def test_account_addresses_delegates_the_customer_reference(monkeypatch):
    from shopman.guestman.services import address as address_service

    from shopman.shop.services import account

    expected = [SimpleNamespace(pk=1)]
    delegated = MagicMock(return_value=expected)
    monkeypatch.setattr(address_service, "addresses", delegated)

    assert account.addresses("CUS-1") is expected
    delegated.assert_called_once_with("CUS-1")


def test_adult_declaration_preserves_the_first_committed_declaration():
    from shopman.shop.services import account
    from shopman.shop.services.marketing_age import ADULT_DECLARATION_KEY

    declaration = {"at": "2026-01-01T00:00:00", "terms_version": "terms-v1", "source": "login"}
    customer = SimpleNamespace(metadata={ADULT_DECLARATION_KEY: declaration})

    assert account.record_adult_declaration(customer) is declaration


def test_phone_change_request_rejects_an_empty_new_number():
    from shopman.shop.services import account

    with pytest.raises(account.PhoneChangeRefused) as caught:
        account.request_phone_change(SimpleNamespace(pk=1), "")

    assert caught.value.field == "phone"
    assert caught.value.error_code == "invalid_phone"


def test_order_erasure_is_blocked_by_an_active_order(monkeypatch):
    from shopman.shop.services import account

    class Orders:
        def select_for_update(self):
            return self

        def order_by(self, _field):
            return [SimpleNamespace(ref="ORD-1", status="preparing")]

    monkeypatch.setattr(account, "_customer_orders", lambda _ref, _phone: Orders())

    assert account.privacy_order_deletion_blocker("CUS-1", "+5543999999999") == "active_order"


def test_otp_erasure_is_blocked_by_a_committed_pending_delivery(monkeypatch):
    from shopman.doorman.models import VerificationCode

    from shopman.shop.services import account

    query = MagicMock()
    query.filter.return_value = query
    query.exists.return_value = True
    monkeypatch.setattr(VerificationCode, "objects", query)

    customer = SimpleNamespace(uuid="customer-uuid")
    assert account.privacy_otp_deletion_blocker(customer) == "otp_delivery_in_flight"
    assert query.filter.call_count == 2


def test_profile_update_preserves_fields_absent_from_the_intent(monkeypatch):
    from shopman.guestman.services import customer as customer_service

    from shopman.shop.sentinels import UNSET
    from shopman.shop.services import account

    locked = SimpleNamespace()
    update = MagicMock(return_value=locked)
    monkeypatch.setattr(account, "lock_active_customer", lambda customer_ref: locked)
    monkeypatch.setattr(account.transaction, "atomic", nullcontext)
    monkeypatch.setattr(customer_service, "update", update)
    intent = SimpleNamespace(first_name="Ana", last_name=UNSET, email=UNSET, birthday=UNSET)

    assert account.update_profile("CUS-1", intent) is locked
    update.assert_called_once_with("CUS-1", first_name="Ana")


def test_invalid_integer_rules_names_only_non_convertible_fields():
    from shopman.shop.services import audience

    assert audience.invalid_integer_rules(
        {"bought_within_days": "sete", "vip_first_minutes": "15", "preferred_hour_window_hours": None}
    ) == ["bought_within_days"]


def test_trusted_device_login_refuses_an_unknown_phone(monkeypatch):
    from shopman.doorman import conf as doorman_conf
    from shopman.doorman.protocols.identity import IdentityHandle

    from shopman.shop.services import auth

    class _NoOwner:
        def login_handle(self, raw):
            return IdentityHandle(kind="phone", value=raw, verified=False, primary=False)

        def resolve_identity(self, kind, value, *, purpose="login"):
            return None

    monkeypatch.setattr(doorman_conf, "get_adapter", lambda: _NoOwner())

    assert auth.trusted_device_login(SimpleNamespace(), phone="+5543999999999") is None


def test_redirect_safety_rejects_external_and_protocol_relative_urls():
    from django.test import override_settings

    from shopman.shop.services import auth

    request = SimpleNamespace(get_host=lambda: "shop.example")
    with override_settings(DOORMAN={"LOGIN_REDIRECT_URL": "/login", "ALLOWED_REDIRECT_HOSTS": set()}):
        assert auth.safe_redirect_url("https://evil.example/path", request) == "/login"
        assert auth.safe_redirect_url("//evil.example/path", request) == "/login"
        assert auth.safe_redirect_url("/account", request) == "/account"


def test_session_hold_release_delegates_the_exact_reference(monkeypatch):
    from shopman.shop.services import availability

    release = MagicMock(return_value=3)
    monkeypatch.setattr(
        availability,
        "get_adapter",
        lambda name: SimpleNamespace(release_holds_for_reference=release) if name == "stock" else None,
    )

    assert availability.release_session_holds("session-1") == 3
    release.assert_called_once_with("session-1")


def test_store_review_is_deferred_only_for_a_new_order_while_closed():
    from shopman.shop.services import business_calendar

    closed = business_calendar.BusinessCalendarState(
        is_open=False,
        opens_at="08:00",
        closes_at="18:00",
        message="Fechado",
    )

    assert business_calendar.store_review_deferred_state(SimpleNamespace(status="new"), state=closed) is closed
    assert business_calendar.store_review_deferred_state(SimpleNamespace(status="confirmed"), state=closed) is None


def _monday_shop():
    return SimpleNamespace(
        opening_hours={"monday": {"open": "08:00", "close": "18:00"}},
        defaults={},
    )


def test_operating_day_uses_the_declared_weekly_window():
    from shopman.shop.services import business_calendar

    assert business_calendar.is_open_on(date(2026, 10, 19), shop=_monday_shop()) is True
    assert business_calendar.is_open_on(date(2026, 10, 20), shop=_monday_shop()) is False


def test_selling_window_returns_the_declared_hours():
    from shopman.shop.services import business_calendar

    assert business_calendar.selling_hours_for(date(2026, 10, 19), shop=_monday_shop()) == (
        time(8),
        time(18),
    )


def test_closed_weekdays_reports_every_missing_regular_window():
    from shopman.shop.services import business_calendar

    assert business_calendar.closed_weekdays(shop=_monday_shop()) == [1, 2, 3, 4, 5, 6]


def test_schedule_governance_requires_one_valid_regular_window():
    from shopman.shop.services import business_calendar

    invalid = SimpleNamespace(opening_hours={"monday": {"open": "", "close": "18:00"}})

    assert business_calendar.has_regular_hours(shop=invalid) is False
    assert business_calendar.has_regular_hours(shop=_monday_shop()) is True


def test_weekly_windows_returns_only_valid_declared_windows():
    from shopman.shop.services import business_calendar

    shop = SimpleNamespace(
        opening_hours={
            "monday": {"open": "08:00", "close": "18:00"},
            "tuesday": {"open": "18:00", "close": "08:00"},
        }
    )

    assert business_calendar.weekly_windows(shop=shop) == {"monday": (time(8), time(18))}


def test_calendar_closure_uses_the_canonical_closed_date_decision():
    from shopman.shop.services import business_calendar

    shop = SimpleNamespace(defaults={"closed_dates": [{"date": "2026-12-25", "label": "Natal"}]})

    assert business_calendar.calendar_closure_on(date(2026, 12, 25), shop=shop) == (True, "Natal")
    assert business_calendar.closed_date_for(date(2026, 12, 25), [{"date": "2026-12-25", "label": "Natal"}]) == (
        True,
        "Natal",
        "date",
    )


def test_special_hours_accepts_only_an_explicit_valid_open_window():
    from shopman.shop.services import business_calendar

    exceptions = [
        {
            "date": "2026-12-24",
            "closed": False,
            "open": "09:00",
            "close": "13:00",
        }
    ]

    assert business_calendar.special_hours_for(date(2026, 12, 24), exceptions) == (
        time(9),
        time(13),
    )
    assert business_calendar.special_hours_for(date(2026, 12, 25), exceptions) is None


def test_shop_timezone_resolves_the_shop_declared_zone():
    from shopman.shop.services import business_calendar

    resolved = business_calendar.shop_timezone(shop=SimpleNamespace(timezone="America/Sao_Paulo"))

    assert str(resolved) == "America/Sao_Paulo"


def test_campaign_content_resolves_template_facts_without_ai(monkeypatch):
    from shopman.shop.services import campaign, marketing_facts

    variables = {"hashtags_list": ["#pao"], "link": "/produto/PAO-1", "name": "Pão"}
    facts = SimpleNamespace(
        variable_values=lambda: {"availability_phrase": "2 disponíveis"},
        as_payload=lambda: {"availability_phrase": "2 disponíveis"},
    )
    monkeypatch.setattr(campaign, "resolve_variables", lambda _context, promotion_ref="": dict(variables))
    monkeypatch.setattr(marketing_facts, "referenced_variables", lambda *_args: {"name"})
    monkeypatch.setattr(marketing_facts, "resolve_facts", lambda **_kwargs: facts)
    monkeypatch.setattr(campaign, "render", lambda body, values, field="": body.replace("{{name}}", values["name"]))
    monkeypatch.setattr(campaign, "_image_url", lambda _template, _context: "/media/pao.jpg")
    template = SimpleNamespace(body="Olá, {{name}}", platform_variants={})

    content = campaign.resolve_content(template, {"sku": "PAO-1"})

    assert content["body"] == "Olá, Pão"
    assert content["facts"] == {"availability_phrase": "2 disponíveis"}


def test_campaign_evaluation_keeps_only_matching_rules(monkeypatch):
    from shopman.shop.models import Campaign
    from shopman.shop.services import campaign

    matching = SimpleNamespace(pk=1)
    ignored = SimpleNamespace(pk=2)
    queryset = MagicMock()
    queryset.select_related.return_value = [matching, ignored]
    manager = SimpleNamespace(filter=lambda **_kwargs: queryset)
    monkeypatch.setattr(Campaign, "objects", manager)
    monkeypatch.setattr(campaign, "matches_filter", lambda rule, _context: rule is matching)
    monkeypatch.setattr(campaign, "_create_announcement", lambda rule, context: (rule.pk, context["sku"]))

    assert campaign.evaluate("production_finished", {"sku": "PAO-1"}) == [(1, "PAO-1")]


def test_marketing_test_target_options_never_projects_the_recipient():
    from django.test import override_settings

    from shopman.shop.services import campaign

    targets = {
        "owner": {
            "label": "Celular do proprietário",
            "recipient": "+5543999999999",
            "backend": "manychat",
            "sandbox": True,
            "ownership_verified": True,
        }
    }
    with override_settings(SHOPMAN_MARKETING_TEST_TARGETS=targets):
        assert campaign.marketing_test_target_options() == [
            {"ref": "owner", "label": "Celular do proprietário", "backend": "manychat"}
        ]


@pytest.mark.django_db
def test_canonical_cancellation_refuses_a_terminal_transition(monkeypatch):
    from shopman.orderman.models import Order

    from shopman.shop.services import cancellation

    query = MagicMock()
    query.select_for_update.return_value = query
    query.get.return_value = object()
    monkeypatch.setattr(Order, "objects", query)
    order = SimpleNamespace(
        pk=1,
        ref="ORD-1",
        status="returned",
        data={},
        refresh_from_db=MagicMock(),
        can_transition_to=lambda _status: False,
    )

    assert cancellation.cancel(order, "Pedido devolvido", actor="operator") is False
    order.refresh_from_db.assert_called_once_with()


def test_operator_cancellation_policy_requires_approval_for_captured_money(monkeypatch):
    from shopman.shop.services import cancellation, payment_status

    monkeypatch.setattr(payment_status, "has_sufficient_captured_payment", lambda _order: True)
    monkeypatch.setattr(payment_status, "get_payment_status", lambda _order: "captured")
    order = SimpleNamespace(
        ref="ORD-1",
        status="ready",
        can_transition_to=lambda _status: True,
    )

    policy = cancellation.operator_cancel_policy(order)

    assert policy.allowed is True
    assert policy.requires_approval is True


@pytest.mark.django_db
def test_cart_add_item_rejects_an_invalid_option_before_reserving(monkeypatch):
    from shopman.shop import product_options
    from shopman.shop.services import cart

    def reject(_product, _options):
        raise product_options.OptionSelectionError("option_unknown", "Escolha inválida.")

    monkeypatch.setattr(product_options, "resolve_selection", reject)
    product = SimpleNamespace(sku="PAO-1")

    with pytest.raises(product_options.OptionSelectionError, match="Escolha inválida"):
        cart.add_item(
            session_key="session-1",
            channel_ref="web",
            origin_channel="storefront",
            sku="PAO-1",
            qty=1,
            unit_price_q=1200,
            options=[{"group": "size", "ref": "unknown"}],
            product=product,
        )


def test_cart_session_lock_returns_the_exact_locked_session(monkeypatch):
    from shopman.orderman.models import Session

    from shopman.shop.services import cart

    expected = SimpleNamespace(session_key="session-1")
    query = MagicMock()
    query.select_for_update.return_value = query
    query.filter.return_value = query
    query.first.return_value = expected
    monkeypatch.setattr(Session, "objects", query)

    assert cart.lock_cart_session(session_key="session-1", channel_ref="web") is expected
    query.filter.assert_called_once_with(session_key="session-1", channel_ref="web")


@pytest.mark.django_db
def test_checkout_draft_clears_delivery_data_for_pickup(monkeypatch):
    from shopman.orderman.models import Session

    from shopman.shop.services import cart

    session = SimpleNamespace(
        data={
            "fulfillment_type": "delivery",
            "delivery_address": "Rua A",
            "delivery_address_structured": {"city": "Londrina"},
            "delivery_fee_q": 500,
        },
        save=MagicMock(),
    )
    query = MagicMock()
    query.select_for_update.return_value = query
    query.filter.return_value = query
    query.first.return_value = session
    modified = SimpleNamespace(data={"fulfillment_type": "pickup"})
    monkeypatch.setattr(Session, "objects", query)
    monkeypatch.setattr(cart.session_service, "modify_session", MagicMock(return_value=modified))

    assert cart.set_delivery_draft(session_key="session-1", channel_ref="web", fulfillment_type="pickup") is modified
    assert session.data == {"fulfillment_type": "pickup"}


def test_channel_activation_uses_the_effective_toggle(monkeypatch):
    from shopman.shop import request_memo
    from shopman.shop.services import channel_switch

    channel = SimpleNamespace(is_active=False, config={})
    monkeypatch.setattr(request_memo, "channel_by_ref", lambda ref: channel if ref == "web" else None)

    assert channel_switch.is_channel_active("web") is False


def test_checkout_command_replays_a_completed_commit(monkeypatch):
    from shopman.shop.services import checkout

    completed = SimpleNamespace(order_ref="ORD-1", status="new", total_q=4200, items_count=2)
    monkeypatch.setattr(checkout.CommitService, "completed_response", lambda *_args: completed)
    monkeypatch.setattr(checkout, "recover_post_commit_side_effects", lambda _ref: ["receipt"])

    result = checkout.process(
        "session-1",
        "web",
        {},
        idempotency_key="idem-1",
        expected_total_q=4200,
        expected_revision=3,
    )

    assert result.order_ref == "ORD-1"
    assert result.convenience_pending == ("receipt",)


def test_checkout_customer_reuses_the_existing_phone_owner(monkeypatch):
    from shopman.guestman.services import customer as customer_service

    from shopman.shop.services import checkout

    customer = SimpleNamespace(first_name="", save=MagicMock())
    monkeypatch.setattr(customer_service, "get_by_phone", lambda _phone: customer)
    intent = SimpleNamespace(customer_phone="+5543999999999", customer_name="Ana")

    assert checkout.ensure_customer(intent, order_ref="ORD-1") is None
    assert customer.first_name == "Ana"
    customer.save.assert_called_once_with(update_fields=["first_name"])


def test_customer_lookup_delegates_to_guestman(monkeypatch):
    from shopman.guestman.services import customer

    from shopman.shop.services import auth

    expected = object()
    monkeypatch.setattr(customer, "get", lambda ref: expected if ref == "CUS-1" else None)
    assert auth.customer_by_ref("CUS-1") is expected


def test_confirmed_customer_name_uses_the_resolved_subject(monkeypatch):
    from shopman.shop.services import auth

    monkeypatch.setattr(auth, "customer_by_uuid", lambda subject: SimpleNamespace(first_name="Ana"))
    result = SimpleNamespace(customer=SimpleNamespace(subject_id="customer-1"))
    assert auth.confirmed_customer_name(result) == "Ana"


def test_device_trust_refuses_a_missing_customer():
    from shopman.shop.services import auth

    assert auth.device_is_trusted(object(), customer_uuid=None) is False


def test_contact_verification_rejects_a_non_phone_handle(monkeypatch):
    from shopman.doorman import conf

    from shopman.shop.services import auth

    adapter = SimpleNamespace(login_handle=lambda _phone: SimpleNamespace(kind="email", value="a@b.test"))
    monkeypatch.setattr(conf, "get_adapter", lambda: adapter)
    result = auth.verify_contact_code(phone="invalid", code_input="123456", customer_uuid="CUS-1")
    assert result.success is False
    assert result.error_code == "invalid_target"


def test_passkey_capability_comes_from_doorman(monkeypatch):
    from shopman.doorman.services import passkey

    from shopman.shop.services import auth

    monkeypatch.setattr(passkey, "is_enabled", lambda: True)
    assert auth.passkey_enabled() is True


def test_cancellation_authority_revision_seals_policy_and_payment(monkeypatch):
    from shopman.shop.services import cancellation, payment, remote_mutations

    monkeypatch.setattr(
        cancellation,
        "operator_cancel_policy",
        lambda _order: SimpleNamespace(allowed=True, requires_approval=True),
    )
    monkeypatch.setattr(cancellation, "is_advanced_cancel", lambda _order: True)
    monkeypatch.setattr(payment, "get_payment_status", lambda _order: "captured")
    monkeypatch.setattr(payment, "captured_balance_q", lambda _order: 1200)
    monkeypatch.setattr(remote_mutations, "mutation_fingerprint", lambda payload: payload)
    order = SimpleNamespace(status="preparing", total_q=1200, data={"payment": {"intent_ref": "PI-1"}})
    revision = cancellation.authority_revision(order)
    assert revision["requires_approval"] is True
    assert revision["intent_ref"] == "PI-1"


def test_cancellation_request_copy_distinguishes_the_preparation_boundary():
    from shopman.shop.services import cancellation_requests

    message = cancellation_requests.operational_message(order_ref="ORD-1", protocol="SC-1", before_preparation=True)
    assert "valor volta inteiro" in message
    assert "SC-1" in message


def test_cart_finalization_abandons_the_exact_session(monkeypatch):
    from shopman.shop.services import cart

    abandon = MagicMock()
    monkeypatch.setattr(cart.session_service, "abandon_session", abandon)
    cart.clear_session(session_key="session-1", channel_ref="web")
    abandon.assert_called_once_with(session_key="session-1", channel_ref="web")


def test_checkout_recovery_refuses_an_empty_session_key():
    from shopman.shop.services import checkout

    assert checkout.recover_committed_checkout(session_key="", channel_ref="web", idempotency_key="idem-1") is None


def test_empty_customer_group_has_no_derived_promotion():
    from shopman.shop.services import customer_groups

    assert customer_groups.group_promotion("") is None


def test_trusted_device_cookie_name_is_owned_by_doorman():
    from shopman.shop.services import devices

    assert devices.cookie_name()


def test_canonical_fulfillment_slots_are_never_empty(monkeypatch):
    from shopman.shop.models import Shop
    from shopman.shop.services import fulfillment_window

    monkeypatch.setattr(Shop, "load", lambda: SimpleNamespace(defaults={}))
    assert fulfillment_window.canonical_slots() == fulfillment_window.DEFAULT_CANONICAL_SLOTS


def test_invalid_campaign_schedule_has_no_autonomous_occurrence():
    from shopman.shop.services import campaign_schedule

    assert campaign_schedule.next_occurrence(None) is None


def test_calendar_without_closures_produces_no_ifood_interruptions(monkeypatch):
    from shopman.shop.services import business_calendar, ifood_merchant

    monkeypatch.setattr(business_calendar, "calendar_closure_on", lambda day, shop=None: (False, ""))
    monkeypatch.setattr(business_calendar, "selling_hours_for", lambda day, shop=None: None)
    assert ifood_merchant.desired_calendar_closures() == []


def test_ifood_merchant_detail_normalizes_a_mapping(monkeypatch):
    from shopman.shop.services import ifood_merchant

    response = object()
    monkeypatch.setattr(ifood_merchant, "_call", lambda *args, **kwargs: response)
    monkeypatch.setattr(ifood_merchant, "_json", lambda value: {"id": "merchant-1"})
    monkeypatch.setattr(ifood_merchant, "_merchant_path", lambda: "/merchants/merchant-1")
    assert ifood_merchant.get_merchant() == {"id": "merchant-1"}


def test_empty_weekly_grid_produces_no_ifood_shifts(monkeypatch):
    from shopman.shop.services import business_calendar, ifood_merchant

    monkeypatch.setattr(business_calendar, "weekly_windows", lambda shop=None: {})
    assert ifood_merchant.desired_shifts() == []


def test_fire_command_rejects_an_invalid_campaign_before_io():
    from shopman.shop.services import marketing_fire
    from shopman.shop.services.marketing_commands import MarketingCommandRejected

    with pytest.raises(MarketingCommandRejected, match="Referência de campanha inválida"):
        marketing_fire.fire_campaign_command(
            0,
            actor=SimpleNamespace(pk=1),
            idempotency_key="idem-1",
            base_version=1,
            audience_rules={},
            authorize=lambda *_args: None,
        )


def test_food_preferences_delegate_to_guestman(monkeypatch):
    from shopman import guestman
    from shopman.shop.services import account

    monkeypatch.setattr(
        guestman.PreferenceService,
        "get_preferences",
        lambda customer_ref, category: [(customer_ref, category)],
    )
    assert account.preferences("CUS-1", "food") == [("CUS-1", "food")]


def test_access_listing_can_be_empty(monkeypatch):
    from shopman.shop.models import UserNotification
    from shopman.shop.services import customer_sign_in

    queryset = MagicMock()
    queryset.order_by.return_value.__getitem__.return_value = []
    monkeypatch.setattr(UserNotification, "objects", SimpleNamespace(filter=lambda **_kwargs: queryset))
    monkeypatch.setattr(customer_sign_in, "_active_sessions", lambda _user: {})
    assert customer_sign_in.list_accesses(user=SimpleNamespace(pk=1)) == []


def test_machine_cancellation_reason_resolves_to_a_canonical_key():
    from shopman.shop.services import cancel_reasons

    assert cancel_reasons.reason_key_of({"cancellation_reason": "payment_timeout"})


def test_cancellation_reason_customer_copy_uses_the_canonical_catalog():
    from shopman.shop.services import cancel_reasons

    reason = cancel_reasons.cancel_reason("payment_timeout")
    assert cancel_reasons.customer_text(reason)


def test_advanced_cancellation_is_a_status_classification():
    from shopman.shop.services import cancellation

    status = next(iter(cancellation.ADVANCED_CANCEL_STATUSES))
    assert cancellation.is_advanced_cancel(SimpleNamespace(status=status)) is True


def test_missing_source_has_no_promised_fulfillment_time():
    from shopman.shop.services import fulfillment_window

    assert fulfillment_window.promised_at(None) is None


def test_unknown_product_readiness_does_not_invent_a_time(monkeypatch):
    from shopman.shop.services import fulfillment_window, product_readiness

    monkeypatch.setattr(product_readiness, "bottleneck", lambda _skus: (None, ""))
    assert fulfillment_window.readiness_for(["SKU-1"]) == (None, "", "")


def test_missing_ifood_channel_has_no_switch_closures(monkeypatch):
    from shopman.shop.services import ifood_merchant

    monkeypatch.setattr(ifood_merchant, "_ifood_channel", lambda: None)
    assert ifood_merchant.channel_off_closures() == []


def test_ifood_governance_requires_declared_regular_hours(monkeypatch):
    from shopman.shop.services import business_calendar, ifood_merchant

    monkeypatch.setattr(business_calendar, "has_regular_hours", lambda shop=None: False)
    assert ifood_merchant.governs() is False


def test_ifood_opening_hours_compare_normalized_shifts():
    from shopman.shop.services import ifood_merchant

    assert ifood_merchant.shifts_match(
        [{"dayOfWeek": "MONDAY", "start": "08:00", "duration": 60}],
        [{"dayOfWeek": "monday", "start": "08:00:00", "duration": "60"}],
    )


def test_unknown_marketing_format_has_no_capability():
    from shopman.shop.services import marketing_capabilities

    assert marketing_capabilities.format_capability("unknown", "image") is None


def test_customer_strategy_registration_owns_the_requested_key(monkeypatch):
    from shopman.shop.services import customer

    def strategy(order):
        return order

    monkeypatch.delitem(customer._STRATEGIES, "focused-test", raising=False)
    customer.register_strategy("focused-test", strategy)
    assert customer._STRATEGIES["focused-test"] is strategy


def test_offer_change_without_projection_channels_enqueues_nothing(monkeypatch):
    from shopman.shop.services import external_availability

    monkeypatch.setattr(external_availability, "projection_refs_stocked_by", lambda _ref: [])
    assert external_availability.on_offer_changed("SKU-1", channel_ref="web") is None


def test_fiscal_publication_gate_reads_the_deployment_switch(monkeypatch):
    from shopman.shop.services import fiscal_catalog

    monkeypatch.setattr(
        fiscal_catalog.settings,
        fiscal_catalog.SETTING_REQUIRE_ON_PUBLISH,
        True,
        raising=False,
    )
    assert fiscal_catalog.publication_gate_enabled() is True


def test_fomo_context_composes_each_domain_fact(monkeypatch):
    from shopman.shop.services import fomo

    monkeypatch.setattr(fomo, "_channel_config", lambda _ref: {"stock": {}})
    monkeypatch.setattr(fomo, "_availability", lambda *_args, **_kwargs: {"available_qty": 2})
    monkeypatch.setattr(fomo, "last_finished_bake", lambda _sku: None)
    monkeypatch.setattr(fomo, "_promotions_for_sku", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(fomo, "social_proof", lambda _sku: {"demand_count": 0, "sold_today": 0})
    monkeypatch.setattr(fomo, "_stock_config", lambda config: config["stock"])
    assert fomo.context_for_sku("SKU-1", channel_ref="web")["availability"] == {"available_qty": 2}


def test_fulfillment_creation_is_idempotent_from_the_order_marker():
    from shopman.shop.services import fulfillment

    order = SimpleNamespace(data={"fulfillment_created": True})
    assert fulfillment.create(order) is None


def test_house_account_requires_an_identified_customer():
    from shopman.shop.services import house_account

    with pytest.raises(house_account.HouseAccountError, match="cliente identificado"):
        house_account.require_eligible("")


def test_ifood_cancellation_code_honors_the_explicit_fallback(monkeypatch):
    from shopman.shop.services import ifood_callbacks

    monkeypatch.setattr(ifood_callbacks, "_cfg", lambda: {})
    assert ifood_callbacks.resolve_cancellation_code("unknown", "fallback") == "fallback"


def test_only_real_ifood_orders_require_a_remote_cancellation_decision():
    from shopman.shop.services import ifood_cancellation

    local = SimpleNamespace(channel_ref="web", data={}, external_ref="ORD-1")
    assert ifood_cancellation.requires_remote_decision(local) is False


def test_ifood_event_tick_polls_then_processes(monkeypatch):
    from shopman.shop.services import ifood_events

    events = [{"id": "evt-1"}]
    monkeypatch.setattr(ifood_events, "poll", lambda: events)
    monkeypatch.setattr(ifood_events, "process_events", lambda value: {"received": len(value)})
    assert ifood_events.run_once() == {"received": 1}


def test_ifood_handshake_alert_ignores_an_unknown_order(monkeypatch):
    from shopman.shop.services import ifood_handshake

    query = MagicMock()
    query.first.return_value = None
    monkeypatch.setattr(ifood_handshake.Order, "objects", SimpleNamespace(filter=lambda **_kwargs: query))
    assert ifood_handshake.sync_alert("missing") is None


def test_ifood_order_fetch_returns_the_provider_json(monkeypatch):
    from shopman.shop.services import ifood_orders

    response = SimpleNamespace(status_code=200, json=lambda: {"id": "IFOOD-1"})
    monkeypatch.setattr(ifood_orders.ifood_http, "request", lambda *_args, **_kwargs: response)
    assert ifood_orders.fetch_order("IFOOD-1") == {"id": "IFOOD-1"}


def test_kds_alert_source_reference_is_stable():
    from shopman.shop.services import kds_alerts

    assert kds_alerts.source_ref(42) == "kds_ticket:42"


def test_non_order_sources_can_always_be_recalled():
    from shopman.shop.services import kds

    assert kds.recall_block_reason(SimpleNamespace()) == ""


def test_kds_due_guard_checks_the_ticket_source(monkeypatch):
    from shopman.shop.services import kds

    source = object()
    guard = MagicMock()
    monkeypatch.setattr(kds, "_ticket_source", lambda _ticket: source)
    monkeypatch.setattr(kds, "_ensure_source_due", guard)
    kds.ensure_ticket_due(object())
    guard.assert_called_once_with(source)


def test_kds_start_delegates_under_the_source_lock(monkeypatch):
    from contextlib import nullcontext

    from django.db import transaction

    from shopman.shop.services import kds

    ticket, source = object(), object()
    monkeypatch.setattr(transaction, "atomic", nullcontext)
    monkeypatch.setattr(kds, "_lock_source_then_ticket", lambda value: (source, value))
    monkeypatch.setattr(kds, "_start_ticket_locked", lambda value, **_kwargs: value is ticket)
    assert kds.start_ticket(ticket, actor="cook") is True


def test_kds_reconciliation_skips_marketplace_test_orders(monkeypatch):
    from shopman.shop.services import kds

    order = SimpleNamespace(ref="IFOOD-TEST", session_key="session-1")
    monkeypatch.setattr(kds, "is_test_order", lambda _order: True)
    assert kds.reconcile_to_lines(order, previous_lines=[]) == {
        "unfired": 0,
        "refired": 0,
        "skipped": "test_order",
    }


def test_unknown_lot_keeps_the_declared_discount():
    from shopman.shop.services import lot_pricing

    assert lot_pricing.percent_for_lot("", declared_percent=17) == 17


def test_loyalty_redemption_ignores_marketplace_test_orders(monkeypatch):
    from shopman.shop.services import loyalty

    order = SimpleNamespace(ref="TEST-1", data={"loyalty": {"applied_discount_q": 100}})
    monkeypatch.setattr(loyalty, "is_test_order", lambda _order: True)
    assert loyalty.redeem(order) is None


def test_marketing_adult_declaration_requires_a_known_terms_version():
    from shopman.shop.services import marketing_age

    metadata = {marketing_age.ADULT_DECLARATION_KEY: {"terms_version": "login-terms-pt-BR-v1"}}
    assert marketing_age.declares_adult(metadata) is True


def test_marketing_platform_catalog_exposes_only_declared_destinations():
    from shopman.shop.services import marketing_capabilities

    assert marketing_capabilities.platform_refs() == tuple(
        item.platform for item in marketing_capabilities.DESTINATIONS
    )


def test_marketing_command_rejects_an_anonymous_actor_before_storage():
    from shopman.shop.services import marketing_commands

    with pytest.raises(marketing_commands.MarketingCommandRejected, match="pessoa autenticada"):
        marketing_commands.execute_announcement_command(
            kind="approve",
            announcement_id=1,
            actor=SimpleNamespace(pk=None),
            idempotency_key="valid-idempotency-key",
            base_version=1,
            payload={},
            operation=lambda *_args: {},
        )


def test_marketing_retry_rejects_a_scalar_platform_selection():
    from shopman.shop.services import marketing_delivery_recovery
    from shopman.shop.services.marketing_contracts import MarketingContractError

    with pytest.raises(MarketingContractError, match="lista"):
        marketing_delivery_recovery.retry_failed_command(
            1,
            actor=SimpleNamespace(pk=1),
            idempotency_key="valid-idempotency-key",
            base_version=1,
            platforms="whatsapp",
        )


def test_marketing_external_effect_guard_allows_an_unfrozen_store(monkeypatch):
    from shopman.shop.services import marketing_security

    query = MagicMock()
    query.exists.return_value = False
    monkeypatch.setattr(
        marketing_security.MarketingSafetyState,
        "objects",
        SimpleNamespace(filter=lambda **_kwargs: query),
    )
    assert marketing_security.require_external_effects_enabled() is None


def test_marketing_rejection_requires_an_operator_reason():
    from shopman.shop.services import marketing_transitions
    from shopman.shop.services.marketing_contracts import MarketingContractError

    with pytest.raises(MarketingContractError) as caught:
        marketing_transitions.reject_command(
            1,
            actor=SimpleNamespace(pk=1),
            idempotency_key="valid-idempotency-key",
            base_version=1,
            reason="",
        )

    assert caught.value.code == "reason_required"
    assert caught.value.field_errors == {"reason": ("Informe o motivo da recusa.",)}


def test_marketing_customer_link_accepts_a_canonical_relative_product_path():
    from shopman.shop.services import marketing_url_policy

    assert marketing_url_policy.validate_customer_link("/produto/PAO-1") == "/produto/PAO-1"


def test_counter_takeover_is_a_noop_without_a_pending_digital_charge():
    from shopman.shop.services import counter_takeover

    order = SimpleNamespace(channel_ref="web", data={"payment": {}})
    result = counter_takeover.take_over_pending_digital_charge(order, actor="operator")
    assert result.taken_over is False


def test_empty_customer_group_advantage_sync_preserves_existing_rows():
    from shopman.shop.services import customer_groups

    tier = SimpleNamespace(advantages=SimpleNamespace(all=lambda: []))
    assert customer_groups.sync_group_advantages(tier, []) is None


def test_fiscal_publication_refusal_names_the_product_and_listing():
    from django.core.exceptions import ValidationError

    from shopman.shop.services import fiscal_catalog

    product = SimpleNamespace(sku="SKU-1", name="Pão")
    with pytest.raises(ValidationError, match="SKU-1"):
        fiscal_catalog.refuse_publication(product, "web", ["NCM ausente."])


def test_house_account_settlement_requires_a_customer():
    from shopman.shop.services import house_account

    with pytest.raises(house_account.HouseAccountError, match="cliente"):
        house_account.settle_account("", 100, "pix", actor="operator")


def test_kds_follow_ignores_an_unsaved_user():
    from shopman.shop.services import kds_alerts

    instance = SimpleNamespace(config={})
    assert kds_alerts.follow(instance, SimpleNamespace(pk=None)) is None


def test_delivery_fiscal_identity_authorities_share_the_delivery_gate(monkeypatch):
    from shopman.shop.rules import validation
    from shopman.shop.services import delivery_fiscal_identity, fiscal

    monkeypatch.setattr(fiscal, "emission_expected", lambda _order: False)
    gaps = delivery_fiscal_identity.recipient_gaps(tax_id="", address={})
    order = SimpleNamespace(data={"fulfillment_type": "delivery"})
    assert gaps
    assert delivery_fiscal_identity.requires_delivery_fiscal_identity(order) is False
    assert (
        validation.DeliveryFiscalIdentityRule().validate(
            channel=SimpleNamespace(ref="web"),
            session=SimpleNamespace(data={"fulfillment_type": "pickup"}, items=[]),
            ctx={},
        )
        is None
    )
