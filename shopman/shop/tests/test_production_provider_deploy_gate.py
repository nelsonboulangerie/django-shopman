from types import SimpleNamespace

import pytest

from shopman.shop.checks import check_production_provider_environments

pytestmark = pytest.mark.django_db


def test_production_deploy_checks_use_runtime_provider_safety(settings, monkeypatch):
    settings.SHOPMAN_ENVIRONMENT = "production"
    seen = []
    def facts(*, mode):
        seen.append(mode)
        return [SimpleNamespace(label="Stripe", status="error", missing=("STRIPE_SECRET_KEY_live",)),
                SimpleNamespace(label="Efí", status="error", missing=("EFI_SANDBOX_false",))]
    monkeypatch.setattr("shopman.backstage.services.integration_readiness.build_provider_readiness", facts)
    errors = check_production_provider_environments(None)
    assert len(errors) == 2
    assert all(error.id == "SHOPMAN_E022" for error in errors)
    assert seen == ["runtime"]


def test_staging_keeps_its_explicit_provider_policy(settings, monkeypatch):
    settings.SHOPMAN_ENVIRONMENT = "staging"
    monkeypatch.setattr("shopman.backstage.services.integration_readiness.build_provider_readiness",
                        lambda **kwargs: pytest.fail("production-only gate called in staging"))
    assert check_production_provider_environments(None) == []


def test_actual_test_provider_settings_block_production(settings):
    settings.SHOPMAN_ENVIRONMENT = "production"
    settings.SHOPMAN_PAYMENT_ADAPTERS = {"card": "shopman.shop.adapters.payment_stripe", "pix": "shopman.shop.adapters.payment_efi"}
    settings.SHOPMAN_STRIPE = {"secret_key": "sk_test_synthetic", "publishable_key": "pk_test_synthetic"}
    settings.SHOPMAN_EFI = {"sandbox": True}
    settings.SHOPMAN_FOCUS_NFE = {"environment": "homologacao"}
    errors = check_production_provider_environments(None)
    assert any("STRIPE_SECRET_KEY_live" in error.hint for error in errors)
    assert any("EFI_SANDBOX_false" in error.hint for error in errors)
    assert any("FOCUS_NFE_ENVIRONMENT" in error.hint for error in errors)
    assert "sk_test_synthetic" not in str(errors)
