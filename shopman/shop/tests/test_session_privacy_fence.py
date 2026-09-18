from __future__ import annotations

import pytest
from shopman.guestman.models import Customer
from shopman.orderman.exceptions import SessionError
from shopman.orderman.models import Session, SessionEvent
from shopman.orderman.services.modify import ModifyService

from shopman.shop.services import cart, sessions
from shopman.shop.services.account import _anonymize_order_trail

pytestmark = pytest.mark.django_db


def _customer(suffix: str = "01") -> Customer:
    return Customer.objects.create(
        ref=f"CUS-SESSION-PRIV-{suffix}",
        first_name="Ana",
        phone=f"+5543999920{suffix}",
    )


def _anonymized_session(suffix: str = "01") -> Session:
    return Session.objects.create(
        session_key=f"session-privacy-{suffix}",
        channel_ref="web",
        handle_type="anonymized",
        handle_ref=f"ANON-{suffix}",
        data={"origin_channel": "web"},
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("customer.ref", "CUS-STALE"),
        ("customer_ref", "CUS-STALE"),
        ("customer_phone", "+554399999999"),
        ("delivery_address_structured", {"route": "Rua Identificável"}),
        ("recipient.phone", "+554399999999"),
        ("order_notes", "texto livre pessoal"),
    ],
)
def test_modify_set_data_never_repopulates_anonymized_session(path, value):
    session = _anonymized_session(path.replace(".", "-")[:20])

    with pytest.raises(SessionError) as exc_info:
        ModifyService.modify_session(
            session_key=session.session_key,
            channel_ref=session.channel_ref,
            ops=[{"op": "set_data", "path": path, "value": value}],
        )

    assert exc_info.value.code == "session_anonymized"
    session.refresh_from_db()
    assert session.data == {"origin_channel": "web"}
    assert session.rev == 0


def test_stale_model_instance_cannot_restore_identity_or_pii_after_deletion_marker():
    session = Session.objects.create(
        session_key="session-privacy-stale",
        channel_ref="web",
        handle_type="phone",
        handle_ref="+554399999991",
        data={"customer": {"ref": "CUS-STALE"}},
    )
    stale = Session.objects.get(pk=session.pk)
    Session.objects.filter(pk=session.pk).update(
        handle_type="anonymized",
        handle_ref="ANON-stale",
        data={},
    )

    stale.data = {"customer": {"ref": "CUS-STALE"}}
    with pytest.raises(SessionError) as exc_info:
        stale.save(update_fields=["data"])
    assert exc_info.value.code == "session_anonymized"

    stale.handle_type = "phone"
    stale.handle_ref = "+554399999991"
    with pytest.raises(SessionError) as exc_info:
        stale.save(update_fields=["handle_type", "handle_ref"])
    assert exc_info.value.code == "session_anonymized"

    stale.handle_type = "anonymized"
    stale.handle_ref = "+554399999991"
    with pytest.raises(SessionError) as exc_info:
        stale.save(update_fields=["handle_ref"])
    assert exc_info.value.code == "session_anonymized"

    session.refresh_from_db()
    assert session.handle_type == "anonymized"
    assert session.data == {}


def test_assign_writers_cannot_reidentify_anonymized_session():
    customer = _customer("02")
    session = _anonymized_session("assign")

    with pytest.raises(SessionError, match="anonimizada"):
        sessions.assign_phone_handle(
            session_key=session.session_key,
            channel_ref=session.channel_ref,
            phone=customer.phone,
        )
    with pytest.raises(SessionError, match="anonimizada"):
        sessions.assign_handle(
            session_key=session.session_key,
            channel_ref=session.channel_ref,
            handle_type="customer",
            handle_ref=customer.ref,
        )

    with pytest.raises(SessionError, match="dados pessoais"):
        sessions.assign_customer(
            session_key=session.session_key,
            channel_ref=session.channel_ref,
            customer_uuid=customer.uuid,
        )
    session.refresh_from_db()
    assert session.handle_type == "anonymized"
    assert "customer" not in session.data


def test_assign_customer_revalidates_active_canonical_owner():
    customer = _customer("03")
    session = Session.objects.create(
        session_key="session-privacy-inactive-owner",
        channel_ref="web",
        data={},
    )
    Customer.objects.filter(pk=customer.pk).update(is_active=False)

    assert sessions.assign_customer(
        session_key=session.session_key,
        channel_ref=session.channel_ref,
        customer_uuid=customer.uuid,
    ) is False
    session.refresh_from_db()
    assert "customer" not in session.data

    with pytest.raises(SessionError) as exc_info:
        sessions.assign_handle(
            session_key=session.session_key,
            channel_ref=session.channel_ref,
            handle_type="customer",
            handle_ref=customer.ref,
        )
    assert exc_info.value.code == "customer_inactive"
    session.refresh_from_db()
    assert session.handle_type is None


def test_coupon_and_delivery_direct_writers_obey_anonymized_fence():
    customer = _customer("04")
    session = _anonymized_session("cart")

    with pytest.raises(SessionError) as coupon_error:
        cart.apply_coupon_code(
            session_key=session.session_key,
            channel_ref=session.channel_ref,
            code="PRIV10",
            customer={"ref": customer.ref, "price_tier": "VIP"},
        )
    assert coupon_error.value.code == "session_anonymized"

    with pytest.raises(SessionError) as address_error:
        cart.set_delivery_draft(
            session_key=session.session_key,
            channel_ref=session.channel_ref,
            fulfillment_type="delivery",
            delivery_address_structured={"route": "Rua Identificável", "number": "10"},
        )
    assert address_error.value.code == "session_anonymized"

    session.refresh_from_db()
    assert session.data == {"origin_channel": "web"}


@pytest.mark.parametrize(
    "meta",
    [
        {"customer_note": "ligar para Ana"},
        {"customization": {"note": "nome no bolo"}},
        {"customization": {"text": "parabéns Ana"}},
        {"customization": {"message": "entregar para Ana"}},
    ],
)
def test_anonymized_session_rejects_personal_line_metadata(meta):
    session = _anonymized_session("line-meta")

    with pytest.raises(SessionError) as exc_info:
        ModifyService.modify_session(
            session_key=session.session_key,
            channel_ref=session.channel_ref,
            ops=[
                {
                    "op": "add_line",
                    "sku": "SKU-PRIVACY",
                    "qty": 1,
                    "unit_price_q": 1000,
                    "meta": meta,
                }
            ],
        )

    assert exc_info.value.code == "session_anonymized"
    session.refresh_from_db()
    assert session.items == []


def test_anonymized_session_keeps_commercial_line_metadata():
    session = _anonymized_session("commercial-meta")

    updated = ModifyService.modify_session(
        session_key=session.session_key,
        channel_ref=session.channel_ref,
        ops=[
            {
                "op": "add_line",
                "sku": "SKU-COMMERCIAL",
                "qty": 1,
                "unit_price_q": 1000,
                "meta": {
                    "batch_ref": "LOT-2026-09",
                    "customization": {"size": "large", "icing": "chocolate"},
                },
            }
        ],
    )

    meta = updated.items[0]["meta"]
    assert meta["batch_ref"] == "LOT-2026-09"
    assert meta["customization"] == {"size": "large", "icing": "chocolate"}
    assert "customer_note" not in meta


def test_replace_sku_cannot_add_personal_line_metadata_after_anonymization():
    session = Session.objects.create(
        session_key="session-privacy-replace-meta",
        channel_ref="web",
        items=[
            {
                "line_id": "LINE-PRIVACY",
                "sku": "SKU-OLD",
                "qty": 1,
                "unit_price_q": 1000,
                "meta": {"batch_ref": "LOT-OLD"},
            }
        ],
        data={},
    )
    Session.objects.filter(pk=session.pk).update(
        handle_type="anonymized",
        handle_ref="ANON-replace-meta",
    )

    with pytest.raises(SessionError) as exc_info:
        ModifyService.modify_session(
            session_key=session.session_key,
            channel_ref=session.channel_ref,
            ops=[
                {
                    "op": "replace_sku",
                    "line_id": "LINE-PRIVACY",
                    "sku": "SKU-NEW",
                    "unit_price_q": 1200,
                    "meta": {"customization": {"message": "para Ana"}},
                }
            ],
        )

    assert exc_info.value.code == "session_anonymized"
    session.refresh_from_db()
    assert session.items[0]["sku"] == "SKU-OLD"
    assert session.items[0]["meta"] == {"batch_ref": "LOT-OLD"}


@pytest.mark.parametrize(
    "payload",
    [
        {"note": "texto pessoal", "sku": "SKU-1"},
        {"customer_phone": "+554399999999"},
        {"context": {"customer_name": "Ana", "protocol": "PROTO-1"}},
    ],
)
def test_anonymized_session_rejects_personal_event_payload(payload):
    session = _anonymized_session("event-personal")

    with pytest.raises(SessionError) as exc_info:
        session.emit_event("manual_context", payload=payload)

    assert exc_info.value.code == "session_anonymized"
    assert not SessionEvent.objects.filter(session_key=session.session_key).exists()


def test_anonymized_session_still_accepts_operational_event_payload():
    session = _anonymized_session("event-operational")

    event = session.emit_event(
        "line_fired",
        actor="operator:test",
        payload={"sku": "SKU-1", "qty": 2, "protocol": "PROTO-1"},
    )

    assert event.payload == {"sku": "SKU-1", "qty": 2, "protocol": "PROTO-1"}


def test_deletion_scrubs_personal_event_written_before_session_was_anonymized():
    customer = _customer("05")
    session = Session.objects.create(
        session_key="session-privacy-event-writer-first",
        channel_ref="web",
        handle_type="phone",
        handle_ref=customer.phone,
        data={"customer": {"ref": customer.ref, "phone": customer.phone}},
    )
    event = session.emit_event(
        "manual_context",
        payload={
            "customer_phone": customer.phone,
            "context": {"customer_name": "Ana", "protocol": "PROTO-KEEP"},
            "sku": "SKU-KEEP",
        },
    )

    _anonymize_order_trail(
        customer_ref=customer.ref,
        phone=customer.phone,
        pseudonym="ANON-event-writer-first",
    )

    event.refresh_from_db()
    assert event.payload == {
        "context": {"protocol": "PROTO-KEEP"},
        "sku": "SKU-KEEP",
    }
