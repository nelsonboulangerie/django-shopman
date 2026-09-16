"""Direct safety tests for the Efí Pix adapter.

No test in this module opens a connection to Efí.  The boundary cases exercise
the adapter entrypoint so the sandbox limit cannot be bypassed by a caller that
skips a storefront or POS validation.
"""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import pytest
from django.core.cache import cache
from django.test import override_settings

from shopman.shop.adapters import payment_efi


def _efi_config(certificate_path: str, *, sandbox: bool = True, client_id: str = "client-a") -> dict:
    return {
        "sandbox": sandbox,
        "client_id": client_id,
        "client_secret": "not-a-real-secret",
        "certificate_path": certificate_path,
        "pix_key": "not-a-real-pix-key",
    }


def _intent_from_call(kwargs: dict) -> SimpleNamespace:
    return SimpleNamespace(
        ref="PI-EFI-TEST",
        status="pending",
        amount_q=kwargs["amount_q"],
        expires_at=kwargs["expires_at"],
        gateway_id=kwargs["gateway_id"],
        gateway_data=dict(kwargs["gateway_data"]),
        save=Mock(),
    )


@pytest.mark.parametrize("amount_q", [999, 1000])
def test_efi_sandbox_accepts_amounts_through_ten_reais(tmp_path, amount_q):
    certificate = tmp_path / "efi.pem"
    certificate.write_text("certificate-a")
    payment_service = Mock()
    payment_service.create_intent.side_effect = lambda **kwargs: _intent_from_call(kwargs)

    with (
        override_settings(SHOPMAN_EFI=_efi_config(str(certificate))),
        patch("shopman.payman.PaymentService.create_intent", payment_service.create_intent),
        patch.object(
            payment_efi,
            "_request",
            side_effect=[
                {"loc": {"id": 7}, "location": "pix.example/7"},
                {"qrcode": "copy-paste", "imagemQrcode": "data:image/svg+xml;base64,test"},
            ],
        ) as request_mock,
    ):
        result = payment_efi.create_intent(
            order_ref=f"ORDER-{amount_q}",
            amount_q=amount_q,
            idempotency_key=f"idem-{amount_q}",
        )

    assert result.amount_q == amount_q
    assert result.metadata["provider_environment"] == "sandbox"
    assert result.metadata["confirmation_mode"] == "provider_simulated"
    assert payment_service.create_intent.call_count == 1
    assert request_mock.call_count == 2


def test_efi_sandbox_rejects_above_ten_reais_before_ledger_or_network(tmp_path):
    from shopman.shop.services.pix_policy import PixPaymentPolicyError

    certificate = tmp_path / "efi.pem"
    certificate.write_text("certificate-a")

    with (
        override_settings(SHOPMAN_EFI=_efi_config(str(certificate))),
        patch("shopman.payman.PaymentService.create_intent") as create_ledger_intent,
        patch.object(payment_efi, "_request") as request_mock,
        pytest.raises(PixPaymentPolicyError) as raised,
    ):
        payment_efi.create_intent(
            order_ref="ORDER-1001",
            amount_q=1001,
            idempotency_key="idem-1001",
        )

    assert raised.value.code == "pix_test_amount_limit"
    assert raised.value.current_amount_q == 1001
    assert raised.value.max_amount_q == 1000
    create_ledger_intent.assert_not_called()
    request_mock.assert_not_called()


@pytest.mark.parametrize(
    "exc",
    [
        TimeoutError("timeout"),
        HTTPError("https://pix", 503, "unavailable", {}, None),
    ],
)
@pytest.mark.django_db
def test_efi_refund_propagates_ambiguous_transport_and_server_errors(exc):
    from shopman.payman import PaymentService

    intent = PaymentService.create_intent(
        order_ref="ORDER-REFUND-TRANSIENT",
        amount_q=500,
        method="pix",
        gateway="efi",
        gateway_id="TXID-REFUND-TRANSIENT",
        gateway_data={"provider_environment": "sandbox"},
    )
    PaymentService.authorize(intent.ref, gateway_id=intent.gateway_id)
    PaymentService.capture(intent.ref, gateway_id=intent.gateway_id)

    with (
        patch.object(
            payment_efi,
            "_request",
            side_effect=[
                {
                    "status": "CONCLUIDA",
                    "pix": [{"endToEndId": "E2E-TRANSIENT"}],
                    "valor": {"original": "5.00"},
                },
                exc,
            ],
        ),
        pytest.raises(type(exc)),
    ):
        payment_efi.refund(intent.ref, idempotency_key="refund-transient")


def test_efi_production_does_not_apply_sandbox_limit_and_marks_live_confirmation(tmp_path):
    certificate = tmp_path / "efi.pem"
    certificate.write_text("certificate-a")
    payment_service = Mock()
    payment_service.create_intent.side_effect = lambda **kwargs: _intent_from_call(kwargs)

    with (
        override_settings(SHOPMAN_EFI=_efi_config(str(certificate), sandbox=False)),
        patch("shopman.payman.PaymentService.create_intent", payment_service.create_intent),
        patch.object(
            payment_efi,
            "_request",
            side_effect=[
                {"loc": {"id": 9}, "location": "pix.example/9"},
                {"qrcode": "copy-paste", "imagemQrcode": "data:image/svg+xml;base64,test"},
            ],
        ) as request_mock,
    ):
        result = payment_efi.create_intent(
            order_ref="ORDER-PRODUCTION",
            amount_q=1001,
            idempotency_key="idem-production-1001",
        )

    assert result.amount_q == 1001
    assert result.metadata["provider_environment"] == "production"
    assert result.metadata["confirmation_mode"] == "provider_live"
    assert payment_service.create_intent.call_args.kwargs["gateway_data"]["provider_environment"] == "production"
    assert payment_service.create_intent.call_args.kwargs["gateway_data"]["confirmation_mode"] == "provider_live"
    assert request_mock.call_count == 2


def test_efi_persists_deterministic_txid_before_creating_remote_charge(tmp_path):
    certificate = tmp_path / "efi.pem"
    certificate.write_text("certificate-a")
    idempotency_key = "sale-close:ORDER-RACE:pix"
    expected_txid = uuid.uuid5(uuid.NAMESPACE_URL, f"shopman-efi:{idempotency_key}").hex
    observed_intent: SimpleNamespace | None = None

    def create_ledger_intent(**kwargs):
        nonlocal observed_intent
        observed_intent = _intent_from_call(kwargs)
        return observed_intent

    def remote_request(method, path, payload=None):
        assert observed_intent is not None
        assert observed_intent.gateway_id == expected_txid
        assert observed_intent.gateway_data["txid"] == expected_txid
        assert observed_intent.gateway_data["provider_environment"] == "sandbox"
        assert observed_intent.gateway_data["confirmation_mode"] == "provider_simulated"
        if method == "PUT":
            assert path == f"/v2/cob/{expected_txid}"
            return {"loc": {"id": 8}, "location": "pix.example/8"}
        assert path == "/v2/loc/8/qrcode"
        return {"qrcode": "copy-paste", "imagemQrcode": "data:image/svg+xml;base64,test"}

    with (
        override_settings(SHOPMAN_EFI=_efi_config(str(certificate))),
        patch("shopman.payman.PaymentService.create_intent", side_effect=create_ledger_intent) as create_mock,
        patch.object(payment_efi, "_request", side_effect=remote_request),
    ):
        result = payment_efi.create_intent(
            order_ref="ORDER-RACE",
            amount_q=1000,
            idempotency_key=idempotency_key,
        )

    assert result.gateway_id == expected_txid
    assert create_mock.call_args.kwargs["gateway_id"] == expected_txid
    assert create_mock.call_args.kwargs["gateway_data"]["txid"] == expected_txid
    assert observed_intent.gateway_data["provider_environment"] == "sandbox"
    assert observed_intent.gateway_data["confirmation_mode"] == "provider_simulated"


@pytest.mark.django_db
def test_efi_qr_save_preserves_webhook_capture_that_wins_after_put(tmp_path):
    from shopman.payman import PaymentService

    certificate = tmp_path / "efi.pem"
    certificate.write_text("certificate-a")
    order_ref = "ORDER-WEBHOOK-RACE"
    idempotency_key = "order-payment:ORDER-WEBHOOK-RACE:pix:1000:g0"
    expected_txid = uuid.uuid5(uuid.NAMESPACE_URL, f"shopman-efi:{idempotency_key}").hex

    def remote_request(method, path, payload=None):
        if method == "PUT":
            intent = PaymentService.get_by_order(order_ref)[0]
            assert intent.gateway_id == expected_txid
            PaymentService.authorize(
                intent.ref,
                gateway_id=expected_txid,
                gateway_data={"e2e_id": "E-WEBHOOK-WON"},
            )
            PaymentService.capture(intent.ref, gateway_id=expected_txid)
            return {"loc": {"id": 18}, "location": "pix.example/18"}
        assert method == "GET"
        assert path == "/v2/loc/18/qrcode"
        return {"qrcode": "copy-paste", "imagemQrcode": "data:image/svg+xml;base64,test"}

    with (
        override_settings(SHOPMAN_EFI=_efi_config(str(certificate))),
        patch.object(payment_efi, "_request", side_effect=remote_request),
    ):
        result = payment_efi.create_intent(
            order_ref=order_ref,
            amount_q=1000,
            idempotency_key=idempotency_key,
        )

    intent = PaymentService.get(result.intent_ref)
    assert result.status == "captured"
    assert intent.status == "captured"
    assert intent.gateway_data["e2e_id"] == "E-WEBHOOK-WON"
    assert intent.gateway_data["confirmation_mode"] == "provider_simulated"
    assert intent.gateway_data["efi_creation_phase"] == "qr_ready"


@pytest.mark.django_db
def test_efi_qr_failure_stays_pending_and_retry_skips_second_charge_put(tmp_path):
    from shopman.payman import PaymentService

    certificate = tmp_path / "efi.pem"
    certificate.write_text("certificate-a")
    order_ref = "ORDER-QR-RETRY"
    idempotency_key = "sale-close:ORDER-QR-RETRY:pix"
    expected_txid = uuid.uuid5(uuid.NAMESPACE_URL, f"shopman-efi:{idempotency_key}").hex
    calls: list[tuple[str, str]] = []

    def remote_request(method, path, payload=None):
        calls.append((method, path))
        if len(calls) == 1:
            assert method == "PUT"
            assert path == f"/v2/cob/{expected_txid}"
            return {"loc": {"id": 17}, "location": "pix.example/17"}
        if len(calls) == 2:
            assert method == "GET"
            assert path == "/v2/loc/17/qrcode"
            raise TimeoutError("simulated QR timeout")
        assert len(calls) == 3
        assert method == "GET"
        assert path == "/v2/loc/17/qrcode"
        return {"qrcode": "copy-paste", "imagemQrcode": "data:image/svg+xml;base64,test"}

    with (
        override_settings(SHOPMAN_EFI=_efi_config(str(certificate))),
        patch.object(payment_efi, "_request", side_effect=remote_request),
    ):
        with pytest.raises(TimeoutError, match="simulated QR timeout"):
            payment_efi.create_intent(
                order_ref=order_ref,
                amount_q=1000,
                idempotency_key=idempotency_key,
            )

        intent = PaymentService.get_by_order(order_ref)[0]
        assert intent.status == "pending"
        assert intent.gateway_id == expected_txid
        assert intent.gateway_data["efi_location_id"] == 17
        assert intent.gateway_data["efi_creation_phase"] == "charge_created"
        assert intent.gateway_data["efi_remote_state"] == "created"
        assert intent.gateway_data["efi_last_error_stage"] == "qr_fetch"
        assert intent.gateway_data["efi_last_error_type"] == "TimeoutError"

        retried = payment_efi.create_intent(
            order_ref=order_ref,
            amount_q=1000,
            idempotency_key=idempotency_key,
        )

    assert calls == [
        ("PUT", f"/v2/cob/{expected_txid}"),
        ("GET", "/v2/loc/17/qrcode"),
        ("GET", "/v2/loc/17/qrcode"),
    ]
    assert retried.gateway_id == expected_txid
    intent.refresh_from_db()
    assert intent.status == "pending"
    assert intent.gateway_data["efi_creation_phase"] == "qr_ready"
    assert intent.gateway_data["provider_environment"] == "sandbox"
    assert intent.gateway_data["confirmation_mode"] == "provider_simulated"
    assert "efi_last_error_stage" not in intent.gateway_data


@pytest.mark.django_db
def test_payment_initiate_resumes_qr_fetch_on_same_intent_without_second_put(tmp_path):
    """The orchestrator must re-enter Efí instead of adopting an unusable row."""
    from shopman.orderman.models import Order
    from shopman.payman import PaymentService

    from shopman.shop.models import Channel
    from shopman.shop.services import payment

    certificate = tmp_path / "efi.pem"
    certificate.write_text("certificate-a")
    Channel.objects.create(ref="web", name="Web")
    order = Order.objects.create(
        ref="ORDER-ORCHESTRATED-QR-RETRY",
        channel_ref="web",
        total_q=1000,
        data={"payment": {"method": "pix"}},
    )
    calls: list[tuple[str, str]] = []

    def remote_request(method, path, payload=None):
        calls.append((method, path))
        if len(calls) == 1:
            return {"loc": {"id": 23}, "location": "pix.example/23"}
        if len(calls) == 2:
            raise TimeoutError("simulated orchestrated QR timeout")
        assert len(calls) == 3
        return {"qrcode": "copy-paste", "imagemQrcode": "qr-image"}

    with (
        override_settings(
            SHOPMAN_PAYMENT_ADAPTERS={"pix": "shopman.shop.adapters.payment_efi"},
            SHOPMAN_EFI=_efi_config(str(certificate)),
        ),
        patch.object(payment_efi, "_request", side_effect=remote_request),
    ):
        payment.initiate(order)
        order.refresh_from_db()
        first_ref = order.data["payment"]["intent_ref"]
        first_txid = PaymentService.get(first_ref).gateway_id
        assert not order.data["payment"].get("copy_paste")
        assert "simulated orchestrated QR timeout" in order.data["payment"]["error"]

        payment.initiate(order)

    order.refresh_from_db()
    resumed = PaymentService.get(first_ref)
    assert order.data["payment"]["intent_ref"] == first_ref
    assert order.data["payment"]["copy_paste"] == "copy-paste"
    assert resumed.gateway_id == first_txid
    assert PaymentService.get_by_order(order.ref).count() == 1
    assert [method for method, _path in calls] == ["PUT", "GET", "GET"]
    assert "efi_last_error_type" not in resumed.gateway_data


@pytest.mark.parametrize(
    "initial_failure",
    [
        TimeoutError("PUT outcome unknown"),
        HTTPError("https://pix", 408, "request timeout", {}, None),
        HTTPError("https://pix", 429, "too many requests", {}, None),
    ],
    ids=["transport-timeout", "http-408", "http-429"],
)
@pytest.mark.django_db
def test_efi_put_timeout_retry_probes_same_txid_and_preserves_original_expiry(
    tmp_path,
    initial_failure,
):
    from shopman.payman import PaymentService

    certificate = tmp_path / "efi.pem"
    certificate.write_text("certificate-a")
    key = "idem-put-timeout"
    txid = uuid.uuid5(uuid.NAMESPACE_URL, f"shopman-efi:{key}").hex
    calls: list[tuple[str, str]] = []

    def remote_request(method, path, payload=None):
        calls.append((method, path))
        if len(calls) == 1:
            raise initial_failure
        if len(calls) == 2:
            return {"status": "ATIVA", "loc": {"id": 31}, "location": "pix.example/31"}
        return {"qrcode": "copy-paste", "imagemQrcode": "qr-image"}

    with (
        override_settings(SHOPMAN_EFI=_efi_config(str(certificate))),
        patch.object(payment_efi, "_request", side_effect=remote_request),
    ):
        with pytest.raises(type(initial_failure)):
            payment_efi.create_intent(
                order_ref="ORDER-PUT-TIMEOUT",
                amount_q=1000,
                idempotency_key=key,
            )
        intent = PaymentService.get_by_order("ORDER-PUT-TIMEOUT")[0]
        original_expiry = intent.expires_at

        resumed = payment_efi.create_intent(
            order_ref="ORDER-PUT-TIMEOUT",
            amount_q=1000,
            idempotency_key=key,
        )

    assert calls == [
        ("PUT", f"/v2/cob/{txid}"),
        ("GET", f"/v2/cob/{txid}"),
        ("GET", "/v2/loc/31/qrcode"),
    ]
    assert resumed.gateway_id == txid
    assert resumed.expires_at == original_expiry
    intent.refresh_from_db()
    assert intent.expires_at == original_expiry
    assert intent.gateway_data["efi_creation_phase"] == "qr_ready"


@pytest.mark.django_db
def test_efi_txid_conflict_is_recovered_not_marked_not_created(tmp_path):
    from shopman.payman import PaymentService

    certificate = tmp_path / "efi.pem"
    certificate.write_text("certificate-a")
    key = "idem-txid-conflict"

    with (
        override_settings(SHOPMAN_EFI=_efi_config(str(certificate))),
        patch.object(
            payment_efi,
            "_request",
            side_effect=[
                HTTPError("https://pix", 409, "txid already exists", {}, None),
                {"status": "ATIVA", "loc": {"id": 41}, "location": "pix.example/41"},
                {"qrcode": "copy-paste", "imagemQrcode": "qr-image"},
            ],
        ) as request_mock,
    ):
        result = payment_efi.create_intent(
            order_ref="ORDER-TXID-CONFLICT",
            amount_q=1000,
            idempotency_key=key,
        )

    intent = PaymentService.get(result.intent_ref)
    assert request_mock.call_count == 3
    assert intent.status == "pending"
    assert intent.gateway_data["efi_remote_state"] == "created"
    assert intent.gateway_data["efi_location_id"] == 41


@pytest.mark.django_db
def test_put_timeout_then_official_not_found_response_reuses_same_txid(tmp_path):
    from shopman.payman import PaymentService

    certificate = tmp_path / "efi.pem"
    certificate.write_text("certificate-a")
    key = "idem-official-not-found"
    txid = uuid.uuid5(uuid.NAMESPACE_URL, f"shopman-efi:{key}").hex
    not_found = HTTPError("https://pix", 400, "bad request", {}, None)
    not_found.efi_error_body = '{"nome":"cobranca_nao_encontrada"}'

    with (
        override_settings(SHOPMAN_EFI=_efi_config(str(certificate))),
        patch.object(
            payment_efi,
            "_request",
            side_effect=[
                TimeoutError("PUT outcome unknown"),
                not_found,
                {"loc": {"id": 51}, "location": "pix.example/51"},
                {"qrcode": "copy-paste", "imagemQrcode": "qr-image"},
            ],
        ) as request_mock,
    ):
        with pytest.raises(TimeoutError):
            payment_efi.create_intent(
                order_ref="ORDER-OFFICIAL-NOT-FOUND",
                amount_q=1000,
                idempotency_key=key,
            )
        result = payment_efi.create_intent(
            order_ref="ORDER-OFFICIAL-NOT-FOUND",
            amount_q=1000,
            idempotency_key=key,
        )

    assert request_mock.call_count == 4
    assert result.gateway_id == txid
    assert PaymentService.get_by_order("ORDER-OFFICIAL-NOT-FOUND").count() == 1


@pytest.mark.django_db
def test_environment_flip_blocks_orchestrator_and_adapter_before_network(tmp_path):
    from shopman.orderman.models import Order
    from shopman.payman import PaymentService

    from shopman.shop.models import Channel
    from shopman.shop.services import payment

    certificate = tmp_path / "efi.pem"
    certificate.write_text("certificate-a")
    key = "idem-environment-flip"
    intent = PaymentService.create_intent(
        order_ref="ORDER-ENV-FLIP",
        amount_q=1000,
        method="pix",
        gateway="efi",
        gateway_id="sandbox-txid",
        gateway_data={
            "provider_environment": "sandbox",
            "confirmation_mode": "provider_simulated",
            "efi_remote_state": "unknown",
        },
        idempotency_key=key,
    )
    Channel.objects.create(ref="web", name="Web")
    order = Order.objects.create(
        ref="ORDER-ENV-FLIP",
        channel_ref="web",
        total_q=1000,
        data={"payment": {"method": "pix", "intent_ref": intent.ref, "idempotency_key": key}},
    )
    production = _efi_config(str(certificate), sandbox=False)

    with (
        override_settings(
            SHOPMAN_PAYMENT_ADAPTERS={"pix": "shopman.shop.adapters.payment_efi"},
            SHOPMAN_EFI=production,
        ),
        patch.object(payment_efi, "_request") as request_mock,
    ):
        payment.initiate(order)
        with pytest.raises(RuntimeError, match="outro ambiente Efí"):
            payment_efi.create_intent(
                order_ref=order.ref,
                amount_q=1000,
                idempotency_key=key,
            )

    request_mock.assert_not_called()
    intent.refresh_from_db()
    assert intent.status == "pending"
    assert intent.gateway_data["provider_environment"] == "sandbox"
    assert intent.gateway_data["confirmation_mode"] == "provider_simulated"


@pytest.mark.django_db
def test_unmarked_legacy_efi_resume_fails_before_network_or_metadata_change(tmp_path):
    from shopman.payman import PaymentService

    certificate = tmp_path / "efi.pem"
    certificate.write_text("certificate-a")
    key = "idem-environment-unknown"
    intent = PaymentService.create_intent(
        order_ref="ORDER-ENV-UNKNOWN",
        amount_q=1000,
        method="pix",
        gateway="efi",
        gateway_id="legacy-txid",
        gateway_data={"efi_remote_state": "unknown"},
        idempotency_key=key,
    )
    original_gateway_data = dict(intent.gateway_data)

    with (
        override_settings(SHOPMAN_EFI=_efi_config(str(certificate), sandbox=True)),
        patch.object(payment_efi, "_request") as request_mock,
        pytest.raises(RuntimeError, match="outro ambiente Efí"),
    ):
        payment_efi.create_intent(
            order_ref=intent.order_ref,
            amount_q=1000,
            idempotency_key=key,
        )

    request_mock.assert_not_called()
    intent.refresh_from_db()
    assert intent.gateway_data == original_gateway_data


@pytest.mark.django_db
def test_efi_definitive_failure_before_charge_marks_attempt_failed(tmp_path):
    from shopman.payman import PaymentService

    certificate = tmp_path / "efi.pem"
    certificate.write_text("certificate-a")

    with (
        override_settings(SHOPMAN_EFI=_efi_config(str(certificate))),
        patch.object(
            payment_efi,
            "_request",
            side_effect=payment_efi.EfiNotConfigured("missing credentials"),
        ) as request_mock,
        pytest.raises(payment_efi.EfiNotConfigured),
    ):
        payment_efi.create_intent(
            order_ref="ORDER-NOT-CREATED",
            amount_q=1000,
            idempotency_key="idem-not-created",
        )

    intent = PaymentService.get_by_order("ORDER-NOT-CREATED")[0]
    assert intent.status == "failed"
    assert intent.gateway_data["efi_remote_state"] == "not_created"
    assert intent.gateway_data["efi_last_error_stage"] == "charge_create"
    request_mock.assert_called_once()


@pytest.mark.django_db
def test_efi_never_reuses_mock_intent_with_same_idempotency_key(tmp_path):
    from shopman.payman import PaymentError, PaymentService

    certificate = tmp_path / "efi.pem"
    certificate.write_text("certificate-a")
    idempotency_key = "order-payment:ORDER-PROVIDER:pix:1000:attempt"
    mock_intent = PaymentService.create_intent(
        order_ref="ORDER-PROVIDER",
        amount_q=1000,
        method="pix",
        gateway="mock",
        gateway_id="mock-pix-existing",
        idempotency_key=idempotency_key,
    )

    with (
        override_settings(SHOPMAN_EFI=_efi_config(str(certificate))),
        patch.object(payment_efi, "_request") as request_mock,
        pytest.raises(PaymentError) as raised,
    ):
        payment_efi.create_intent(
            order_ref="ORDER-PROVIDER",
            amount_q=1000,
            idempotency_key=idempotency_key,
        )

    assert raised.value.code == "idempotency_key_conflict"
    request_mock.assert_not_called()
    mock_intent.refresh_from_db()
    assert mock_intent.gateway == "mock"
    assert mock_intent.gateway_id == "mock-pix-existing"


def test_efi_token_cache_key_is_namespaced_without_plaintext_identity(tmp_path):
    certificate_a = tmp_path / "efi-a.pem"
    certificate_b = tmp_path / "efi-b.pem"
    certificate_a.write_text("certificate-a")
    certificate_b.write_text("certificate-b")

    sandbox = _efi_config(str(certificate_a), sandbox=True, client_id="client-a")
    production = _efi_config(str(certificate_a), sandbox=False, client_id="client-a")
    other_client = _efi_config(str(certificate_a), sandbox=True, client_id="client-b")
    other_certificate = _efi_config(str(certificate_b), sandbox=True, client_id="client-a")

    keys = {
        payment_efi._token_cache_key(sandbox),
        payment_efi._token_cache_key(production),
        payment_efi._token_cache_key(other_client),
        payment_efi._token_cache_key(other_certificate),
    }

    assert len(keys) == 4
    for key in keys:
        assert key.startswith("efi_access_token:")
        assert "client-a" not in key
        assert "client-b" not in key
        assert str(tmp_path) not in key


def test_efi_token_is_reused_for_same_environment_and_identity(tmp_path):
    certificate = tmp_path / "efi.pem"
    certificate.write_text("certificate-a")
    config = _efi_config(str(certificate))
    cache.clear()

    with (
        override_settings(SHOPMAN_EFI=config),
        patch.object(payment_efi, "_request_access_token", return_value="sandbox-token") as request_token,
    ):
        assert payment_efi._get_access_token() == "sandbox-token"
        assert payment_efi._get_access_token() == "sandbox-token"

    request_token.assert_called_once_with(config)


def test_efi_token_refresh_is_single_flight_for_concurrent_callers(tmp_path):
    certificate = tmp_path / "efi.pem"
    certificate.write_text("certificate-a")
    config = _efi_config(str(certificate))
    cache.clear()
    request_started = threading.Event()
    release_request = threading.Event()
    calls = 0

    def request_token(_config):
        nonlocal calls
        calls += 1
        request_started.set()
        assert release_request.wait(timeout=2)
        return "shared-sandbox-token"

    with (
        override_settings(SHOPMAN_EFI=config),
        patch.object(payment_efi, "_request_access_token", side_effect=request_token),
        ThreadPoolExecutor(max_workers=2) as executor,
    ):
        first = executor.submit(payment_efi._get_access_token)
        assert request_started.wait(timeout=1)
        second = executor.submit(payment_efi._get_access_token)
        time.sleep(0.1)
        release_request.set()
        assert first.result(timeout=2) == "shared-sandbox-token"
        assert second.result(timeout=2) == "shared-sandbox-token"

    assert calls == 1
