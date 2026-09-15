from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import override_settings

from shopman.shop.models import Shop
from shopman.shop.services import pix_policy

pytestmark = pytest.mark.django_db

EFI_ADAPTERS = {"pix": "shopman.shop.adapters.payment_efi"}
MOCK_ADAPTERS = {"pix": "shopman.shop.adapters.payment_mock"}
EFI_SANDBOX = {
    "sandbox": True,
    "client_id": "",
    "client_secret": "",
    "certificate_path": "",
    "pix_key": "",
}


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=EFI_ADAPTERS, SHOPMAN_EFI=EFI_SANDBOX)
@pytest.mark.parametrize("amount_q", [1, 999, 1000])
def test_efi_sandbox_boundary_allows_up_to_ten_reais(amount_q):
    pix_policy.enforce_pix_test_amount_limit(amount_q)


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=EFI_ADAPTERS, SHOPMAN_EFI=EFI_SANDBOX)
def test_efi_sandbox_rejects_1001_with_actions_and_exact_cents():
    with pytest.raises(pix_policy.PixPaymentPolicyError) as caught:
        pix_policy.enforce_pix_test_amount_limit(1001)

    assert caught.value.code == "pix_test_amount_limit"
    assert caught.value.context == {
        "method": "pix",
        "provider": "efi",
        "environment": "sandbox",
        "mode": "provider_test",
        "current_amount_q": 1001,
        "max_amount_q": 1000,
        "actions": ["change_payment_method", "edit_cart"],
    }
    assert "simula a confirmação" in caught.value.message


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=EFI_ADAPTERS, SHOPMAN_EFI={})
def test_missing_efi_mode_defaults_to_sandbox_like_the_adapter():
    with pytest.raises(pix_policy.PixPaymentPolicyError):
        pix_policy.enforce_pix_test_amount_limit(1001)


@override_settings(
    SHOPMAN_PAYMENT_ADAPTERS=EFI_ADAPTERS,
    SHOPMAN_EFI={**EFI_SANDBOX, "sandbox": False},
)
def test_efi_production_has_no_test_limit():
    pix_policy.enforce_pix_test_amount_limit(100_000)
    assert pix_policy.payment_constraints_payload() == {}


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=MOCK_ADAPTERS, SHOPMAN_EFI=EFI_SANDBOX)
def test_mock_pix_has_no_efi_test_limit():
    pix_policy.enforce_pix_test_amount_limit(100_000)
    assert pix_policy.payment_constraints_payload() == {}


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=EFI_ADAPTERS, SHOPMAN_EFI=EFI_SANDBOX)
def test_shop_database_mock_override_wins_over_efi_setting():
    Shop.objects.create(
        name="Test Shop",
        integrations={"payment": {"pix": "shopman.shop.adapters.payment_mock"}},
    )

    assert pix_policy.pix_payment_constraint() is None


@override_settings(
    SHOPMAN_PAYMENT_ADAPTERS=EFI_ADAPTERS,
    SHOPMAN_EFI={
        **EFI_SANDBOX,
        "client_id": "id",
        "client_secret": "secret",
        "certificate_path": __file__,
        "pix_key": "key",
    },
    SHOPMAN_EFI_WEBHOOK={"webhook_token": "token"},
)
def test_readiness_fails_when_shop_database_overrides_efi_with_mock():
    from shopman.backstage.services.integration_readiness import efi_pix_readiness

    Shop.objects.create(
        name="Test Shop",
        integrations={"payment": {"pix": "shopman.shop.adapters.payment_mock"}},
    )

    readiness = efi_pix_readiness(mode="staging")
    assert readiness.status == "error"
    assert "SHOP_INTEGRATIONS_payment_pix_efi" in readiness.missing


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=MOCK_ADAPTERS, SHOPMAN_EFI=EFI_SANDBOX)
def test_shop_database_efi_override_activates_capability():
    Shop.objects.create(
        name="Test Shop",
        integrations={"payment": {"pix": "shopman.shop.adapters.payment_efi"}},
    )

    assert pix_policy.payment_constraints_payload()["pix"] == {
        "provider": "efi",
        "environment": "sandbox",
        "mode": "provider_test",
        "is_test": True,
        "max_amount_q": 1000,
        "max_amount_display": "R$ 10,00",
        "message": (
            "Ambiente de testes: a Efí simula a confirmação de Pix de até R$ 10,00. "
            "Para continuar, troque a forma de pagamento ou ajuste os itens do pedido."
        ),
    }


@override_settings(
    DEBUG=False,
    SHOPMAN_EXPOSE_MOCK_CAPTURE=True,
    SHOPMAN_PAYMENT_ADAPTERS=MOCK_ADAPTERS,
    SHOPMAN_EFI=EFI_SANDBOX,
)
def test_shop_database_efi_override_removes_mock_capture_affordance():
    from shopman.shop.services import payment

    Shop.objects.create(
        name="Test Shop",
        integrations={"payment": {"pix": "shopman.shop.adapters.payment_efi"}},
    )

    assert payment.mock_capture_allowed("pix") is False


@override_settings(SHOPMAN_EFI=EFI_SANDBOX)
def test_adapter_can_apply_hard_stop_without_registry_lookup():
    with patch.object(pix_policy, "get_adapter") as resolved:
        with pytest.raises(pix_policy.PixPaymentPolicyError):
            pix_policy.enforce_pix_test_amount_limit(
                1001,
                adapter_path="shopman.shop.adapters.payment_efi",
            )
    resolved.assert_not_called()


def test_unrelated_adapter_path_never_inherits_pix_limit(settings):
    settings.SHOPMAN_EFI = EFI_SANDBOX
    pix_policy.enforce_pix_test_amount_limit(
        100_000,
        adapter_path="shopman.shop.adapters.payment_stripe",
    )
