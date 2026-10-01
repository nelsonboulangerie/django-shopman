"""
Tests for Manychat integration: service + webhook.

Service tests (6 scenarios):
1. New subscriber → creates Customer + identifiers
2. Existing by Manychat ID → updates without duplicating
3. Existing by whatsapp_id → links Manychat ID
4. Existing by email → links Manychat ID
5. Partial data (only Manychat ID)
6. whatsapp_id normalization

Webhook tests (4 scenarios):
7. Valid POST with HMAC → 200 + customer created
8. Invalid/missing HMAC → 401
9. Duplicate event (replay) → 200 + "duplicate"
10. Partial data → 400
"""

import hashlib
import hmac
import json

import pytest
from django.db import IntegrityError
from django.test import RequestFactory
from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
from shopman.guestman.contrib.manychat.service import ManychatService
from shopman.guestman.contrib.manychat.views import ManychatWebhookView
from shopman.guestman.models import ContactPoint, Customer

# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

WEBHOOK_SECRET = "test-webhook-secret-12345"


@pytest.fixture(autouse=True)
def _enable_db(db):
    """Enable DB access for all tests."""


@pytest.fixture
def factory():
    return RequestFactory()


@pytest.fixture
def subscriber_data():
    """Full Manychat subscriber payload."""
    return {
        "id": "mc-subscriber-001",
        "first_name": "Maria",
        "last_name": "Silva",
        "whatsapp_id": "+5511999887766",
        "email": "maria@example.com",
    }


@pytest.fixture
def subscriber_partial():
    """Minimal Manychat subscriber (ID only)."""
    return {
        "id": "mc-subscriber-minimal",
    }


@pytest.fixture
def existing_customer(db):
    """Customer already in the database."""
    return Customer.objects.create(
        ref="EXISTING-001",
        first_name="João",
        last_name="Oliveira",
        email="joao@example.com",
        phone="5511988776655",
    )


# ═══════════════════════════════════════════════════════════════════
# Service Tests
# ═══════════════════════════════════════════════════════════════════


class TestManychatServiceSync:
    """ManychatService.sync_subscriber() scenarios."""

    def test_new_subscriber_creates_customer(self, subscriber_data):
        """Scenario 1: New subscriber → creates Customer + identifiers."""
        customer, created = ManychatService.sync_subscriber(subscriber_data)

        assert created is True
        assert customer.pk is not None
        assert customer.first_name == "Maria"
        assert customer.last_name == "Silva"
        assert customer.ref.startswith("MC-")
        assert customer.phone == "+5511999887766"

        # Verify Manychat identifier was created
        assert CustomerIdentifier.objects.filter(
            customer=customer,
            identifier_type=IdentifierType.MANYCHAT,
            identifier_value="mc-subscriber-001",
        ).exists()
        assert ContactPoint.objects.filter(
            customer=customer,
            type=ContactPoint.Type.PHONE,
            value_normalized="+5511999887766",
            is_verified=True,
        ).exists()
        assert ContactPoint.objects.filter(
            customer=customer,
            type=ContactPoint.Type.WHATSAPP,
            value_normalized="+5511999887766",
            is_verified=True,
        ).exists()

    def test_new_subscriber_rolls_back_when_identifier_link_fails(
        self,
        subscriber_data,
        monkeypatch,
    ):
        """Customer and identifiers are one atomic unit."""
        def failing_add_identifiers(*args, **kwargs):
            raise IntegrityError("forced identifier failure")

        monkeypatch.setattr(
            ManychatService,
            "_add_manychat_identifiers",
            failing_add_identifiers,
        )

        with pytest.raises(IntegrityError, match="forced identifier failure"):
            ManychatService.sync_subscriber(subscriber_data)

        hash_value = hashlib.md5(subscriber_data["id"].encode()).hexdigest()[:8]
        hash_value = hash_value.upper()
        expected_ref = f"MC-{hash_value}"

        assert not Customer.objects.filter(ref=expected_ref).exists()

    def test_existing_by_manychat_id_updates(self, subscriber_data):
        """Scenario 2: Existing by Manychat ID → updates, no duplicate."""
        customer1, created1 = ManychatService.sync_subscriber(subscriber_data)
        assert created1 is True

        # Second sync — should find by Manychat ID
        subscriber_data["first_name"] = "Maria Updated"
        customer2, created2 = ManychatService.sync_subscriber(subscriber_data)

        assert created2 is False
        assert customer2.pk == customer1.pk
        # Only 1 customer total
        assert Customer.objects.filter(ref=customer1.ref).count() == 1

    def test_existing_by_whatsapp_id_links_manychat(self, existing_customer):
        """Scenario 3: Existing by whatsapp_id → links Manychat ID."""
        # Add the normalized WhatsApp identifier to the existing customer.
        CustomerIdentifier.objects.create(
            customer=existing_customer,
            identifier_type=IdentifierType.PHONE,
            identifier_value="5511988776655",
            source_system="manual",
        )

        data = {
            "id": "mc-link-phone-001",
            "first_name": "João",
            "whatsapp_id": "5511988776655",
        }
        customer, created = ManychatService.sync_subscriber(data)

        assert created is False
        assert customer.pk == existing_customer.pk

        # Manychat ID now linked
        assert CustomerIdentifier.objects.filter(
            customer=existing_customer,
            identifier_type=IdentifierType.MANYCHAT,
            identifier_value="mc-link-phone-001",
        ).exists()

    def test_existing_by_customer_phone_links_manychat_from_whatsapp_id(self, existing_customer):
        """Existing Customer.phone is enough to deduplicate ManyChat sync."""
        data = {
            "id": "mc-link-phone-no-ident-001",
            "first_name": "João",
            "whatsapp_id": "5511988776655",
        }

        customer, created = ManychatService.sync_subscriber(data)

        assert created is False
        assert customer.pk == existing_customer.pk
        assert CustomerIdentifier.objects.filter(
            customer=existing_customer,
            identifier_type=IdentifierType.MANYCHAT,
            identifier_value="mc-link-phone-no-ident-001",
        ).exists()

    def test_existing_by_email_links_manychat(self, existing_customer):
        """Scenario 4: Existing by email → links Manychat ID."""
        CustomerIdentifier.objects.create(
            customer=existing_customer,
            identifier_type=IdentifierType.EMAIL,
            identifier_value="joao@example.com",
            source_system="manual",
        )

        data = {
            "id": "mc-link-email-001",
            "first_name": "João",
            "email": "joao@example.com",
            "whatsapp_id": "5511988776655",
        }
        customer, created = ManychatService.sync_subscriber(data)

        assert created is False
        assert customer.pk == existing_customer.pk

    def test_partial_data_only_manychat_id(self, subscriber_partial):
        """Scenario 5: Minimal data (only ID) is rejected to avoid garbage customers."""
        with pytest.raises(ValueError, match="identificar este assinante"):
            ManychatService.sync_subscriber(subscriber_partial)

        assert Customer.objects.count() == 0

    def test_whatsapp_id_normalization(self):
        """Scenario 6: whatsapp_id is normalized before matching."""
        data = {
            "id": "mc-phone-norm-001",
            "first_name": "Ana",
            "whatsapp_id": "(11) 99988-7766",
        }
        customer, created = ManychatService.sync_subscriber(data)
        assert created is True

        # Verify normalized phone is stored
        phone_ids = CustomerIdentifier.objects.filter(
            customer=customer,
            identifier_type=IdentifierType.PHONE,
        )
        assert phone_ids.exists()
        # Should be normalized (digits only, possibly with country code)
        stored_phone = phone_ids.first().identifier_value
        assert "(" not in stored_phone
        assert " " not in stored_phone
        assert "-" not in stored_phone

    def test_invalid_whatsapp_id_is_not_persisted_as_empty_identifier(self):
        """Invalid/blank ManyChat whatsapp_id must not poison identifier lookup."""
        data = {
            "id": "mc-invalid-phone-001",
            "first_name": "Diofer",
            "whatsapp_id": "not-a-phone",
        }

        with pytest.raises(ValueError, match="identificar este assinante"):
            ManychatService.sync_subscriber(data)

        assert not CustomerIdentifier.objects.filter(
            identifier_type=IdentifierType.PHONE,
            identifier_value="",
        ).exists()


# ═══════════════════════════════════════════════════════════════════
# Webhook Tests
# ═══════════════════════════════════════════════════════════════════


def _make_signature(body: bytes, secret: str) -> str:
    """Generate HMAC-SHA256 signature for webhook payload."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _make_webhook_request(factory, body: bytes, signature: str = ""):
    """Build a POST request with JSON body and signature header."""
    request = factory.post(
        "/manychat/webhook/",
        data=body,
        content_type="application/json",
    )
    if signature:
        request.META["HTTP_X_HUB_SIGNATURE_256"] = f"sha256={signature}"
    return request


class TestManychatWebhook:
    """ManychatWebhookView POST scenarios."""

    @pytest.fixture(autouse=True)
    def _set_webhook_secret(self, settings):
        settings.MANYCHAT_WEBHOOK_SECRET = WEBHOOK_SECRET

    def test_valid_post_creates_customer(self, factory):
        """Scenario 7: Valid POST with HMAC → 200 + customer created."""
        payload = {
            "id": "evt-001",
            "subscriber": {
                "id": "mc-webhook-001",
                "first_name": "Webhook",
                "last_name": "Test",
                "whatsapp_id": "+5511999001122",
            },
        }
        body = json.dumps(payload).encode()
        sig = _make_signature(body, WEBHOOK_SECRET)
        request = _make_webhook_request(factory, body, sig)

        response = ManychatWebhookView.as_view()(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["status"] == "created"
        assert data["customer_ref"].startswith("MC-")

        # Customer actually exists
        assert Customer.objects.filter(ref=data["customer_ref"]).exists()

    def test_invalid_hmac_returns_401(self, factory):
        """Scenario 8: Invalid HMAC → 401."""
        body = json.dumps({"id": "evt-bad", "subscriber": {"id": "mc-bad"}}).encode()
        request = _make_webhook_request(factory, body, "invalid-signature")

        response = ManychatWebhookView.as_view()(request)

        assert response.status_code == 401

    def test_missing_hmac_returns_401(self, factory):
        """Scenario 8b: Missing HMAC → 401."""
        body = json.dumps({"id": "evt-nosig"}).encode()
        request = _make_webhook_request(factory, body, "")

        response = ManychatWebhookView.as_view()(request)

        assert response.status_code == 401

    def test_duplicate_event_returns_200_duplicate(self, factory):
        """Scenario 9: Duplicate event (replay) → 200 + 'duplicate'."""
        payload = {
            "event_id": "evt-replay-001",
            "subscriber": {
                "id": "mc-replay-001",
                "first_name": "Replay",
                "whatsapp_id": "+5511999003344",
            },
        }
        body = json.dumps(payload).encode()
        sig = _make_signature(body, WEBHOOK_SECRET)

        # First request — succeeds
        request1 = _make_webhook_request(factory, body, sig)
        response1 = ManychatWebhookView.as_view()(request1)
        assert response1.status_code == 200
        data1 = json.loads(response1.content)
        assert data1["status"] == "created"

        # Second request — same event ID → duplicate
        request2 = _make_webhook_request(factory, body, sig)
        response2 = ManychatWebhookView.as_view()(request2)
        assert response2.status_code == 200
        data2 = json.loads(response2.content)
        assert data2["status"] == "duplicate"

    def test_partial_subscriber_data(self, factory):
        """Scenario 10: Minimal subscriber data is rejected."""
        payload = {
            "id": "evt-partial-001",
            "subscriber": {
                "id": "mc-partial-001",
            },
        }
        body = json.dumps(payload).encode()
        sig = _make_signature(body, WEBHOOK_SECRET)
        request = _make_webhook_request(factory, body, sig)

        response = ManychatWebhookView.as_view()(request)

        assert response.status_code == 400
        data = json.loads(response.content)
        assert "identificar este assinante" in data["error"]


# ═══════════════════════════════════════════════════════════════════
# Nome que chega numa caixa só (contato de WhatsApp)
# ═══════════════════════════════════════════════════════════════════


class TestManychatNameSplit:
    """O login por WhatsApp divide o nome na entrada, com a regra do pedido."""

    def _subscriber(self, **name):
        return {"id": "mc-name-001", "whatsapp_id": "+5543999112233", **name}

    def test_full_name_in_first_name_is_split_on_create(self):
        customer, created = ManychatService.sync_subscriber(
            self._subscriber(first_name="Pablo Valentini", last_name="")
        )

        assert created is True
        assert (customer.first_name, customer.last_name) == ("Pablo", "Valentini")
        assert customer.name == "Pablo Valentini"
        # O texto cru fica guardado: a divisão é um palpite, e precisa ser reparável.
        assert customer.metadata["manychat_name_raw"] == {
            "first_name": "Pablo Valentini",
            "last_name": "",
        }

    def test_rule_errs_on_the_surname_side(self):
        customer, _ = ManychatService.sync_subscriber(
            self._subscriber(first_name="Ana Maria Silva")
        )

        assert (customer.first_name, customer.last_name) == ("Ana", "Maria Silva")

    def test_explicit_last_name_is_trusted_as_sent(self):
        customer, _ = ManychatService.sync_subscriber(
            self._subscriber(first_name="Ana Maria", last_name="Silva")
        )

        assert (customer.first_name, customer.last_name) == ("Ana Maria", "Silva")

    def test_single_token_keeps_last_name_empty(self):
        customer, _ = ManychatService.sync_subscriber(self._subscriber(first_name="Pablo"))

        assert (customer.first_name, customer.last_name) == ("Pablo", "")

    def test_no_name_stores_no_raw_name(self):
        customer, _ = ManychatService.sync_subscriber(self._subscriber())

        assert (customer.first_name, customer.last_name) == ("", "")
        assert "manychat_name_raw" not in customer.metadata

    def test_update_fills_only_empty_fields(self):
        customer = Customer.objects.create(
            ref="NAME-001", first_name="Paulinho", last_name="", phone="+5543999112233"
        )

        ManychatService.sync_customer(customer, self._subscriber(first_name="Pablo Valentini"))
        customer.refresh_from_db()

        # O nome que já estava fica; só o sobrenome vazio é completado.
        assert (customer.first_name, customer.last_name) == ("Paulinho", "Valentini")
        assert customer.metadata["manychat_name_raw"]["first_name"] == "Pablo Valentini"

    def test_update_never_overwrites_filled_names(self):
        customer = Customer.objects.create(
            ref="NAME-002", first_name="Pablo", last_name="V.", phone="+5543999112233"
        )

        ManychatService.sync_customer(customer, self._subscriber(first_name="Pablo Valentini"))
        customer.refresh_from_db()

        assert (customer.first_name, customer.last_name) == ("Pablo", "V.")
        assert "manychat_name_raw" not in customer.metadata

    def test_update_fills_both_when_empty(self):
        customer = Customer.objects.create(
            ref="NAME-003", first_name="", last_name="", phone="+5543999112233"
        )

        ManychatService.sync_customer(customer, self._subscriber(first_name="Pablo Valentini"))
        customer.refresh_from_db()

        assert (customer.first_name, customer.last_name) == ("Pablo", "Valentini")

    def test_legacy_full_name_record_is_not_doubled(self):
        """Cadastro gravado antes da divisão não vira "Pablo Valentini Valentini"."""
        customer = Customer.objects.create(
            ref="NAME-004", first_name="Pablo Valentini", last_name="", phone="+5543999112233"
        )

        ManychatService.sync_customer(customer, self._subscriber(first_name="Pablo Valentini"))
        customer.refresh_from_db()

        assert (customer.first_name, customer.last_name) == ("Pablo Valentini", "")
        assert customer.name == "Pablo Valentini"
        assert "manychat_name_raw" not in customer.metadata

    def test_existing_subscriber_resync_splits_into_empty_last_name(self):
        """O caminho do login com assinante já conhecido (achado pelo ID do ManyChat)."""
        ManychatService.sync_subscriber(self._subscriber(first_name="Pablo"))

        customer, created = ManychatService.sync_subscriber(
            self._subscriber(first_name="Pablo Valentini")
        )

        assert created is False
        assert (customer.first_name, customer.last_name) == ("Pablo", "Valentini")
