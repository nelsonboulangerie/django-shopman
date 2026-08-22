from __future__ import annotations

import json

import pytest
from django.core.cache import cache
from django.test import override_settings

from scripts import check_release_readiness as readiness
from shopman.shop.models import Shop
from shopman.shop.models.shop import SHOP_CACHE_KEY


def test_readiness_report_allows_external_blockers_in_default_mode():
    report = readiness.ReadinessReport(
        strict_external=False,
        checks=(
            readiness.ReadinessCheck(
                id="local",
                title="Local",
                status="passed",
                message="ok",
            ),
            readiness.ReadinessCheck(
                id="external",
                title="External",
                status="blocked_external",
                message="needs credentials",
            ),
        ),
    )

    assert report.status == "passed_with_external_blockers"
    assert report.external_blocked
    assert not report.blocking
    assert report.as_dict()["profile"] == "pilot"


def test_readiness_report_blocks_external_in_strict_mode():
    report = readiness.ReadinessReport(
        strict_external=True,
        checks=(
            readiness.ReadinessCheck(
                id="external",
                title="External",
                status="blocked_external",
                message="needs staging",
            ),
        ),
    )

    assert report.status == "blocked_external"
    assert report.blocking


def test_manual_qa_evidence_check_passes_when_file_exists(tmp_path):
    evidence = tmp_path / "manual-qa.md"
    evidence.write_text("manual_qa_status: passed\n# QA\n", encoding="utf-8")

    check = readiness._manual_qa_check(str(evidence))

    assert check.status == "passed"
    assert check.details["evidence"] == str(evidence)


def test_manual_qa_evidence_check_rejects_pending_report(tmp_path):
    evidence = tmp_path / "manual-qa.md"
    evidence.write_text("manual_qa_status: pending\n# QA\n", encoding="utf-8")

    check = readiness._manual_qa_check(str(evidence))

    assert check.status == "blocked_external"


def test_manual_qa_pending_is_warning_for_alpha(tmp_path):
    evidence = tmp_path / "manual-qa.md"
    evidence.write_text("manual_qa_status: pending\n# QA\n", encoding="utf-8")

    check = readiness._manual_qa_check(str(evidence), profile="alpha")

    assert check.status == "warning"


@override_settings(
    DEBUG=False,
    SHOPMAN_ENVIRONMENT="staging",
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_mock",
        "card": "shopman.shop.adapters.payment_mock",
        "cash": None,
        "external": None,
    },
    SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=True,
    SHOPMAN_EXPOSE_MOCK_CAPTURE=True,
    SHOPMAN_MOCK_PIX_AUTO_CONFIRM=False,
    SHOPMAN_EXPOSE_DEBUG_OTP=True,
    SHOPMAN_STAGING_AUTOPILOT=True,
)
def test_alpha_profile_allows_explicit_mock_payment_with_warning():
    check = readiness._alpha_profile_check()

    assert check.status == "warning"
    assert check.details["mock_payment_methods"] == ["pix", "card"]
    assert "SHOPMAN_EXPOSE_MOCK_CAPTURE=true" in check.details["test_affordances"]


@override_settings(
    DEBUG=False,
    SHOPMAN_ENVIRONMENT="staging",
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_mock",
        "card": "shopman.shop.adapters.payment_mock",
        "cash": None,
        "external": None,
    },
    SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=True,
    SHOPMAN_EXPOSE_MOCK_CAPTURE=False,
    SHOPMAN_MOCK_PIX_AUTO_CONFIRM=False,
)
def test_alpha_profile_fails_mock_pix_without_any_capture_path():
    check = readiness._alpha_profile_check()

    assert check.status == "failed"
    assert "SHOPMAN_MOCK_PIX_AUTO_CONFIRM=true_or_SHOPMAN_EXPOSE_MOCK_CAPTURE=true" in check.details["missing_or_invalid"]


@override_settings(
    DEBUG=False,
    SHOPMAN_ENVIRONMENT="production",
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_mock",
        "card": "shopman.shop.adapters.payment_stripe",
        "cash": None,
        "external": None,
    },
    SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=True,
    SHOPMAN_EXPOSE_MOCK_CAPTURE=True,
    SHOPMAN_MOCK_PIX_AUTO_CONFIRM=True,
    SHOPMAN_EXPOSE_DEBUG_OTP=True,
    SHOPMAN_STAGING_AUTOPILOT=True,
)
def test_production_profile_blocks_alpha_switches():
    check = readiness._production_profile_check()

    assert check.status == "failed"
    assert "remove_SHOPMAN_EXPOSE_MOCK_CAPTURE" in check.details["remove_or_change"]
    assert "real_payment_adapters_for_pix" in check.details["remove_or_change"]


@override_settings(
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_mock",
        "card": "shopman.shop.adapters.payment_mock",
    },
    SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=True,
    SHOPMAN_EXPOSE_DEBUG_OTP=True,
    DOORMAN={"MESSAGE_SENDER_CLASS": "shopman.doorman.senders.LogSender"},
)
def test_alpha_gateway_waivers_cover_only_declared_simulations():
    check = type("Check", (), {"provider": "efi"})()
    assert readiness._alpha_waives_gateway_blocker("alpha", check) is True

    check.provider = "stripe"
    assert readiness._alpha_waives_gateway_blocker("alpha", check) is True

    check.provider = "manychat"
    assert readiness._alpha_waives_gateway_blocker("alpha", check) is True

    check.provider = "ifood"
    assert readiness._alpha_waives_gateway_blocker("alpha", check) is False


@pytest.mark.django_db
def test_storefront_contact_check_requires_whatsapp_url():
    cache.delete(SHOP_CACHE_KEY)
    Shop.objects.create(name="Loja")

    check = readiness._storefront_contact_check()

    assert check.status == "blocked_external"
    assert check.id == "storefront.contact"


@pytest.mark.django_db
def test_storefront_contact_check_passes_with_phone():
    cache.delete(SHOP_CACHE_KEY)
    Shop.objects.create(name="Loja", phone="554333231997")

    check = readiness._storefront_contact_check()

    assert check.status == "passed"
    assert check.details["whatsapp_url"] == "https://wa.me/554333231997"


def test_main_outputs_json_and_uses_blocking_exit(monkeypatch, capsys):
    report = readiness.ReadinessReport(
        strict_external=True,
        checks=(
            readiness.ReadinessCheck(
                id="external",
                title="External",
                status="blocked_external",
                message="needs staging",
            ),
        ),
    )
    monkeypatch.setattr(readiness, "build_report", lambda **kwargs: report)

    exit_code = readiness.main(["--strict-external", "--json"])

    data = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert data["status"] == "blocked_external"
    assert data["counts"]["blocked_external"] == 1


def test_main_production_profile_forces_strict_external(monkeypatch, capsys):
    captured = {}

    def fake_build_report(**kwargs):
        captured.update(kwargs)
        return readiness.ReadinessReport(
            profile=kwargs["profile"],
            strict_external=kwargs["strict_external"],
            checks=(
                readiness.ReadinessCheck(
                    id="external",
                    title="External",
                    status="blocked_external",
                    message="needs production credentials",
                ),
            ),
        )

    monkeypatch.setattr(readiness, "build_report", fake_build_report)

    exit_code = readiness.main(["--profile", "production", "--json"])

    data = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert captured["strict_external"] is True
    assert data["profile"] == "production"
