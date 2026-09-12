"""A nota pode usar dados de terceiro sem tomar posse do cadastro."""
from __future__ import annotations

import pytest
from shopman.guestman.models import Customer

from shopman.shop.services.pos import _persist_customer_from_payload, build_session_ops
from shopman.shop.services.pos_intent import PosIntentError, parse_pos_sale_intent
from shopman.shop.services.pos_receipt_identity import ReceiptIdentityConflict, require_receipt_identity_choice

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return Customer.objects.create(ref="owner", first_name="Ana", document="52998224725", email="ana@example.org")


def choice(field, value, *, customer_ref="", owner_ref="owner", request_id="sale-1"):
    return {"field": field, "value": value, "customer_ref": customer_ref, "owner_ref": owner_ref,
            "choice": "receipt_only", "client_request_id": request_id}


@pytest.mark.parametrize("field,value,api_field", [("tax_id", "529.982.247-25", "fiscal_tax_id"), ("email", "ANA@EXAMPLE.ORG ", "receipt_email")])
def test_known_document_prompts_without_save_opt_in(owner, field, value, api_field):
    with pytest.raises(ReceiptIdentityConflict) as error:
        _persist_customer_from_payload({api_field: value, "client_request_id": "sale-1", "receipt_channels": ["email"]}, operator_username="op")
    data = error.value.as_dict()
    assert data["code"] == "receipt_identity_conflict"
    assert data["field"] == api_field
    assert data["customer_ref"] == ""
    assert data["candidates"][0]["ref"] == owner.ref
    assert data["client_request_id"] == "sale-1"
    assert Customer.objects.count() == 1


def test_receipt_only_retries_do_not_associate_or_write(owner):
    payload = {"receipt_channels": ["email"], "fiscal_tax_id": "52998224725", "receipt_email": "ana@example.org", "client_request_id": "sale-1",
               "receipt_identity_choices": [choice("tax_id", "52998224725"), choice("email", "ana@example.org")]}
    original = dict(Customer.objects.values().get(pk=owner.pk))
    for _ in range(3):
        assert _persist_customer_from_payload(payload, operator_username="op") == {}
    ops = build_session_ops({**payload, "items": []}, "op")
    assert not any(op.get("path") in ("customer.ref", "customer_ref") for op in ops)
    assert any(op.get("path") == "fiscal.tax_id" and op["value"] == "52998224725" for op in ops)
    assert dict(Customer.objects.values().get(pk=owner.pk)) == original


@pytest.mark.parametrize("changed", [
    {"customer_ref": "someone-else"}, {"client_request_id": "sale-2"},
    {"save_receipt_tax_id": True},
])
def test_ack_cannot_authorize_another_sale_or_customer_or_crm_write(owner, changed):
    with pytest.raises(ReceiptIdentityConflict):
        require_receipt_identity_choice({"fiscal_tax_id": owner.document, "client_request_id": "sale-1",
            "receipt_identity_choices": [choice("tax_id", owner.document)], **changed})


def test_changed_value_or_owner_invalidates_choice(owner):
    other = Customer.objects.create(ref="other", first_name="Bia", document="11144477735")
    with pytest.raises(ReceiptIdentityConflict):
        require_receipt_identity_choice({"fiscal_tax_id": other.document, "client_request_id": "sale-1",
            "receipt_identity_choices": [choice("tax_id", owner.document)]})
    stale = choice("tax_id", owner.document, owner_ref="old-owner")
    with pytest.raises(ReceiptIdentityConflict):
        require_receipt_identity_choice({"fiscal_tax_id": owner.document, "client_request_id": "sale-1", "receipt_identity_choices": [stale]})


def test_associated_owner_needs_no_additional_ack(owner):
    require_receipt_identity_choice({"customer_ref": owner.ref, "fiscal_tax_id": owner.document,
                                    "receipt_email": owner.email, "save_receipt_tax_id": True})


def test_inactive_owner_still_can_be_used_on_document(owner):
    owner.is_active = False
    owner.save(update_fields=["is_active"])
    payload = {"fiscal_tax_id": owner.document, "client_request_id": "sale-1"}
    with pytest.raises(ReceiptIdentityConflict) as error:
        require_receipt_identity_choice(payload)
    assert error.value.candidates[0]["owner_inactive"]
    assert _persist_customer_from_payload({**payload, "receipt_identity_choices": [choice("tax_id", owner.document)]}, operator_username="op") == {}


def test_choices_parser_normalizes_and_rejects_unsupported_actions():
    raw = {"items": [], "receipt_identity_choices": [choice("email", " ANA@EXAMPLE.ORG ")]}
    assert parse_pos_sale_intent(raw, for_commit=False).payload["receipt_identity_choices"][0]["value"] == "ana@example.org"
    raw["receipt_identity_choices"][0]["choice"] = "associate"
    with pytest.raises(PosIntentError):
        parse_pos_sale_intent(raw, for_commit=False)


@pytest.fixture
def counter_runtime():
    from shopman.shop.tests.test_pos_scheduled_order import balcao

    return balcao.__wrapped__()


def test_review_and_close_require_same_decision_without_associating(owner, counter_runtime):
    from shopman.orderman.models import Order

    from shopman.shop.services.pos import review_sale
    from shopman.shop.tests.test_pos_scheduled_order import _close, _payload

    operator, shift = counter_runtime
    payload = _payload(shift, client_request_id="sale-1", customer_name="", fiscal_tax_id=owner.document)
    with pytest.raises(ReceiptIdentityConflict):
        review_sale(channel_ref="pdv", payload=payload, operator_username=operator.username)
    with pytest.raises(ReceiptIdentityConflict):
        _close(operator, payload)
    assert not Order.objects.exists()
    assert Customer.objects.count() == 1
    payload["receipt_identity_choices"] = [choice("tax_id", owner.document)]
    assert review_sale(channel_ref="pdv", payload=payload, operator_username=operator.username).total_q > 0
    order = Order.objects.get(ref=_close(operator, payload).order_ref)
    assert order.data["fiscal"]["tax_id"] == owner.document
    assert not order.data.get("customer_ref")
    assert not order.data.get("customer", {}).get("ref")
    assert "receipt_identity_choices" not in order.data
    assert Customer.objects.count() == 1


def test_disabled_email_is_ignored_without_prompt_or_crm_write(owner):
    other = Customer.objects.create(ref="associated", first_name="Bia", email="bia@example.org")
    payload = {"customer_ref": other.ref, "receipt_channels": [], "receipt_email": owner.email,
               "save_receipt_contact": True, "client_request_id": "hidden-email"}
    normalized = parse_pos_sale_intent({**payload, "items": []}, for_commit=False).payload
    assert normalized["receipt_email"] == ""
    assert normalized["save_receipt_contact"] is False
    resolved = _persist_customer_from_payload(payload, operator_username="op")
    assert resolved["ref"] == other.ref
    assert resolved["email"] == "bia@example.org"
    other.refresh_from_db()
    owner.refresh_from_db()
    assert other.email == "bia@example.org"
    assert owner.email == "ana@example.org"
    ops = build_session_ops({**payload, "items": []}, "op")
    assert not any(op.get("path") == "receipt.email" and op["value"] == owner.email for op in ops)


def test_document_only_does_not_teach_preferences_to_associated_customer(owner):
    current = Customer.objects.create(ref="current", first_name="Bia")
    original = dict(Customer.objects.values().get(pk=current.pk))
    payload = {"customer_ref": current.ref, "fiscal_tax_id": owner.document, "receipt_email": owner.email,
               "receipt_channels": ["email"], "client_request_id": "sale-1", "receipt_identity_choices": [
                   choice("tax_id", owner.document, customer_ref=current.ref),
                   choice("email", owner.email, customer_ref=current.ref),
               ]}
    assert _persist_customer_from_payload(payload, operator_username="op")["ref"] == current.ref
    saved = dict(Customer.objects.values().get(pk=current.pk))
    assert saved["metadata"].get("fiscal_prefs") == original["metadata"].get("fiscal_prefs")
    # A trilha de atendimento (pos.last_operator/last_capture_at) continua normal.
    for field in ("first_name", "last_name", "document", "email", "phone"):
        assert saved[field] == original[field]


@pytest.mark.parametrize("different_owners", [False, True])
def test_all_unresolved_document_fields_are_returned_together(owner, different_owners):
    email_owner = Customer.objects.create(ref="email-owner", first_name="Bruno", email="bruno@example.org") if different_owners else owner
    original = list(Customer.objects.order_by("pk").values())
    with pytest.raises(ReceiptIdentityConflict) as error:
        _persist_customer_from_payload({
            "fiscal_tax_id": "529.982.247-25", "receipt_email": f" {email_owner.email.upper()} ",
            "receipt_channels": ["email"], "client_request_id": "sale-1",
        }, operator_username="op")
    data = error.value.as_dict()
    assert [(item["field"], item["value"], item["candidates"][0]["ref"]) for item in data["conflicts"]] == [
        ("fiscal_tax_id", owner.document, owner.ref),
        ("receipt_email", email_owner.email, email_owner.ref),
    ]
    assert data["field"] == data["conflicts"][0]["field"]
    assert data["value"] == data["conflicts"][0]["value"]
    assert data["candidates"] == data["conflicts"][0]["candidates"]
    assert data["owner_ref"] == owner.ref
    assert data["customer_ref"] == ""
    assert data["client_request_id"] == "sale-1"
    assert list(Customer.objects.order_by("pk").values()) == original


def test_group_omits_acknowledged_field_but_keeps_other_decision_pending(owner):
    payload = {"fiscal_tax_id": owner.document, "receipt_email": owner.email,
               "receipt_channels": ["email"], "client_request_id": "sale-1",
               "receipt_identity_choices": [choice("tax_id", owner.document)]}
    with pytest.raises(ReceiptIdentityConflict) as error:
        require_receipt_identity_choice(payload)
    data = error.value.as_dict()
    assert data["field"] == "receipt_email"
    assert [item["field"] for item in data["conflicts"]] == ["receipt_email"]
    payload["receipt_identity_choices"].append(choice("email", owner.email))
    require_receipt_identity_choice(payload)
    # CRM opt-in invalidates only the matching acknowledgement, not the entire group.
    with pytest.raises(ReceiptIdentityConflict) as error:
        require_receipt_identity_choice({**payload, "save_receipt_tax_id": True})
    assert [item["field"] for item in error.value.conflicts] == ["fiscal_tax_id"]


def test_group_requires_new_ack_context_after_associating_one_of_two_owners(owner):
    other = Customer.objects.create(ref="other", first_name="Bruno", email="bruno@example.org")
    payload = {"customer_ref": owner.ref, "fiscal_tax_id": owner.document, "receipt_email": other.email,
               "receipt_channels": ["email"], "client_request_id": "sale-1",
               "receipt_identity_choices": [choice("email", other.email, owner_ref=other.ref)]}
    with pytest.raises(ReceiptIdentityConflict) as error:
        require_receipt_identity_choice(payload)
    assert [item["field"] for item in error.value.conflicts] == ["receipt_email"]
    payload["receipt_identity_choices"] = [choice("email", other.email, owner_ref=other.ref, customer_ref=owner.ref)]
    require_receipt_identity_choice(payload)


def test_group_excludes_hidden_email_even_when_both_values_have_owners(owner):
    with pytest.raises(ReceiptIdentityConflict) as error:
        require_receipt_identity_choice({"fiscal_tax_id": owner.document, "receipt_email": owner.email,
                                        "receipt_channels": [], "client_request_id": "sale-1"})
    assert [item["field"] for item in error.value.conflicts] == ["fiscal_tax_id"]


@pytest.mark.parametrize("save", [False, True])
def test_unknown_values_require_choice_or_explicit_save(save):
    payload = {"fiscal_tax_id": "11144477735", "receipt_email": "new@example.org", "receipt_channels": ["email"]}
    if save:
        require_receipt_identity_choice({**payload, "save_receipt_tax_id": True, "save_receipt_contact": True})
    else:
        with pytest.raises(ReceiptIdentityConflict) as error:
            require_receipt_identity_choice(payload)
        assert len(error.value.conflicts) == 2
        assert all(item["candidates"] == [] for item in error.value.conflicts)
        assert error.value.owner_ref == ""
    assert Customer.objects.count() == 0


def test_unknown_receipt_only_ack_never_creates_and_rechecks_new_owner():
    payload = {"fiscal_tax_id": "11144477735", "client_request_id": "sale-1",
               "receipt_identity_choices": [choice("tax_id", "11144477735", owner_ref="")]}
    assert _persist_customer_from_payload(payload, operator_username="op") == {}
    assert Customer.objects.count() == 0
    Customer.objects.create(ref="new-owner", document="11144477735")
    with pytest.raises(ReceiptIdentityConflict):
        _persist_customer_from_payload(payload, operator_username="op")


def receipt_action(**changes):
    return {"action": "create", "customer_ref": "", "target_ref": "", "client_request_id": "sale-1",
            "fields": [{"field": "tax_id", "value": "11144477735", "owner_ref": ""},
                       {"field": "email", "value": "new@example.org", "owner_ref": ""}], **changes}


def test_receipt_create_has_no_invented_name_and_retry_never_duplicates():
    from shopman.shop.services.pos import resolve_or_create_customer
    action = receipt_action()
    result = resolve_or_create_customer(receipt_identity_action=action, operator_username="op")
    saved = Customer.objects.get(ref=result["ref"])
    assert saved.first_name == saved.last_name == ""
    assert saved.document == "11144477735"
    assert saved.email == "new@example.org"
    with pytest.raises(ReceiptIdentityConflict):
        resolve_or_create_customer(receipt_identity_action=action, operator_username="op")
    assert Customer.objects.count() == 1


def test_receipt_save_mixed_known_new_requires_target_and_preserves_cpf_confirmation(owner):
    from shopman.shop.services.pos import PosTaxIdOverwriteError, resolve_or_create_customer
    action = receipt_action(action="save", target_ref=owner.ref, fields=[
        {"field": "email", "value": owner.email, "owner_ref": owner.ref},
        {"field": "tax_id", "value": "11144477735", "owner_ref": ""},
    ])
    with pytest.raises(PosTaxIdOverwriteError):
        resolve_or_create_customer(receipt_identity_action=action, operator_username="op")
    owner.refresh_from_db()
    assert owner.document == "52998224725"
    with pytest.raises(PosIntentError) as error:
        resolve_or_create_customer(receipt_identity_action={**action, "tax_id_overwrite_confirmed": True, "tax_id_before": "stale"}, operator_username="op")
    assert error.value.code == "receipt_identity_changed"
    result = resolve_or_create_customer(receipt_identity_action={**action, "tax_id_overwrite_confirmed": True, "tax_id_before": owner.document}, operator_username="op")
    assert result["ref"] == owner.ref
    owner.refresh_from_db()
    assert owner.document == "11144477735"
    assert Customer.objects.count() == 1


def test_receipt_create_rechecks_snapshot_before_any_write(owner):
    from shopman.shop.services.pos import resolve_or_create_customer
    original = list(Customer.objects.values())
    with pytest.raises(ReceiptIdentityConflict):
        resolve_or_create_customer(receipt_identity_action=receipt_action(fields=[
            {"field": "email", "value": owner.email, "owner_ref": ""},
            {"field": "tax_id", "value": "11144477735", "owner_ref": ""},
        ]), operator_username="op")
    assert list(Customer.objects.values()) == original


def test_receipt_save_validates_third_party_snapshot_without_copying_it(owner):
    from shopman.shop.services.pos import resolve_or_create_customer
    current = Customer.objects.create(ref="current", first_name="Bia")
    original_owner = dict(Customer.objects.values().get(pk=owner.pk))
    action = receipt_action(action="save", customer_ref=current.ref, target_ref=current.ref, fields=[
        {"field": "tax_id", "value": owner.document, "owner_ref": owner.ref},
        {"field": "email", "value": "new@example.org", "owner_ref": ""},
    ])
    result = resolve_or_create_customer(receipt_identity_action=action, operator_username="op")
    assert result["ref"] == current.ref
    current.refresh_from_db()
    assert current.document == ""
    assert current.email == "new@example.org"
    assert dict(Customer.objects.values().get(pk=owner.pk)) == original_owner
    assert Customer.objects.count() == 2


def test_receipt_save_new_cpf_keeps_third_party_email_outside_customer(owner):
    from shopman.shop.services.pos import resolve_or_create_customer
    current = Customer.objects.create(ref="current", first_name="Bia")
    original_owner = dict(Customer.objects.values().get(pk=owner.pk))
    action = receipt_action(action="save", customer_ref=current.ref, target_ref=current.ref, fields=[
        {"field": "tax_id", "value": "11144477735", "owner_ref": ""},
        {"field": "email", "value": owner.email, "owner_ref": owner.ref},
    ])
    resolve_or_create_customer(receipt_identity_action=action, operator_username="op")
    current.refresh_from_db()
    assert current.document == "11144477735"
    assert current.email == ""
    assert dict(Customer.objects.values().get(pk=owner.pk)) == original_owner
