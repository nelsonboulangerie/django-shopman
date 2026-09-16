"""WP-3 — "Me avise quando disponível" (stock-back alerts).

Cobre: subscribe (canal verificado/dedup/sem contato), endpoint web autenticado,
notify idempotente (dispara só quando disponível, marca uma vez, não marca em
falha de envio) e compatibilidade das capacidades de sessão legadas.
"""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.db import IntegrityError
from django.utils import timezone
from shopman.guestman import ConsentService
from shopman.guestman.models import Customer
from shopman.offerman.models import Product

from shopman.shop.protocols import NotificationResult
from shopman.storefront.models import StockAlertDelivery, StockAlertOccurrence, StockAlertSubscription
from shopman.storefront.services import stock_alerts
from shopman.storefront.stock_alert_delivery import StockAlertDeliveryHandler

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def configured_channel():
    from shopman.shop.models import Channel

    Channel.objects.get_or_create(ref="web", defaults={"name": "Web", "is_active": True})


PHONE = "+5543999990001"


@pytest.fixture
def isolated_stock_intent_rate_limit():
    """Intent cases must not spend the shared in-memory limiter of later cases."""
    cache.clear()
    yield
    cache.clear()


def _state(can_add: bool, available_qty: int | None = None):
    return MagicMock(can_add_to_cart=can_add, available_qty=available_qty)


def _publish(sku="SKU-NOTIFY", *, is_batch_produced=False):
    return Product.objects.create(
        sku=sku,
        name="Pão Teste",
        base_price_q=500,
        is_published=True,
        is_sellable=True,
        is_batch_produced=is_batch_produced,
    )


def _move(
    sku: str,
    *,
    kind: str = "buy",
    delta=1,
    metadata=None,
    target_date=None,
):
    """Um ``Move`` de mentira, com o ``kind`` que o receptor lê para decidir a rede."""
    fake = MagicMock(pk=42, quant_id=1, kind=kind, delta=delta, metadata=metadata or {})
    fake.quant.sku = sku
    fake.quant.target_date = target_date
    return fake


def _deliver_queued():
    for delivery in StockAlertDelivery.objects.filter(status="queued").order_by("pk"):
        StockAlertDeliveryHandler().handle(message=MagicMock(payload={"delivery_id": delivery.pk}), ctx={})


def _authenticate(client, *, ref="CUS-AUTH-NOTIFY", phone=PHONE):
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    customer = Customer.objects.create(ref=ref, first_name="Ana", phone=phone)
    info = AuthCustomerInfo(
        uuid=customer.uuid,
        name=customer.name,
        phone=customer.phone,
        email=None,
        is_active=True,
    )
    user, _created = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")
    return customer


def _mark_legacy_session(client, sub):
    """Reproduz uma capacidade anônima emitida antes da exigência de login."""
    session = client.session
    session["stock_alert_subscriptions"] = [
        {
            "ref": str(sub.ref),
            "sku": sub.sku,
            "alert_type": sub.alert_type,
            "contact_phone": sub.contact_phone,
        }
    ]
    session.save()


# ── subscribe ───────────────────────────────────────────────────────


def test_subscribe_anonymous_creates_pending():
    sub = stock_alerts.subscribe("SKU-1", channel_ref="web", phone=PHONE, adult_declared=True)
    assert sub is not None
    assert sub.is_pending
    assert sub.contact_phone == PHONE


def test_subscribe_dedupes_pending_for_same_contact():
    a = stock_alerts.subscribe("SKU-1", phone=PHONE, adult_declared=True)
    b = stock_alerts.subscribe("SKU-1", phone=PHONE, adult_declared=True)
    assert a.pk == b.pk
    assert StockAlertSubscription.objects.filter(sku="SKU-1").count() == 1


def test_subscribe_dedupes_phone_formats_and_keeps_verifiable_evidence():
    first = stock_alerts.subscribe("SKU-NORM", phone="(43) 99999-0001", adult_declared=True)
    second = stock_alerts.subscribe("SKU-NORM", phone="+55 43 99999-0001", adult_declared=True)

    assert first.pk == second.pk
    assert first.contact_phone == "+5543999990001"
    assert first.proof_status == "verified"
    assert first.adult_declared is True
    assert first.disclosure_version == stock_alerts.STOCK_ALERT_DISCLOSURE_VERSION
    assert len(first.disclosure_hash) == 64
    assert len(first.evidence_hash) == 64
    assert first.expires_at is None


def test_database_unique_rejects_two_pending_rows_for_same_target():
    original = stock_alerts.subscribe("SKU-UNIQUE", phone=PHONE, adult_declared=True)

    with pytest.raises(IntegrityError):
        StockAlertSubscription.objects.create(
            sku=original.sku,
            alert_type=original.alert_type,
            channel_ref=original.channel_ref,
            contact_phone=original.contact_phone,
            target_key=original.target_key,
            disclosure_text=original.disclosure_text,
            disclosure_version=original.disclosure_version,
            disclosure_hash=original.disclosure_hash,
            evidence_hash="f" * 64,
            proof_status="verified",
            expires_at=original.expires_at,
        )


def test_subscribe_requires_a_contact():
    assert stock_alerts.subscribe("SKU-1", adult_declared=True) is None


def test_subscribe_requires_an_adult_declaration():
    assert stock_alerts.subscribe("SKU-ADULT-OMITTED", phone=PHONE) is None
    assert stock_alerts.subscribe("SKU-ADULT", phone=PHONE, adult_declared=False) is None
    assert not StockAlertSubscription.objects.filter(
        sku__in=("SKU-ADULT-OMITTED", "SKU-ADULT")
    ).exists()


def test_subscribe_known_minor_cannot_override_birthday_with_declaration():
    today = timezone.localdate()
    customer = Customer.objects.create(
        ref="CUS-KNOWN-MINOR",
        first_name="Ana",
        phone=PHONE,
        birthday=today.replace(year=today.year - 17),
    )

    outcome = stock_alerts.subscribe_with_outcome(
        "SKU-KNOWN-MINOR",
        customer=customer,
        adult_declared=True,
    )

    assert outcome.subscription is None
    assert outcome.created is False
    assert not StockAlertSubscription.objects.filter(sku="SKU-KNOWN-MINOR").exists()


def test_subscribe_race_with_ineligible_old_writer_fails_closed_without_500():
    with patch.object(StockAlertSubscription.objects, "create", side_effect=IntegrityError):
        outcome = stock_alerts.subscribe_with_outcome(
            "SKU-OLD-WRITER-RACE",
            phone=PHONE,
            adult_declared=True,
        )

    assert outcome.subscription is None
    assert outcome.created is False


def test_subscribe_rejects_ambiguous_mobile_without_creating_subscription():
    assert stock_alerts.subscribe("SKU-AMBIGUOUS", phone="(43) 9840-4900", adult_declared=True) is None
    assert not StockAlertSubscription.objects.filter(sku="SKU-AMBIGUOUS").exists()


def test_subscribe_reconfirms_legacy_row_without_consent_evidence():
    legacy = StockAlertSubscription.objects.create(
        sku="SKU-LEGACY",
        alert_type="stock_back",
        channel_ref="web",
        contact_phone=PHONE,
        target_key=stock_alerts._target_key(customer_ref="", phone=PHONE),
        proof_status="legacy_unverified",
    )

    current = stock_alerts.subscribe("SKU-LEGACY", phone=PHONE, alert_type="stock_back", adult_declared=True)

    legacy.refresh_from_db()
    assert legacy.revoked_at is not None
    assert legacy.revoke_reason == "reconfirmed_with_evidence"
    assert legacy.revocation_evidence_hash
    assert current.pk != legacy.pk
    assert current.proof_status == "verified"
    assert current.is_active


def test_subscribe_reconfirms_verified_row_without_adult_declaration():
    legacy = StockAlertSubscription.objects.create(
        sku="SKU-LEGACY-AGE",
        alert_type="stock_back",
        channel_ref="web",
        contact_phone=PHONE,
        target_key=stock_alerts._target_key(customer_ref="", phone=PHONE),
        disclosure_text="Texto antigo.",
        disclosure_version="stock-availability-pt-BR-v3",
        disclosure_hash="a" * 64,
        evidence_hash="b" * 64,
        proof_status="verified",
        adult_declared=False,
    )

    current = stock_alerts.subscribe("SKU-LEGACY-AGE", phone=PHONE, alert_type="stock_back", adult_declared=True)

    legacy.refresh_from_db()
    assert legacy.revoked_at is not None
    assert current.pk != legacy.pk
    assert current.adult_declared is True
    assert current.is_active


def test_legacy_row_cannot_resume_without_a_fresh_adult_declaration():
    legacy = StockAlertSubscription.objects.create(
        sku="SKU-LEGACY-RESUME",
        alert_type="stock_back",
        channel_ref="web",
        contact_phone=PHONE,
        target_key=stock_alerts._target_key(customer_ref="", phone=PHONE),
        evidence_hash="e" * 64,
        proof_status="verified",
        adult_declared=False,
        paused_at=timezone.now(),
    )

    resumed = stock_alerts.set_paused(
        legacy.ref,
        paused=False,
        sku=legacy.sku,
        phone=PHONE,
    )

    assert resumed is False
    legacy.refresh_from_db()
    assert legacy.paused_at is not None


def test_known_minor_cannot_resume_existing_alert():
    today = timezone.localdate()
    customer = Customer.objects.create(
        ref="CUS-MINOR-RESUME",
        first_name="Ana",
        phone=PHONE,
        birthday=today.replace(year=today.year - 30),
    )
    sub = stock_alerts.subscribe("SKU-MINOR-RESUME", customer=customer, adult_declared=True)
    assert stock_alerts.set_paused(
        sub.ref,
        paused=True,
        sku=sub.sku,
        customer=customer,
    )
    Customer.objects.filter(pk=customer.pk).update(
        birthday=today.replace(year=today.year - 17)
    )

    resumed = stock_alerts.set_paused(
        sub.ref,
        paused=False,
        sku=sub.sku,
        customer=customer,
    )

    assert resumed is False
    sub.refresh_from_db()
    assert sub.paused_at is not None


# ── notify ──────────────────────────────────────────────────────────


def test_notify_sends_and_marks_when_available():
    sub = stock_alerts.subscribe("SKU-1", phone=PHONE, adult_declared=True)
    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)),
        patch("shopman.shop.notifications.notify", return_value=MagicMock(success=True)) as nf,
    ):
        notified = stock_alerts.notify_back_in_stock("SKU-1")
        _deliver_queued()

    assert notified == 1
    nf.assert_called_once()
    assert nf.call_args.kwargs["event"] == "stock_arrived"
    assert nf.call_args.kwargs["recipient"] == PHONE
    sub.refresh_from_db()
    assert sub.notified_at is not None


def test_notify_context_includes_truthful_availability_phrase():
    stock_alerts.subscribe("SKU-1", phone=PHONE, alert_type="production_ready", adult_declared=True)
    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True, available_qty=12)),
        patch(
            "shopman.shop.services.quality.reviewed_saleable_quantity",
            return_value=Decimal("12"),
        ),
        patch("shopman.shop.notifications.notify", return_value=MagicMock(success=True)) as nf,
    ):
        notified = stock_alerts.notify_bake_ready("SKU-1")
        _deliver_queued()

    assert notified == 1
    assert nf.call_args.kwargs["event"] == "production_ready"
    context = nf.call_args.kwargs["context"]
    assert context["available_qty"] == "12"
    assert context["availability_phrase"] == "Neste momento ainda temos 12 unidades."
    assert urlsplit(context["management_url"]).path == "/gerenciar-aviso"
    assert urlsplit(context["management_url"]).fragment
    assert context["management_url"] in context["management_note"]


def test_notify_context_uses_neutral_phrase_when_quantity_is_unknown():
    stock_alerts.subscribe("SKU-1", phone=PHONE, alert_type="stock_back", adult_declared=True)
    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)),
        patch("shopman.shop.notifications.notify", return_value=MagicMock(success=True)) as nf,
    ):
        notified = stock_alerts.notify_back_in_stock("SKU-1")
        _deliver_queued()

    assert notified == 1
    context = nf.call_args.kwargs["context"]
    assert context["available_qty"] == ""
    assert context["availability_phrase"] == "Já está disponível para pedido."


def test_availability_phrase_uses_singular_for_one_unit():
    from shopman.shop.services.availability_copy import availability_phrase

    assert availability_phrase(1) == "Neste momento ainda temos 1 unidade."


def test_notify_skips_when_still_unavailable():
    sub = stock_alerts.subscribe("SKU-1", phone=PHONE, adult_declared=True)
    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(False)),
        patch("shopman.shop.notifications.notify") as nf,
    ):
        notified = stock_alerts.notify_back_in_stock("SKU-1")

    assert notified == 0
    nf.assert_not_called()
    sub.refresh_from_db()
    assert sub.notified_at is None


def test_non_sellable_bake_is_recorded_blocked_and_subscription_stays_active():
    sub = stock_alerts.subscribe("SKU-QC-BLOCK", phone=PHONE, alert_type="production_ready", adult_declared=True)
    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(False)),
        patch(
            "shopman.shop.services.quality.reviewed_saleable_quantity",
            return_value=Decimal("10"),
        ),
        patch("shopman.shop.notifications.notify") as notify,
    ):
        first = stock_alerts.notify_bake_ready(sub.sku, source_ref="work-order-qc-1")
        replay = stock_alerts.notify_bake_ready(sub.sku, source_ref="work-order-qc-1")

    assert first == replay == 0
    notify.assert_not_called()
    occurrence = StockAlertOccurrence.objects.get()
    assert occurrence.status == "blocked"
    assert occurrence.status_reason == "unavailable_after_quality_review"
    assert occurrence.closed_at is not None
    assert not StockAlertDelivery.objects.exists()
    assert StockAlertSubscription.objects.get(pk=sub.pk).is_active


def test_finished_bake_stays_pending_until_manager_review_then_queues_once():
    sub = stock_alerts.subscribe("SKU-QC-PENDING", phone=PHONE, alert_type="production_ready", adult_declared=True)

    assert stock_alerts.record_bake_pending(sub.sku, source_ref="work-order-qc-2") == 1
    occurrence = StockAlertOccurrence.objects.get()
    assert occurrence.status == "pending"
    assert occurrence.status_reason == "awaiting_quality_review"
    assert not StockAlertDelivery.objects.exists()

    with (
        patch(
            "shopman.shop.services.quality.reviewed_saleable_quantity",
            return_value=Decimal("6"),
        ),
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True, 10)),
    ):
        assert stock_alerts.review_bake_ready(sub.sku, source_ref="work-order-qc-2") == 1
        assert stock_alerts.review_bake_ready(sub.sku, source_ref="work-order-qc-2") == 0

    occurrence.refresh_from_db()
    assert occurrence.status == "eligible"
    assert occurrence.status_reason == "quality_reviewed_sellable"
    assert occurrence.available_qty == Decimal("6")
    assert StockAlertDelivery.objects.count() == 1


def test_reviewed_bake_with_no_channel_eligible_quality_is_blocked():
    sub = stock_alerts.subscribe("SKU-QC-FAIR", phone=PHONE, alert_type="production_ready", adult_declared=True)
    stock_alerts.record_bake_pending(sub.sku, source_ref="work-order-qc-3")

    with (
        patch(
            "shopman.shop.services.quality.reviewed_saleable_quantity",
            return_value=Decimal("0"),
        ),
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True, 10)),
    ):
        assert stock_alerts.review_bake_ready(sub.sku, source_ref="work-order-qc-3") == 0

    occurrence = StockAlertOccurrence.objects.get()
    assert occurrence.status == "blocked"
    assert occurrence.status_reason == "quality_not_sellable_for_channel"
    assert occurrence.closed_at is not None
    assert not StockAlertDelivery.objects.exists()
    assert StockAlertSubscription.objects.get(pk=sub.pk).is_active


def test_quality_change_before_provider_suppresses_queued_bake_delivery():
    sub = stock_alerts.subscribe("SKU-QC-CHANGED", phone=PHONE, alert_type="production_ready", adult_declared=True)
    stock_alerts.record_bake_pending(sub.sku, source_ref="work-order-qc-4")
    with (
        patch(
            "shopman.shop.services.quality.reviewed_saleable_quantity",
            return_value=Decimal("5"),
        ),
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True, 5)),
    ):
        assert stock_alerts.review_bake_ready(sub.sku, source_ref="work-order-qc-4") == 1

    with (
        patch(
            "shopman.shop.services.quality.reviewed_saleable_quantity",
            return_value=Decimal("0"),
        ),
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True, 5)),
        patch("shopman.shop.notifications.notify") as notify,
    ):
        assert stock_alerts.review_bake_ready(sub.sku, source_ref="work-order-qc-4") == 0
        _deliver_queued()

    notify.assert_not_called()
    assert StockAlertOccurrence.objects.get().status == "blocked"
    assert StockAlertDelivery.objects.get().status == "suppressed"


def test_notify_is_idempotent_within_one_occurrence_but_subscription_stays_active():
    stock_alerts.subscribe("SKU-1", phone=PHONE, adult_declared=True)
    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)),
        patch("shopman.shop.notifications.notify", return_value=MagicMock(success=True)),
    ):
        stock_alerts.notify_back_in_stock("SKU-1")
        _deliver_queued()
        again = stock_alerts.notify_back_in_stock("SKU-1")

    assert again == 0
    assert StockAlertSubscription.objects.get(sku="SKU-1").is_active


def test_notify_does_not_mark_on_send_failure():
    sub = stock_alerts.subscribe("SKU-1", phone=PHONE, adult_declared=True)
    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)),
        patch("shopman.shop.notifications.notify", return_value=MagicMock(success=False)),
    ):
        notified = stock_alerts.notify_back_in_stock("SKU-1")
        with pytest.raises(Exception, match="provider rejected"):
            _deliver_queued()

    assert notified == 1
    sub.refresh_from_db()
    assert sub.notified_at is None
    assert StockAlertDelivery.objects.get().status == "retryable"


def test_revoke_before_notify_prevents_delivery_and_preserves_evidence():
    sub = stock_alerts.subscribe("SKU-REVOKE", phone=PHONE, adult_declared=True)
    original_evidence = sub.evidence_hash
    assert stock_alerts.revoke(sub.ref, sku=sub.sku, phone=PHONE) is True

    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)),
        patch("shopman.shop.notifications.notify") as nf,
    ):
        assert stock_alerts.notify_back_in_stock(sub.sku) == 0

    nf.assert_not_called()
    sub.refresh_from_db()
    assert sub.evidence_hash == original_evidence
    assert sub.revoked_at is not None
    assert len(sub.revocation_evidence_hash) == 64


def test_global_optout_is_rechecked_immediately_before_stock_alert_send():
    customer = Customer.objects.create(
        ref="CLI-STOCK-OPTOUT",
        first_name="Ana",
        phone=PHONE,
    )
    sub = stock_alerts.subscribe("SKU-OPTOUT", customer=customer, adult_declared=True)
    ConsentService.revoke_consent(customer.ref, "whatsapp")

    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)),
        patch("shopman.shop.notifications.notify") as nf,
    ):
        assert stock_alerts.notify_back_in_stock(sub.sku) == 1
        _deliver_queued()

    nf.assert_not_called()
    sub.refresh_from_db()
    assert sub.notified_at is None


# ── endpoint ────────────────────────────────────────────────────────


def test_anonymous_intent_records_only_short_lived_session_proof(client, isolated_stock_intent_rate_limit):
    product = _publish(sku="SKU-INTENT")

    response = client.post(
        f"/api/v1/availability/{product.sku}/notify/intent/",
        {"adult_declared": True, "phone": "+5543000000000", "email": "ignored@example.com"},
        REMOTE_ADDR="203.0.113.21",
    )

    assert response.status_code == 200
    assert response["Cache-Control"] == "private, no-store, max-age=0"
    body = response.json()
    assert body["ok"] is True
    assert body["intent_ref"]
    assert body["expires_at"]
    assert not StockAlertSubscription.objects.filter(sku=product.sku).exists()
    marker = client.session["stock_alert_intents"][0]
    assert marker["ref"] == body["intent_ref"]
    assert marker["sku"] == product.sku
    assert marker["adult_declared"] is True
    assert marker["adult_declared_at"]
    assert marker["disclosure_version"] == "recurring-whatsapp-adult-v1"
    assert "phone" not in marker
    assert "email" not in marker
    assert "cpf" not in marker


def test_anonymous_intent_requires_explicit_adult_declaration(client, isolated_stock_intent_rate_limit):
    product = _publish(sku="SKU-INTENT-NO-CONSENT")

    response = client.post(
        f"/api/v1/availability/{product.sku}/notify/intent/",
        {},
        REMOTE_ADDR="203.0.113.22",
    )

    assert response.status_code == 400
    assert response.json()["field"] == "adult_declared"
    assert client.session.get("stock_alert_intents") in (None, [])


def test_authenticated_return_consumes_matching_session_intent_automatically(client, isolated_stock_intent_rate_limit):
    product = _publish(sku="SKU-INTENT-RETURN")
    prepared = client.post(
        f"/api/v1/availability/{product.sku}/notify/intent/",
        {"adult_declared": True},
        REMOTE_ADDR="203.0.113.23",
    ).json()
    customer = _authenticate(client, ref="CUS-INTENT-RETURN")

    response = client.post(
        f"/api/v1/availability/{product.sku}/notify/",
        {"intent_ref": prepared["intent_ref"]},
        REMOTE_ADDR="203.0.113.24",
    )

    assert response.status_code == 200
    sub = StockAlertSubscription.objects.get(sku=product.sku)
    assert sub.customer_ref == customer.ref
    assert sub.contact_phone == PHONE
    assert sub.adult_declared is True
    marker = client.session["stock_alert_intents"][0]
    assert marker["completed_customer_ref"] == customer.ref


def test_manipulated_or_cross_session_intent_cannot_subscribe(client, isolated_stock_intent_rate_limit):
    from django.test import Client

    product = _publish(sku="SKU-INTENT-BOUNDARY")
    prepared = client.post(
        f"/api/v1/availability/{product.sku}/notify/intent/",
        {"adult_declared": True},
        REMOTE_ADDR="203.0.113.25",
    ).json()
    other_session = Client()
    _authenticate(other_session, ref="CUS-INTENT-OTHER")

    response = other_session.post(
        f"/api/v1/availability/{product.sku}/notify/",
        {"intent_ref": prepared["intent_ref"]},
        REMOTE_ADDR="203.0.113.26",
    )

    assert response.status_code == 400
    assert response.json()["field"] == "intent_ref"
    assert not StockAlertSubscription.objects.filter(sku=product.sku).exists()


def test_expired_session_intent_cannot_subscribe(client, isolated_stock_intent_rate_limit):
    product = _publish(sku="SKU-INTENT-EXPIRED")
    prepared = client.post(
        f"/api/v1/availability/{product.sku}/notify/intent/",
        {"adult_declared": True},
        REMOTE_ADDR="203.0.113.27",
    ).json()
    session = client.session
    session["stock_alert_intents"][0]["created_at"] -= 16 * 60
    session.save()
    _authenticate(client, ref="CUS-INTENT-EXPIRED")

    response = client.post(
        f"/api/v1/availability/{product.sku}/notify/",
        {"intent_ref": prepared["intent_ref"]},
        REMOTE_ADDR="203.0.113.28",
    )

    assert response.status_code == 400
    assert response.json()["field"] == "intent_ref"
    assert not StockAlertSubscription.objects.filter(sku=product.sku).exists()


def test_completed_intent_replays_for_same_customer_after_lost_response(client, isolated_stock_intent_rate_limit):
    product = _publish(sku="SKU-INTENT-REPLAY")
    prepared = client.post(
        f"/api/v1/availability/{product.sku}/notify/intent/",
        {"adult_declared": True},
        REMOTE_ADDR="203.0.113.29",
    ).json()
    _authenticate(client, ref="CUS-INTENT-REPLAY")
    payload = {"intent_ref": prepared["intent_ref"]}

    first = client.post(
        f"/api/v1/availability/{product.sku}/notify/",
        payload,
        REMOTE_ADDR="203.0.113.30",
    )
    repeated = client.post(
        f"/api/v1/availability/{product.sku}/notify/",
        payload,
        REMOTE_ADDR="203.0.113.30",
    )

    assert first.status_code == repeated.status_code == 200
    assert first.json()["management_url"] == repeated.json()["management_url"]
    assert StockAlertSubscription.objects.filter(sku=product.sku).count() == 1


def test_completed_intent_replay_does_not_resume_a_later_pause(client, isolated_stock_intent_rate_limit):
    product = _publish(sku="SKU-INTENT-PAUSED-REPLAY")
    prepared = client.post(
        f"/api/v1/availability/{product.sku}/notify/intent/",
        {"adult_declared": True},
        REMOTE_ADDR="203.0.113.33",
    ).json()
    customer = _authenticate(client, ref="CUS-INTENT-PAUSED-REPLAY")
    payload = {"intent_ref": prepared["intent_ref"]}
    assert client.post(
        f"/api/v1/availability/{product.sku}/notify/",
        payload,
        REMOTE_ADDR="203.0.113.34",
    ).status_code == 200
    sub = StockAlertSubscription.objects.get(sku=product.sku)
    assert stock_alerts.set_paused(sub.ref, paused=True, sku=sub.sku, customer=customer)

    repeated = client.post(
        f"/api/v1/availability/{product.sku}/notify/",
        payload,
        REMOTE_ADDR="203.0.113.34",
    )

    sub.refresh_from_db()
    assert repeated.status_code == 200
    assert repeated.json()["active"] is False
    assert sub.paused_at is not None
    assert StockAlertSubscription.objects.filter(sku=product.sku).count() == 1


def test_completed_intent_replay_does_not_recreate_a_cancelled_alert(client, isolated_stock_intent_rate_limit):
    product = _publish(sku="SKU-INTENT-CANCELLED-REPLAY")
    prepared = client.post(
        f"/api/v1/availability/{product.sku}/notify/intent/",
        {"adult_declared": True},
        REMOTE_ADDR="203.0.113.35",
    ).json()
    customer = _authenticate(client, ref="CUS-INTENT-CANCELLED-REPLAY")
    payload = {"intent_ref": prepared["intent_ref"]}
    assert client.post(
        f"/api/v1/availability/{product.sku}/notify/",
        payload,
        REMOTE_ADDR="203.0.113.36",
    ).status_code == 200
    sub = StockAlertSubscription.objects.get(sku=product.sku)
    assert stock_alerts.revoke(sub.ref, sku=sub.sku, customer=customer)

    repeated = client.post(
        f"/api/v1/availability/{product.sku}/notify/",
        payload,
        REMOTE_ADDR="203.0.113.36",
    )

    sub.refresh_from_db()
    assert repeated.status_code == 200
    assert repeated.json()["active"] is False
    assert "management_url" not in repeated.json()
    assert sub.revoked_at is not None
    assert StockAlertSubscription.objects.filter(sku=product.sku).count() == 1


def test_known_minor_cannot_complete_prelogin_intent(client, isolated_stock_intent_rate_limit):
    product = _publish(sku="SKU-INTENT-MINOR")
    prepared = client.post(
        f"/api/v1/availability/{product.sku}/notify/intent/",
        {"adult_declared": True},
        REMOTE_ADDR="203.0.113.31",
    ).json()
    customer = _authenticate(client, ref="CUS-INTENT-MINOR")
    today = timezone.localdate()
    customer.birthday = today.replace(year=today.year - 17)
    customer.save(update_fields=["birthday"])

    response = client.post(
        f"/api/v1/availability/{product.sku}/notify/",
        {"intent_ref": prepared["intent_ref"]},
        REMOTE_ADDR="203.0.113.32",
    )

    assert response.status_code == 400
    assert response.json()["field"] == "birthday"
    assert not StockAlertSubscription.objects.filter(sku=product.sku).exists()


def test_endpoint_anonymous_requires_verified_identity_and_ignores_typed_phone(client):
    p = _publish()
    path = f"/api/v1/availability/{p.sku}/notify/"
    resp = client.post(path, {"phone": PHONE})
    assert resp.status_code == 401
    assert resp.json() == {
        "detail": "Entre para confirmar seu WhatsApp e ativar este aviso.",
        "field": "auth",
        "auth_required": True,
    }
    assert resp["Cache-Control"] == "private, no-store, max-age=0"
    assert not StockAlertSubscription.objects.filter(sku=p.sku).exists()
    assert client.session.get("stock_alert_subscriptions") in (None, [])
    assert client.get(path).status_code == 404


def test_endpoint_retry_after_lost_response_recovers_same_session_capability(client):
    product = _publish(sku="SKU-SUBSCRIBE-LOST-RESPONSE")
    path = f"/api/v1/availability/{product.sku}/notify/"
    _authenticate(client, ref="CUS-SUBSCRIBE-LOST-RESPONSE")

    first = client.post(path, {"adult_declared": True}, REMOTE_ADDR="203.0.113.200")
    repeated = client.post(path, {"adult_declared": True}, REMOTE_ADDR="203.0.113.200")

    assert first.status_code == repeated.status_code == 200
    assert first.json()["management_url"] == repeated.json()["management_url"]
    assert StockAlertSubscription.objects.filter(sku=product.sku).count() == 1
    assert client.get(path).status_code == 200


def test_anonymous_repeat_from_other_session_cannot_take_over_existing_subscription(client):
    from django.test import Client

    product = _publish(sku="SKU-SUBSCRIBE-CROSS-SESSION")
    path = f"/api/v1/availability/{product.sku}/notify/"
    sub = stock_alerts.subscribe(product.sku, phone=PHONE, adult_declared=True)
    other_session = Client()

    repeated = other_session.post(path, {"phone": PHONE}, REMOTE_ADDR="203.0.113.211")

    assert repeated.status_code == 401
    assert repeated.json()["auth_required"] is True
    assert other_session.session.get("stock_alert_subscriptions") in (None, [])
    assert other_session.get(path).status_code == 404

    cancelled = other_session.delete(
        path,
        data={"subscription_ref": str(sub.ref)},
        content_type="application/json",
    )
    assert cancelled.status_code == 404
    paused = other_session.patch(
        path,
        data={"subscription_ref": str(sub.ref), "action": "pause"},
        content_type="application/json",
    )
    assert paused.status_code == 404
    sub.refresh_from_db()
    assert sub.is_active


def test_anonymous_repeat_from_other_session_does_not_resume_paused_subscription(client):
    from django.test import Client

    product = _publish(sku="SKU-SUBSCRIBE-CROSS-SESSION-PAUSED")
    path = f"/api/v1/availability/{product.sku}/notify/"
    sub = stock_alerts.subscribe(product.sku, phone=PHONE, adult_declared=True)
    assert stock_alerts.set_paused(sub.ref, paused=True, sku=sub.sku, phone=PHONE)

    other_session = Client()
    repeated = other_session.post(path, {"phone": PHONE}, REMOTE_ADDR="203.0.113.213")

    assert repeated.status_code == 401
    assert repeated.json()["auth_required"] is True
    sub.refresh_from_db()
    assert sub.paused_at is not None


def test_anonymous_reload_recovers_exact_session_management_link(client):
    product = _publish(sku="SKU-MANAGE-SESSION")
    path = f"/api/v1/availability/{product.sku}/notify/"
    sub = stock_alerts.subscribe(product.sku, phone=PHONE, adult_declared=True)
    _mark_legacy_session(client, sub)

    recovered = client.get(path)

    assert recovered.status_code == 200
    assert recovered["Cache-Control"] == "private, no-store, max-age=0"
    assert recovered["Referrer-Policy"] == "no-referrer"
    assert recovered.json()["active"] is True
    assert recovered.json()["management_url"] == stock_alerts.management_url(sub)
    body = recovered.content.decode()
    assert PHONE not in body
    assert str(sub.ref) not in body


def test_session_management_link_cannot_be_recovered_by_ref_or_wrong_owner(client):
    from django.test import Client

    product = _publish(sku="SKU-MANAGE-SESSION-IDOR")
    sub = stock_alerts.subscribe(product.sku, phone=PHONE, adult_declared=True)
    other_device = Client()
    session = other_device.session
    session["stock_alert_subscriptions"] = [
        {
            "ref": str(sub.ref),
            "sku": product.sku,
            "alert_type": StockAlertSubscription.AlertType.STOCK_BACK,
            "contact_phone": "+5543999999999",
        }
    ]
    session.save()

    recovered = other_device.get(f"/api/v1/availability/{product.sku}/notify/")

    assert recovered.status_code == 404
    assert recovered["Cache-Control"] == "private, no-store, max-age=0"
    assert stock_alerts.management_url(sub) not in recovered.content.decode()

    session = other_device.session
    session["stock_alert_subscriptions"][0]["ref"] = "not-a-uuid"
    session.save()
    assert other_device.get(f"/api/v1/availability/{product.sku}/notify/").status_code == 404


def test_endpoint_anonymous_does_not_normalize_or_persist_typed_phone(client):
    p = _publish(sku="SKU-LEGACY-PHONE")
    resp = client.post(f"/api/v1/availability/{p.sku}/notify/", {"phone": "(43) 9840-4900"})
    assert resp.status_code == 401
    assert resp.json()["auth_required"] is True
    assert not StockAlertSubscription.objects.filter(sku=p.sku).exists()
    assert client.session.get("stock_alert_subscriptions") in (None, [])
    assert "stock_alert_skus" not in client.session


def test_endpoint_anonymous_without_phone_also_routes_to_auth(client):
    p = _publish()
    resp = client.post(f"/api/v1/availability/{p.sku}/notify/", {})
    assert resp.status_code == 401
    assert resp.json()["auth_required"] is True
    assert not StockAlertSubscription.objects.filter(sku=p.sku).exists()


def test_authenticated_subscribe_uses_canonical_account_phone_not_request_body(client):
    product = _publish(sku="SKU-AUTH-CANONICAL-PHONE")
    customer = _authenticate(client)

    response = client.post(
        f"/api/v1/availability/{product.sku}/notify/",
        {"phone": "+5543999990099", "adult_declared": True},
    )

    assert response.status_code == 200
    assert response.json()["management_url"].startswith("/gerenciar-aviso#")
    sub = StockAlertSubscription.objects.get(sku=product.sku)
    assert sub.customer_ref == customer.ref
    assert sub.contact_phone == PHONE


def test_authenticated_subscribe_requires_explicit_adult_declaration(client):
    product = _publish(sku="SKU-ADULT-DECLARATION")
    _authenticate(client, ref="CUS-ADULT-DECLARATION")

    response = client.post(f"/api/v1/availability/{product.sku}/notify/", {})

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Confirme que você tem 18 anos ou mais para receber este aviso.",
        "field": "adult_declared",
    }
    assert not StockAlertSubscription.objects.filter(sku=product.sku).exists()


def test_authenticated_known_minor_gets_clear_non_actionable_age_response(client):
    product = _publish(sku="SKU-API-KNOWN-MINOR")
    customer = _authenticate(client, ref="CUS-API-KNOWN-MINOR")
    today = timezone.localdate()
    customer.birthday = today.replace(year=today.year - 17)
    customer.save(update_fields=["birthday"])

    response = client.post(
        f"/api/v1/availability/{product.sku}/notify/",
        {"adult_declared": True},
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": (
            "Este aviso está disponível somente para pessoas com 18 anos ou mais. "
            "A data de nascimento da sua conta indica idade inferior a 18 anos."
        ),
        "field": "birthday",
    }
    assert not StockAlertSubscription.objects.filter(sku=product.sku).exists()


def test_endpoint_anonymous_can_cancel_only_its_session_subscription(client):
    product = _publish(sku="SKU-CANCEL")
    sub = stock_alerts.subscribe(product.sku, phone=PHONE, adult_declared=True)
    _mark_legacy_session(client, sub)
    subscription_ref = str(sub.ref)

    response = client.delete(
        f"/api/v1/availability/{product.sku}/notify/",
        data={"subscription_ref": subscription_ref},
        content_type="application/json",
    )

    assert response.status_code == 200
    sub = StockAlertSubscription.objects.get(ref=subscription_ref)
    assert sub.revoked_at is not None
    assert client.session["stock_alert_subscriptions"] == []


def test_endpoint_does_not_cancel_a_ref_outside_anonymous_session(client):
    product = _publish(sku="SKU-CANCEL-IDOR")
    sub = stock_alerts.subscribe(product.sku, phone=PHONE, adult_declared=True)

    response = client.delete(
        f"/api/v1/availability/{product.sku}/notify/",
        data={"subscription_ref": str(sub.ref)},
        content_type="application/json",
    )

    assert response.status_code == 404
    sub.refresh_from_db()
    assert sub.revoked_at is None


def test_endpoint_404_for_unknown_sku(client):
    resp = client.post("/api/v1/availability/NOPE/notify/", {"phone": PHONE})
    assert resp.status_code == 404


def test_anonymous_session_marker_remains_after_a_delivery(rf):
    from django.contrib.sessions.middleware import SessionMiddleware

    from shopman.storefront.presentation.catalog import notify_subscribed_skus

    sub = stock_alerts.subscribe("SKU-PENDING-MARK", phone=PHONE, adult_declared=True)
    request = rf.get("/")
    SessionMiddleware(lambda request: None).process_request(request)
    request.session["stock_alert_skus"] = ["SKU-LEGACY-MARK"]
    request.session["stock_alert_subscriptions"] = [
        {
            "ref": str(sub.ref),
            "sku": "SKU-PENDING-MARK",
            "alert_type": StockAlertSubscription.AlertType.STOCK_BACK,
            "contact_phone": PHONE,
        }
    ]

    assert notify_subscribed_skus(request) == {"SKU-PENDING-MARK"}

    sub.notified_at = timezone.now()
    sub.save(update_fields=["notified_at"])

    assert notify_subscribed_skus(request) == {"SKU-PENDING-MARK"}


# ── trigger (Move receiver) ─────────────────────────────────────────


def test_move_receiver_schedules_notify_for_pending_sku():
    from shopman.storefront import handlers

    stock_alerts.subscribe("SKU-MOVE", phone=PHONE, adult_declared=True)
    fake = _move("SKU-MOVE", kind="buy")
    with (
        patch("shopman.storefront.services.stock_alerts.notify_back_in_stock") as nb,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_move_for_stock_alerts(sender=None, instance=fake)
    nb.assert_called_once_with("SKU-MOVE", source_ref="42")


def test_move_receiver_skips_when_no_pending_subscription():
    from shopman.storefront import handlers

    fake = _move("SKU-NO-WAITERS")
    with (
        patch("shopman.storefront.services.stock_alerts.notify_back_in_stock") as nb,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_move_for_stock_alerts(sender=None, instance=fake)
    nb.assert_not_called()


@pytest.mark.parametrize(
    "kind",
    ["synthetic", "future"],
)
def test_move_receiver_skips_synthetic_refresh_and_future_planning(kind):
    from shopman.storefront import handlers

    # Compute tomorrow at execution: collection can happen before local midnight.
    move = (_move("SKU-SYNTHETIC", metadata={"suppress_notifications": True}) if kind == "synthetic"
            else _move("SKU-FUTURE", target_date=timezone.localdate() + timedelta(days=1)))

    stock_alerts.subscribe(move.quant.sku, phone=PHONE, adult_declared=True)
    with (
        patch("shopman.storefront.services.stock_alerts.notify_back_in_stock") as nb,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_move_for_stock_alerts(sender=None, instance=move)
    nb.assert_not_called()


def test_move_receiver_reconciles_a_debit_to_close_the_availability_cycle():
    from shopman.storefront import handlers

    stock_alerts.subscribe("SKU-QC", phone=PHONE, adult_declared=True)
    with (
        patch("shopman.storefront.services.stock_alerts.notify_back_in_stock") as nb,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_move_for_stock_alerts(sender=None, instance=_move("SKU-QC", delta=-1))
    nb.assert_called_once_with("SKU-QC", source_ref="42")


def test_move_receiver_never_calls_a_qc_correction_a_new_arrival():
    from shopman.storefront import handlers

    stock_alerts.subscribe("SKU-QC", phone=PHONE, adult_declared=True)
    move = _move(
        "SKU-QC",
        delta=1,
        kind="waste",
        metadata={"operation": "production_qc_correction", "direction": "loss_recovery"},
    )
    with (
        patch("shopman.storefront.services.stock_alerts.notify_back_in_stock") as nb,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_move_for_stock_alerts(sender=None, instance=move)
    nb.assert_not_called()


# ── trigger (fornada) ───────────────────────────────────────────────


def test_bake_receiver_records_pending_occurrence_until_quality_review():
    """A fornada cria o fato pendente sem autorizar comunicação ao cliente."""
    from shopman.storefront import handlers

    stock_alerts.subscribe("SKU-BAKE", phone=PHONE, alert_type="production_ready", adult_declared=True)
    with (
        patch("shopman.storefront.services.stock_alerts.record_bake_pending") as pending,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_production_finished_for_stock_alerts(
            sender=None, product_ref="SKU-BAKE", date=None, action="finished", work_order=None
        )
    pending.assert_called_once_with("SKU-BAKE", source_ref="")


def test_quality_review_receiver_releases_the_same_bake_occurrence():
    from shopman.storefront import handlers

    stock_alerts.subscribe("SKU-BAKE", phone=PHONE, alert_type="production_ready", adult_declared=True)
    work_order = MagicMock(ref="wo-reviewed")
    with (
        patch("shopman.storefront.services.stock_alerts.review_bake_ready") as reviewed,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_production_finished_for_stock_alerts(
            sender=None,
            product_ref="SKU-BAKE",
            date=None,
            action="quality_reviewed",
            work_order=work_order,
        )
    reviewed.assert_called_once_with("SKU-BAKE", source_ref="wo-reviewed")


def test_bake_receiver_ignores_other_production_actions():
    from shopman.storefront import handlers

    stock_alerts.subscribe("SKU-BAKE", phone=PHONE, alert_type="production_ready", adult_declared=True)
    with (
        patch("shopman.storefront.services.stock_alerts.record_bake_pending") as pending,
        patch("shopman.storefront.services.stock_alerts.review_bake_ready") as reviewed,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_production_finished_for_stock_alerts(
            sender=None, product_ref="SKU-BAKE", date=None, action="started", work_order=None
        )
        _deliver_queued()
    pending.assert_not_called()
    reviewed.assert_not_called()


def test_stock_back_subscriber_is_not_woken_by_a_bake():
    """Os dois gatilhos são independentes: quem espera reposição não recebe fornada."""
    from shopman.storefront import handlers

    stock_alerts.subscribe("SKU-BAKE", phone=PHONE, adult_declared=True)  # stock_back (default)
    with (
        patch("shopman.storefront.services.stock_alerts.record_bake_pending") as pending,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_production_finished_for_stock_alerts(
            sender=None, product_ref="SKU-BAKE", date=None, action="finished", work_order=None
        )
    pending.assert_not_called()


def test_both_alert_types_coexist_for_the_same_shopper():
    back = stock_alerts.subscribe("SKU-BOTH", phone=PHONE, adult_declared=True)
    bake = stock_alerts.subscribe("SKU-BOTH", phone=PHONE, alert_type="production_ready", adult_declared=True)
    assert back.pk != bake.pk
    assert bake.alert_type == "production_ready"


def test_endpoint_accepts_the_bake_alert_type(client):
    p = _publish(sku="SKU-BAKE-API")
    _authenticate(client, ref="CUS-BAKE-API")
    resp = client.post(
        f"/api/v1/availability/{p.sku}/notify/",
        {"alert_type": "production_ready", "adult_declared": True},
    )
    assert resp.status_code == 200
    sub = StockAlertSubscription.objects.get(sku=p.sku)
    assert sub.alert_type == "production_ready"


def test_endpoint_rejects_an_unknown_alert_type(client):
    p = _publish(sku="SKU-BAD-TYPE")
    resp = client.post(
        f"/api/v1/availability/{p.sku}/notify/",
        {"phone": PHONE, "alert_type": "telepatia"},
    )
    assert resp.status_code == 400
    assert resp.json()["field"] == "alert_type"


# ── o eixo do aviso: quem decide é o servidor ────────────────────────


def test_bread_subscribes_to_the_oven_not_to_the_shelf():
    """O caso do Pablo: o sino de um pão entra na fila da FORNADA.

    A loja manda só o telefone. Antes, sem ``alert_type`` no corpo, todo mundo
    caía em ``stock_back`` e a fila de fornada nascia vazia para sempre.
    """
    _publish(sku="BF", is_batch_produced=True)
    sub = stock_alerts.subscribe("BF", phone=PHONE, adult_declared=True)
    assert sub.alert_type == StockAlertSubscription.AlertType.PRODUCTION_READY


def test_shelf_item_subscribes_to_the_shelf():
    _publish(sku="AG")  # água: chega por recebimento, não sai do forno
    sub = stock_alerts.subscribe("AG", phone=PHONE, adult_declared=True)
    assert sub.alert_type == StockAlertSubscription.AlertType.STOCK_BACK


def test_an_active_recipe_is_enough_to_make_it_an_oven_item():
    """A flag do gestor não é preenchida na prática; a receita ativa é a prova.

    No banco vivo do alpha (05/09/2026) todo produto tem ``is_batch_produced``
    em ``False``, pães inclusive. Derivar só pela flag entregaria uma correção
    que nunca dispara.
    """
    from decimal import Decimal

    from shopman.craftsman.models import Recipe

    _publish(sku="CI")
    Recipe.objects.create(
        ref="ciabatta",
        name="Ciabatta",
        output_sku="CI",
        batch_size=Decimal("10"),
        is_active=True,
    )
    assert stock_alerts.subscribe("CI", phone=PHONE, adult_declared=True).alert_type == "production_ready"


def test_unknown_sku_falls_back_to_the_shelf():
    """Na dúvida, prateleira: é o eixo com mais caminhos de chegada."""
    assert stock_alerts.subscribe("SKU-GHOST", phone=PHONE, adult_declared=True).alert_type == "stock_back"


def test_explicit_alert_type_still_wins():
    _publish(sku="BF-EXPLICIT", is_batch_produced=True)
    sub = stock_alerts.subscribe("BF-EXPLICIT", phone=PHONE, alert_type="stock_back", adult_declared=True)
    assert sub.alert_type == "stock_back"


def test_endpoint_derives_the_oven_axis_without_the_front_asking(client):
    """A tela continua dizendo só "avise-me sobre este produto"."""
    p = _publish(sku="BF-API", is_batch_produced=True)
    _authenticate(client, ref="CUS-OVEN-API")
    resp = client.post(
        f"/api/v1/availability/{p.sku}/notify/",
        {"adult_declared": True},
    )
    assert resp.status_code == 200
    assert StockAlertSubscription.objects.get(sku=p.sku).alert_type == "production_ready"
    assert client.session["stock_alert_subscriptions"][0]["alert_type"] == "production_ready"


# ── uma fornada, UMA mensagem ────────────────────────────────────────


def test_a_bake_waits_for_qc_and_does_not_send_twice_to_the_same_person():
    """A fornada acorda os DOIS receptores; a revisão libera uma mensagem.

    O ``finish`` escreve o ledger (``kind=make``), então nasce um ``Move`` no
    mesmo instante em que ``production_changed`` dispara. Com o eixo certo, o
    receptor de estoque não acha ``stock_back`` pendente e se cala.
    """
    from shopman.storefront import handlers

    _publish(sku="BF-BAKE", is_batch_produced=True)
    stock_alerts.subscribe("BF-BAKE", phone=PHONE, adult_declared=True)

    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True, 6)),
        patch(
            "shopman.shop.services.quality.reviewed_saleable_quantity",
            return_value=Decimal("6"),
        ),
        patch("shopman.shop.notifications.notify", return_value=MagicMock(success=True)) as nf,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_move_for_stock_alerts(sender=None, instance=_move("BF-BAKE", kind="make"))
        handlers.on_production_finished_for_stock_alerts(
            sender=None,
            product_ref="BF-BAKE",
            date=None,
            action="finished",
            work_order=None,
        )
        _deliver_queued()
        assert nf.call_count == 0
        handlers.on_production_finished_for_stock_alerts(
            sender=None,
            product_ref="BF-BAKE",
            date=None,
            action="quality_reviewed",
            work_order=None,
        )
        _deliver_queued()

    assert nf.call_count == 1
    assert nf.call_args.kwargs["event"] == "production_ready"


def test_a_production_move_never_serves_the_oven_queue():
    """A rede de segurança fica DESLIGADA na produção.

    Ligada ali, o ``Move`` chegaria primeiro (os dois ``on_commit`` correm em
    ordem de registro) e o "saiu do forno" viraria "chegou ao estoque" — a
    mensagem certa trocada pela errada, sem ninguém perceber.
    """
    from shopman.storefront import handlers

    _publish(sku="BF-MAKE", is_batch_produced=True)
    stock_alerts.subscribe("BF-MAKE", phone=PHONE, adult_declared=True)

    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)),
        patch("shopman.shop.notifications.notify", return_value=MagicMock(success=True)) as nf,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_move_for_stock_alerts(sender=None, instance=_move("BF-MAKE", kind="make"))

    nf.assert_not_called()
    assert StockAlertSubscription.objects.get(sku="BF-MAKE").is_pending


def test_one_event_only_targets_its_matching_subscription():
    stock_alerts.subscribe("SKU-LEGACY-BOTH", phone=PHONE, alert_type="stock_back", adult_declared=True)
    stock_alerts.subscribe("SKU-LEGACY-BOTH", phone=PHONE, alert_type="production_ready", adult_declared=True)

    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)),
        patch("shopman.shop.notifications.notify", return_value=MagicMock(success=True)) as nf,
    ):
        notified = stock_alerts.notify_back_in_stock("SKU-LEGACY-BOTH", also_bake_waiters=True)
        _deliver_queued()

    assert notified == 1
    assert nf.call_count == 1
    assert (
        StockAlertSubscription.objects.filter(
            sku="SKU-LEGACY-BOTH", alert_type="production_ready", notified_at__isnull=True
        ).count()
        == 1
    )


# ── rede de segurança: estoque que chega por fora da produção ────────


def test_a_non_production_arrival_does_not_impersonate_a_bake():
    from shopman.storefront import handlers

    _publish(sku="BF-RECEBIDO", is_batch_produced=True)
    stock_alerts.subscribe("BF-RECEBIDO", phone=PHONE, adult_declared=True)

    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True, 3)),
        patch("shopman.shop.notifications.notify", return_value=MagicMock(success=True)) as nf,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_move_for_stock_alerts(sender=None, instance=_move("BF-RECEBIDO", kind="adjust"))

    nf.assert_not_called()
    assert StockAlertSubscription.objects.get(sku="BF-RECEBIDO").is_active
    assert not StockAlertOccurrence.objects.exists()


# ── persistent occurrence contract ─────────────────────────────────────────


def test_subscription_delivers_again_only_after_a_new_stock_cycle():
    sub = stock_alerts.subscribe("SKU-CYCLE", phone=PHONE, adult_declared=True)
    states = [
        _state(True, 2),
        _state(True, 2),
        _state(True, 2),
        _state(True, 2),
        _state(False),
        _state(True, 3),
        _state(True, 3),
        _state(True, 3),
    ]
    with (
        patch("shopman.storefront.services.sku_state.resolve", side_effect=states),
        patch(
            "shopman.shop.notifications.notify",
            return_value=NotificationResult(success=True, message_id="provider-accepted"),
        ) as notify,
    ):
        assert stock_alerts.notify_back_in_stock(sub.sku, source_ref="move-1") == 1
        _deliver_queued()
        assert stock_alerts.notify_back_in_stock(sub.sku, source_ref="move-1-retry") == 0
        assert stock_alerts.notify_back_in_stock(sub.sku, source_ref="move-2-debit") == 0
        assert stock_alerts.notify_back_in_stock(sub.sku, source_ref="move-3") == 1
        _deliver_queued()

    assert notify.call_count == 2
    assert StockAlertOccurrence.objects.filter(sku=sub.sku).count() == 2
    assert StockAlertDelivery.objects.filter(status="accepted").count() == 2
    sub.refresh_from_db()
    assert sub.is_active


def test_stock_cycle_closes_after_last_subscription_is_cancelled():
    sub = stock_alerts.subscribe("SKU-CYCLE-CANCELLED", phone=PHONE, adult_declared=True)
    with patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True, 2)):
        assert stock_alerts.notify_back_in_stock(sub.sku, source_ref="move-open") == 1
    assert stock_alerts.revoke(sub.ref, sku=sub.sku, phone=PHONE)

    from shopman.storefront import handlers

    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(False)),
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_move_for_stock_alerts(sender=None, instance=_move(sub.sku, delta=-1))

    first = StockAlertOccurrence.objects.get(sku=sub.sku)
    assert first.closed_at is not None
    replacement = stock_alerts.subscribe(sub.sku, phone=PHONE, adult_declared=True)
    with patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True, 3)):
        assert stock_alerts.notify_back_in_stock(replacement.sku, source_ref="move-new-cycle") == 1
    assert StockAlertOccurrence.objects.filter(sku=sub.sku).count() == 2


def test_replayed_bake_source_has_one_occurrence_and_one_delivery():
    sub = stock_alerts.subscribe("SKU-BAKE-REPLAY", phone=PHONE, alert_type="production_ready", adult_declared=True)
    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True, 5)),
        patch(
            "shopman.shop.services.quality.reviewed_saleable_quantity",
            return_value=Decimal("5"),
        ),
        patch("shopman.shop.notifications.notify", return_value=NotificationResult(success=True)) as notify,
    ):
        assert stock_alerts.notify_bake_ready(sub.sku, source_ref="work-order-77") == 1
        _deliver_queued()
        assert stock_alerts.notify_bake_ready(sub.sku, source_ref="work-order-77") == 0

    assert notify.call_count == 1
    assert StockAlertOccurrence.objects.count() == 1
    assert StockAlertDelivery.objects.count() == 1


def test_pause_after_queue_is_rechecked_before_provider_call():
    sub = stock_alerts.subscribe("SKU-PAUSE", phone=PHONE, adult_declared=True)
    with patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)):
        assert stock_alerts.notify_back_in_stock(sub.sku, source_ref="move-pause") == 1
    assert stock_alerts.set_paused(sub.ref, paused=True, sku=sub.sku, phone=PHONE)

    with patch("shopman.shop.notifications.notify") as notify:
        _deliver_queued()

    notify.assert_not_called()
    assert StockAlertDelivery.objects.get().status == "suppressed"
    assert StockAlertSubscription.objects.get(pk=sub.pk).paused_at is not None


def test_known_minor_birthday_added_after_queue_suppresses_before_provider_call():
    today = timezone.localdate()
    customer = Customer.objects.create(
        ref="CUS-LATE-KNOWN-MINOR",
        first_name="Ana",
        phone=PHONE,
        birthday=today.replace(year=today.year - 30),
    )
    sub = stock_alerts.subscribe("SKU-LATE-KNOWN-MINOR", customer=customer, adult_declared=True)
    with patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)):
        assert stock_alerts.notify_back_in_stock(sub.sku, source_ref="move-known-minor") == 1
    Customer.objects.filter(pk=customer.pk).update(
        birthday=today.replace(year=today.year - 17)
    )

    with patch("shopman.shop.notifications.notify") as notify:
        _deliver_queued()

    notify.assert_not_called()
    delivery = StockAlertDelivery.objects.get(subscription=sub)
    assert delivery.status == StockAlertDelivery.Status.SUPPRESSED
    assert delivery.last_error_code == "known_minor"


def test_known_minor_is_rechecked_again_at_provider_boundary():
    customer = Customer.objects.create(
        ref="CUS-PROVIDER-AGE-BOUNDARY",
        first_name="Ana",
        phone=PHONE,
    )
    sub = stock_alerts.subscribe("SKU-PROVIDER-AGE-BOUNDARY", customer=customer, adult_declared=True)
    with patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)):
        assert stock_alerts.notify_back_in_stock(sub.sku, source_ref="move-age-boundary") == 1

    with (
        patch(
            "shopman.shop.services.marketing_age.customer_is_known_minor",
            side_effect=[False, True],
        ),
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)),
        patch("shopman.shop.notifications.notify") as notify,
    ):
        _deliver_queued()

    notify.assert_not_called()
    delivery = StockAlertDelivery.objects.get(subscription=sub)
    assert delivery.status == StockAlertDelivery.Status.SUPPRESSED
    assert delivery.last_error_code == "known_minor_before_send"


def test_age_lookup_failure_retries_without_contacting_provider():
    customer = Customer.objects.create(
        ref="CUS-AGE-LOOKUP-FAILURE",
        first_name="Ana",
        phone=PHONE,
    )
    sub = stock_alerts.subscribe("SKU-AGE-LOOKUP-FAILURE", customer=customer, adult_declared=True)
    with patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)):
        assert stock_alerts.notify_back_in_stock(sub.sku, source_ref="move-age-failure") == 1

    with (
        patch(
            "shopman.shop.services.marketing_age.customer_is_known_minor",
            side_effect=RuntimeError("age source unavailable"),
        ),
        patch("shopman.shop.notifications.notify") as notify,
        pytest.raises(Exception, match="age_check_failed"),
    ):
        _deliver_queued()

    notify.assert_not_called()
    delivery = StockAlertDelivery.objects.get(subscription=sub)
    assert delivery.status == StockAlertDelivery.Status.QUEUED


def test_unavailable_at_provider_boundary_suppresses_delivery():
    sub = stock_alerts.subscribe("SKU-BOUNDARY", phone=PHONE, adult_declared=True)
    with patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)):
        assert stock_alerts.notify_back_in_stock(sub.sku, source_ref="move-boundary") == 1

    with (
        patch(
            "shopman.storefront.services.sku_state.resolve",
            side_effect=[_state(True), _state(False)],
        ),
        patch("shopman.shop.notifications.notify") as notify,
    ):
        _deliver_queued()

    notify.assert_not_called()
    delivery = StockAlertDelivery.objects.get()
    assert delivery.status == "suppressed"
    assert delivery.last_error_code == "unavailable_at_provider_boundary"


def test_lost_provider_response_is_not_retried_blindly(django_capture_on_commit_callbacks):
    sub = stock_alerts.subscribe("SKU-UNKNOWN", phone=PHONE, adult_declared=True)
    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)),
        patch(
            "shopman.shop.notifications.notify",
            return_value=NotificationResult(success=False, error="acceptance_unconfirmed", outcome_unknown=True),
        ) as notify,
        patch("shopman.shop.services.observability.create_operator_alert") as alert,
    ):
        stock_alerts.notify_back_in_stock(sub.sku, source_ref="move-unknown")
        with django_capture_on_commit_callbacks(execute=True):
            _deliver_queued()
        _deliver_queued()

    assert notify.call_count == 1
    assert StockAlertDelivery.objects.get().status == "indeterminate"
    alert.assert_called_once()


def test_stale_worker_claim_is_indeterminate_and_alerted_without_resend():
    sub = stock_alerts.subscribe("SKU-STALE", phone=PHONE, adult_declared=True)
    with patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)):
        stock_alerts.notify_back_in_stock(sub.sku, source_ref="move-stale")
    delivery = StockAlertDelivery.objects.get()
    delivery.status = StockAlertDelivery.Status.CLAIMED
    delivery.claimed_at = timezone.now() - timedelta(minutes=11)
    delivery.save(update_fields=["status", "claimed_at", "updated_at"])

    with (
        patch("shopman.shop.notifications.notify") as notify,
        patch("shopman.shop.services.observability.create_operator_alert") as alert,
    ):
        StockAlertDeliveryHandler().handle(
            message=MagicMock(payload={"delivery_id": delivery.pk}),
            ctx={},
        )

    notify.assert_not_called()
    delivery.refresh_from_db()
    assert delivery.status == "indeterminate"
    assert delivery.last_error_code == "stale_claim_before_retry"
    alert.assert_called_once()


def test_delivery_sla_command_alerts_with_counts_and_runbook():
    sub = stock_alerts.subscribe("SKU-SLA", phone=PHONE, adult_declared=True)
    with patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)):
        stock_alerts.notify_back_in_stock(sub.sku, source_ref="move-sla")
    StockAlertDelivery.objects.update(updated_at=timezone.now() - timedelta(minutes=11))
    output = StringIO()

    with patch("shopman.shop.services.observability.create_operator_alert") as alert:
        call_command("check_stock_alert_delivery_sla", minutes=10, stdout=output)

    assert "stuck=1" in output.getvalue()
    message = alert.call_args.kwargs["message"]
    assert "queued" in message
    assert "docs/runbooks/stock-alert-delivery.md" in message
    assert PHONE not in message


def test_partial_failure_keeps_independent_receipts_and_same_occurrence():
    stock_alerts.subscribe("SKU-PARTIAL", phone=PHONE, adult_declared=True)
    stock_alerts.subscribe("SKU-PARTIAL", phone="+5543999990002", adult_declared=True)
    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)),
        patch(
            "shopman.shop.notifications.notify",
            side_effect=[
                NotificationResult(success=True, message_id="ok-1"),
                NotificationResult(success=False, error="provider_503"),
            ],
        ),
    ):
        assert stock_alerts.notify_back_in_stock("SKU-PARTIAL", source_ref="move-partial") == 2
        with pytest.raises(Exception, match="provider rejected"):
            _deliver_queued()

    assert StockAlertOccurrence.objects.count() == 1
    assert set(StockAlertDelivery.objects.values_list("status", flat=True)) == {
        "accepted",
        "retryable",
    }


def test_anonymous_can_pause_and_resume_the_exact_session_subscription(client):
    product = _publish(sku="SKU-PAUSE-API")
    sub = stock_alerts.subscribe(product.sku, phone=PHONE, adult_declared=True)
    _mark_legacy_session(client, sub)
    subscription_ref = str(sub.ref)
    path = f"/api/v1/availability/{product.sku}/notify/"

    paused = client.patch(
        path,
        data={"subscription_ref": subscription_ref, "action": "pause"},
        content_type="application/json",
    )
    resumed = client.patch(
        path,
        data={"subscription_ref": subscription_ref, "action": "resume"},
        content_type="application/json",
    )

    assert paused.status_code == 200 and paused.json()["active"] is False
    assert resumed.status_code == 200 and resumed.json()["active"] is True
    assert StockAlertSubscription.objects.get(ref=subscription_ref).is_active


def test_former_expiry_does_not_disable_or_prevent_resuming(client):
    product = _publish(sku="SKU-EXPIRED-API")
    sub = stock_alerts.subscribe(product.sku, phone=PHONE, adult_declared=True)
    _mark_legacy_session(client, sub)
    subscription_ref = str(sub.ref)
    StockAlertSubscription.objects.filter(ref=subscription_ref).update(
        paused_at=timezone.now(),
        expires_at=timezone.now() - timedelta(seconds=1),
    )

    response = client.patch(
        f"/api/v1/availability/{product.sku}/notify/",
        data={"subscription_ref": subscription_ref, "action": "resume"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert StockAlertSubscription.objects.get(ref=subscription_ref).is_active


def test_verified_subscription_remains_eligible_after_more_than_30_days():
    sub = stock_alerts.subscribe("SKU-PERSISTENT-31-DAYS", phone=PHONE, adult_declared=True)
    StockAlertSubscription.objects.filter(pk=sub.pk).update(
        subscribed_at=timezone.now() - timedelta(days=31),
        expires_at=timezone.now() - timedelta(days=1),
    )

    sub.refresh_from_db()
    assert sub.is_active
    assert StockAlertSubscription.objects.active().filter(pk=sub.pk).exists()
    with patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)):
        assert stock_alerts.notify_back_in_stock(sub.sku, source_ref="move-after-31-days") == 1

    assert StockAlertDelivery.objects.get(subscription=sub).status == StockAlertDelivery.Status.QUEUED


def _management_token(sub) -> str:
    return urlsplit(stock_alerts.management_url(sub)).fragment


def _management_headers(sub) -> dict:
    return {"HTTP_X_STOCK_ALERT_CAPABILITY": _management_token(sub)}


def test_management_capability_works_cross_device_and_get_is_read_only(client):
    from django.test import Client

    product = _publish(sku="SKU-MANAGE-CROSS-DEVICE")
    sub = stock_alerts.subscribe(product.sku, phone=PHONE, adult_declared=True)
    token = _management_token(sub)
    other_device = Client()

    response = other_device.get(
        "/api/v1/stock-alert/manage/",
        HTTP_X_STOCK_ALERT_CAPABILITY=token,
    )

    assert response.status_code == 200
    assert response["Cache-Control"] == "private, no-store, max-age=0"
    assert response["Referrer-Policy"] == "no-referrer"
    assert response.json()["state"] == "active"
    body = response.content.decode()
    assert PHONE not in body
    assert str(sub.ref) not in body
    assert token not in body
    sub.refresh_from_db()
    assert sub.paused_at is None and sub.revoked_at is None


@pytest.mark.parametrize("candidate", ["simple-ref", "altered-token"])
def test_management_rejects_simple_ref_and_altered_token(client, candidate):
    sub = stock_alerts.subscribe("SKU-MANAGE-TAMPER", phone=PHONE, adult_declared=True)
    management_token = _management_token(sub)
    altered_token = f"{management_token[:-1]}{'A' if management_token[-1] != 'A' else 'B'}"
    token = str(sub.ref) if candidate == "simple-ref" else altered_token

    response = client.get(
        "/api/v1/stock-alert/manage/",
        HTTP_X_STOCK_ALERT_CAPABILITY=token,
    )

    assert response.status_code == 404
    sub.refresh_from_db()
    assert sub.is_active


@pytest.mark.parametrize(
    ("method", "body", "reason"),
    [
        ("patch", {"action": "pause"}, "subscription_paused"),
        ("delete", None, "subscription_cancelled"),
    ],
)
def test_capability_pause_or_cancel_immediately_suppresses_enqueued_delivery(
    client,
    method,
    body,
    reason,
):
    sub = stock_alerts.subscribe(f"SKU-MANAGE-{method.upper()}", phone=PHONE, adult_declared=True)
    with patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)):
        stock_alerts.notify_back_in_stock(sub.sku, source_ref=f"move-{method}")

    request = getattr(client, method)
    response = request(
        "/api/v1/stock-alert/manage/",
        data=body,
        content_type="application/json",
        **_management_headers(sub),
    )

    assert response.status_code == 200
    assert response.json()["suppressed_deliveries"] == 1
    delivery = StockAlertDelivery.objects.get(subscription=sub)
    assert delivery.status == StockAlertDelivery.Status.SUPPRESSED
    assert delivery.last_error_code == reason


def test_resume_applies_only_to_future_occurrences(client):
    sub = stock_alerts.subscribe("SKU-MANAGE-FUTURE", phone=PHONE, alert_type="production_ready", adult_declared=True)
    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True, 3)),
        patch("shopman.shop.services.quality.reviewed_saleable_quantity", return_value=Decimal("3")),
    ):
        assert stock_alerts.review_bake_ready(sub.sku, source_ref="bake-old") == 1
        client.patch(
            "/api/v1/stock-alert/manage/",
            data={"action": "pause"},
            content_type="application/json",
            **_management_headers(sub),
        )
        client.patch(
            "/api/v1/stock-alert/manage/",
            data={"action": "resume"},
            content_type="application/json",
            **_management_headers(sub),
        )
        assert stock_alerts.review_bake_ready(sub.sku, source_ref="bake-old") == 0
        assert stock_alerts.review_bake_ready(sub.sku, source_ref="bake-new") == 1

    statuses = list(StockAlertDelivery.objects.filter(subscription=sub).order_by("pk").values_list("status", flat=True))
    assert statuses == [StockAlertDelivery.Status.SUPPRESSED, StockAlertDelivery.Status.QUEUED]


def test_logged_in_account_cannot_control_another_customers_alert(client):
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    owner = Customer.objects.create(ref="CUS-ALERT-OWNER", first_name="Ana", phone=PHONE)
    stranger = Customer.objects.create(ref="CUS-ALERT-STRANGER", first_name="Bia", phone="+5543999990099")
    sub = stock_alerts.subscribe("SKU-ACCOUNT-IDOR", customer=owner, adult_declared=True)
    info = AuthCustomerInfo(uuid=stranger.uuid, name=stranger.name, phone=stranger.phone, email=None, is_active=True)
    user, _created = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")

    response = client.delete(
        f"/api/v1/availability/{sub.sku}/notify/",
        data={"subscription_ref": str(sub.ref)},
        content_type="application/json",
    )

    assert response.status_code == 404
    sub.refresh_from_db()
    assert sub.revoked_at is None


@pytest.mark.parametrize(
    "subscription_ref",
    [
        pytest.param("00000000-0000-0000-0000-000000000028", id="token-ending-A"),
        pytest.param("00000000-0000-0000-0000-000000000033", id="token-ending-Z"),
    ],
)
def test_capability_never_appears_in_application_logs(client, caplog, settings, subscription_ref):
    settings.SECRET_KEY = "stock-alert-log-test-only"
    sub = stock_alerts.subscribe("SKU-MANAGE-LOG", phone=PHONE, adult_declared=True)
    sub.ref = subscription_ref
    sub.save(update_fields=["ref"])
    token = _management_token(sub)
    # Flip a signature byte, then re-encode: always different and still canonical.
    altered = bytearray(urlsafe_b64decode(token))
    altered[-1] ^= 1
    altered_token = urlsafe_b64encode(altered).decode("ascii")

    assert client.get(
        "/api/v1/stock-alert/manage/",
        HTTP_X_STOCK_ALERT_CAPABILITY=token,
    ).status_code == 200
    assert client.get(
        "/api/v1/stock-alert/manage/",
        HTTP_X_STOCK_ALERT_CAPABILITY=altered_token,
    ).status_code == 404

    assert token not in caplog.text
