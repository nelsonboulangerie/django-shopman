#!/usr/bin/env python
"""Shopman release/pilot readiness contract.

This script is intentionally stricter than a healthcheck and less expensive
than the full CI suite. It answers one operational question:

    "Can this tree move toward a real pilot, and what is still external?"

Local failures exit non-zero. External blockers (gateway credentials, physical
QA evidence, pre-prod URL) are reported honestly and only fail with
``--strict-external``. Profiles make the target explicit:

- ``pilot`` preserves the historical local+external report.
- ``alpha`` means a publicable technical staging for invited testers. Mock PIX
  may be intentional, but only with an explicit test path and hard production
  guardrails.
- ``production`` means real-money go-live. Test affordances and mock gateways
  are blockers.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Literal

try:
    import fcntl
except ImportError:  # pragma: no cover - POSIX is the supported deploy target
    fcntl = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

Status = Literal["passed", "failed", "blocked_external", "warning"]
ReadinessProfile = Literal["pilot", "alpha", "production"]

_NON_PRODUCTION_ENVIRONMENTS = {"development", "dev", "local", "staging", "alpha", "test"}
_PRODUCTION_ENVIRONMENTS = {"production", "prod", "live"}


@dataclass(frozen=True)
class ReadinessCheck:
    id: str
    title: str
    status: Status
    message: str
    details: dict[str, object] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return self.status == "failed"

    @property
    def external_blocked(self) -> bool:
        return self.status == "blocked_external"

    def as_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "message": self.message,
        }
        if self.details:
            data["details"] = self.details
        return data


@dataclass(frozen=True)
class ReadinessReport:
    checks: tuple[ReadinessCheck, ...]
    strict_external: bool
    profile: ReadinessProfile = "pilot"

    @property
    def local_failed(self) -> bool:
        return any(check.failed for check in self.checks)

    @property
    def external_blocked(self) -> bool:
        return any(check.external_blocked for check in self.checks)

    @property
    def blocking(self) -> bool:
        return self.local_failed or (self.strict_external and self.external_blocked)

    @property
    def status(self) -> str:
        if self.local_failed:
            return "failed"
        if self.external_blocked:
            return "blocked_external" if self.strict_external else "passed_with_external_blockers"
        return "passed"

    @property
    def counts(self) -> dict[str, int]:
        statuses = ("passed", "failed", "blocked_external", "warning")
        return {status: sum(1 for check in self.checks if check.status == status) for status in statuses}

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "profile": self.profile,
            "strict_external": self.strict_external,
            "counts": self.counts,
            "checks": [check.as_dict() for check in self.checks],
        }


def setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    previous_disable_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        django.setup()
    finally:
        logging.disable(previous_disable_level)


@contextmanager
def _process_lock():
    """Serialize readiness runs that mutate local smoke data.

    The gateway smoke fixtures run inside rollback transactions, but two local
    readiness processes sharing SQLite can still collide on write locks. The
    lock is process-scoped and automatically released by the OS on exit.
    """
    if fcntl is None:
        yield
        return

    lock_path = Path(os.environ.get("SHOPMAN_RELEASE_READINESS_LOCK", "/tmp/shopman-release-readiness.lock"))
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def build_report(
    *,
    profile: ReadinessProfile = "pilot",
    strict_external: bool = False,
    manual_qa_evidence: str = "",
    preprod_url: str = "",
) -> ReadinessReport:
    setup_django()
    strict_external = bool(strict_external or profile == "production")

    with _suppress_operational_logs():
        checks = [
            _django_system_check(),
            *(_profile_checks(profile)),
            _migration_check(),
            _storefront_contact_check(),
            _omotenashi_seed_check(),
            _rules_load_check(),
            _gateway_smoke_check(),
            _gateway_sandbox_check(profile=profile),
            _manual_qa_check(manual_qa_evidence, profile=profile),
            _preprod_check(preprod_url),
        ]
    return ReadinessReport(checks=tuple(checks), strict_external=strict_external, profile=profile)


@contextmanager
def _suppress_operational_logs():
    """Keep readiness output operator-readable while preserving check details."""
    previous_disable_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(previous_disable_level)


def _profile_checks(profile: ReadinessProfile) -> tuple[ReadinessCheck, ...]:
    if profile == "alpha":
        return (_alpha_profile_check(),)
    if profile == "production":
        return (_production_profile_check(),)
    return ()


def _alpha_profile_check() -> ReadinessCheck:
    from django.conf import settings

    environment = _environment_name()
    adapters = _payment_adapters()
    mock_methods = _mock_payment_methods(adapters)
    allow_mock = bool(getattr(settings, "SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS", False))
    expose_mock_capture = bool(getattr(settings, "SHOPMAN_EXPOSE_MOCK_CAPTURE", False))
    mock_pix_auto_confirm = bool(getattr(settings, "SHOPMAN_MOCK_PIX_AUTO_CONFIRM", False))
    warnings: list[str] = []
    failures: list[str] = []

    if settings.DEBUG:
        failures.append("DJANGO_DEBUG=false")
    if environment in _PRODUCTION_ENVIRONMENTS:
        failures.append("SHOPMAN_ENVIRONMENT=staging")
    elif environment not in _NON_PRODUCTION_ENVIRONMENTS:
        warnings.append(f"SHOPMAN_ENVIRONMENT_desconhecido:{environment or '<empty>'}")

    if mock_methods and not allow_mock:
        failures.append("SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true")
    if "pix" in mock_methods and not (mock_pix_auto_confirm or expose_mock_capture):
        failures.append("SHOPMAN_MOCK_PIX_AUTO_CONFIRM=true_or_SHOPMAN_EXPOSE_MOCK_CAPTURE=true")

    if expose_mock_capture:
        warnings.append("SHOPMAN_EXPOSE_MOCK_CAPTURE=true")
    if mock_pix_auto_confirm:
        warnings.append("SHOPMAN_MOCK_PIX_AUTO_CONFIRM=true")
    if bool(getattr(settings, "SHOPMAN_EXPOSE_DEBUG_OTP", False)):
        warnings.append("SHOPMAN_EXPOSE_DEBUG_OTP=true")
    if bool(getattr(settings, "SHOPMAN_STAGING_AUTOPILOT", False)):
        warnings.append("SHOPMAN_STAGING_AUTOPILOT=true")

    details = {
        "environment": environment,
        "mock_payment_methods": mock_methods,
        "test_affordances": warnings,
    }
    if failures:
        return ReadinessCheck(
            id="alpha.profile",
            title="Alpha technical profile",
            status="failed",
            message="Alpha técnico não está configurado de forma publicável.",
            details={**details, "missing_or_invalid": failures},
        )
    if warnings:
        return ReadinessCheck(
            id="alpha.profile",
            title="Alpha technical profile",
            status="warning",
            message="Alpha técnico está explícito, com affordances de teste que devem sair no go-live.",
            details=details,
        )
    return ReadinessCheck(
        id="alpha.profile",
        title="Alpha technical profile",
        status="passed",
        message="Alpha técnico sem affordances de teste expostas.",
        details=details,
    )


def _production_profile_check() -> ReadinessCheck:
    from django.conf import settings

    environment = _environment_name()
    adapters = _payment_adapters()
    failures: list[str] = []

    if settings.DEBUG:
        failures.append("DJANGO_DEBUG=false")
    if environment not in _PRODUCTION_ENVIRONMENTS:
        failures.append("SHOPMAN_ENVIRONMENT=production")
    if bool(getattr(settings, "SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS", False)):
        failures.append("remove_SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS")
    if bool(getattr(settings, "SHOPMAN_EXPOSE_MOCK_CAPTURE", False)):
        failures.append("remove_SHOPMAN_EXPOSE_MOCK_CAPTURE")
    if bool(getattr(settings, "SHOPMAN_MOCK_PIX_AUTO_CONFIRM", False)):
        failures.append("remove_SHOPMAN_MOCK_PIX_AUTO_CONFIRM")
    if bool(getattr(settings, "SHOPMAN_EXPOSE_DEBUG_OTP", False)):
        failures.append("remove_SHOPMAN_EXPOSE_DEBUG_OTP")
    if bool(getattr(settings, "SHOPMAN_STAGING_AUTOPILOT", False)):
        failures.append("remove_SHOPMAN_STAGING_AUTOPILOT")

    mock_methods = _mock_payment_methods(adapters)
    if mock_methods:
        failures.append("real_payment_adapters_for_" + "_".join(mock_methods))

    details = {"environment": environment, "mock_payment_methods": mock_methods}
    if failures:
        return ReadinessCheck(
            id="production.profile",
            title="Production flip profile",
            status="failed",
            message="Produção ainda contém switches de alpha/staging.",
            details={**details, "remove_or_change": failures},
        )
    return ReadinessCheck(
        id="production.profile",
        title="Production flip profile",
        status="passed",
        message="Nenhum switch explícito de teste/staging está ligado para produção.",
        details=details,
    )


def _environment_name() -> str:
    from django.conf import settings

    return str(getattr(settings, "SHOPMAN_ENVIRONMENT", "") or "").strip().lower()


def _payment_adapters() -> dict:
    from django.conf import settings

    return dict(getattr(settings, "SHOPMAN_PAYMENT_ADAPTERS", {}) or {})


def _mock_payment_methods(adapters: dict) -> list[str]:
    return [
        method
        for method in ("pix", "card")
        if "payment_mock" in str(adapters.get(method) or "")
    ]


def _django_system_check() -> ReadinessCheck:
    from django.core.management import call_command

    try:
        output = StringIO()
        call_command("check", deploy=True, stdout=output, stderr=output, verbosity=0)
    except Exception as exc:  # noqa: BLE001 - readiness must report every local blocker
        return ReadinessCheck(
            id="django.check",
            title="Django system checks",
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
        )
    return ReadinessCheck(
        id="django.check",
        title="Django system checks",
        status="passed",
        message="Deploy system checks passed.",
    )


def _migration_check() -> ReadinessCheck:
    from django.core.management import call_command

    try:
        output = StringIO()
        call_command("makemigrations", check=True, dry_run=True, stdout=output, stderr=output, verbosity=0)
    except Exception as exc:  # noqa: BLE001 - uncommitted migrations block release
        return ReadinessCheck(
            id="django.migrations",
            title="Migrations committed",
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
        )
    return ReadinessCheck(
        id="django.migrations",
        title="Migrations committed",
        status="passed",
        message="No model changes without migrations.",
    )


def _storefront_contact_check() -> ReadinessCheck:
    from shopman.shop.models import Shop

    shop = Shop.load() or Shop.objects.order_by("pk").first()
    if not shop:
        return ReadinessCheck(
            id="storefront.contact",
            title="Storefront public contact",
            status="blocked_external",
            message="Shop contact is not configured.",
            details={"expected": "Run python manage.py configure_shop_contact --phone 554333231997."},
        )

    whatsapp_url = (shop.whatsapp_url or "").strip()
    if not whatsapp_url:
        return ReadinessCheck(
            id="storefront.contact",
            title="Storefront public contact",
            status="blocked_external",
            message="Storefront WhatsApp URL is missing.",
            details={"expected": "Set Shop.phone or Shop.social_links via configure_shop_contact."},
        )

    return ReadinessCheck(
        id="storefront.contact",
        title="Storefront public contact",
        status="passed",
        message="Storefront WhatsApp contact is configured.",
        details={"whatsapp_url": whatsapp_url},
    )


def _rules_load_check() -> ReadinessCheck:
    """Toda RuleConfig HABILITADA precisa carregar.

    O contrato do load é estrito (chave órfã = regra não carrega — decisão do
    Pablo, 2026-08-13); este check é a metade barulhenta: regra de dinheiro ou
    guarda que não carrega fica VERMELHA aqui em vez de sumir num WARNING de
    log, como no incidente `da69c714`. Alcance honesto: só enxerga o banco em
    que roda — no CI o seed é fresco, então rename-sem-migração aparece onde o
    dado velho mora (staging/prod) e na coluna "carrega?" do Admin.
    """
    try:
        from shopman.shop.models import RuleConfig
        from shopman.shop.rules.engine import load_rule

        broken: list[dict] = []
        total = 0
        for rc in RuleConfig.objects.filter(enabled=True):
            total += 1
            try:
                load_rule(rc)
            except Exception as exc:  # noqa: BLE001 - o motivo vai no relatório
                broken.append({"ref": rc.ref, "error": f"{type(exc).__name__}: {exc}"})
    except Exception as exc:  # noqa: BLE001 - readiness must report every local blocker
        return ReadinessCheck(
            id="rules.load",
            title="RuleConfig load contract",
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
        )

    if broken:
        return ReadinessCheck(
            id="rules.load",
            title="RuleConfig load contract",
            status="failed",
            message=f"{len(broken)} enabled rule(s) do not load.",
            details={"broken": broken, "total_enabled": total},
        )
    return ReadinessCheck(
        id="rules.load",
        title="RuleConfig load contract",
        status="passed",
        message=f"{total} enabled rule(s) load cleanly.",
        details={"total_enabled": total},
    )


def _omotenashi_seed_check() -> ReadinessCheck:
    from shopman.backstage.services.omotenashi_qa import build_omotenashi_qa_report

    try:
        report = build_omotenashi_qa_report()
    except Exception as exc:  # noqa: BLE001
        return ReadinessCheck(
            id="omotenashi.seed",
            title="Omotenashi QA seed matrix",
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
        )

    details = report.as_dict().get("counts", {})
    if report.blocking:
        missing = [check.id for check in report.checks if check.status == "missing"]
        return ReadinessCheck(
            id="omotenashi.seed",
            title="Omotenashi QA seed matrix",
            status="failed",
            message="Seed does not cover every canonical Omotenashi scenario.",
            details={"counts": details, "missing": missing},
        )
    return ReadinessCheck(
        id="omotenashi.seed",
        title="Omotenashi QA seed matrix",
        status="passed",
        message=f"{report.ready_count}/{len(report.checks)} scenarios ready.",
        details={"counts": details},
    )


def _gateway_smoke_check() -> ReadinessCheck:
    from shopman.backstage.services.gateway_smoke import run_gateway_smoke

    try:
        report = run_gateway_smoke(
            include_local=True,
            include_sandbox_readiness=False,
            require_sandbox=False,
            rollback=True,
        )
    except Exception as exc:  # noqa: BLE001
        return ReadinessCheck(
            id="gateways.local",
            title="Local gateway smoke",
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
        )

    failed = [check.as_dict() for check in report.checks if check.is_failure]
    if failed:
        return ReadinessCheck(
            id="gateways.local",
            title="Local gateway smoke",
            status="failed",
            message="At least one local gateway fixture failed.",
            details={"counts": report.counts, "failed": failed},
        )
    return ReadinessCheck(
        id="gateways.local",
        title="Local gateway smoke",
        status="passed",
        message="EFI, Stripe and iFood local contracts passed with rollback.",
        details={"counts": report.counts, "rolled_back": report.rolled_back},
    )


def _gateway_sandbox_check(*, profile: ReadinessProfile = "pilot") -> ReadinessCheck:
    from shopman.backstage.services.gateway_smoke import run_gateway_smoke

    try:
        report = run_gateway_smoke(
            include_local=False,
            include_sandbox_readiness=True,
            require_sandbox=False,
            rollback=True,
            readiness_mode="runtime" if profile == "production" else "staging",
        )
    except Exception as exc:  # noqa: BLE001
        return ReadinessCheck(
            id="gateways.sandbox",
            title="Gateway sandbox/staging readiness",
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
        )

    blocked = []
    alpha_waived = []
    for check in report.checks:
        if check.is_blocked and _alpha_waives_gateway_blocker(profile, check):
            alpha_waived.append(check.as_dict())
        elif check.is_blocked:
            blocked.append(check.as_dict())
    failed = [check.as_dict() for check in report.checks if check.is_failure]
    if failed:
        return ReadinessCheck(
            id="gateways.sandbox",
            title="Gateway sandbox/staging readiness",
            status="failed",
            message="Sandbox readiness check failed unexpectedly.",
            details={"counts": report.counts, "failed": failed},
        )
    if blocked:
        return ReadinessCheck(
            id="gateways.sandbox",
            title="Gateway sandbox/staging readiness",
            status="blocked_external",
            message="Requires real sandbox/staging credentials before production traffic.",
            details={"counts": report.counts, "blocked": blocked, "alpha_waived": alpha_waived},
        )
    if alpha_waived:
        return ReadinessCheck(
            id="gateways.sandbox",
            title="Gateway sandbox/staging readiness",
            status="warning",
            message="Alpha técnico usa simulação/fallback explícitos para alguns provedores externos.",
            details={"counts": report.counts, "alpha_waived": alpha_waived},
        )
    return ReadinessCheck(
        id="gateways.sandbox",
        title="Gateway sandbox/staging readiness",
        status="passed",
        message="Sandbox/staging gateway configuration is ready to exercise.",
        details={"counts": report.counts},
    )


def _alpha_waives_gateway_blocker(profile: ReadinessProfile, check) -> bool:
    if profile != "alpha":
        return False

    from django.conf import settings

    adapters = _payment_adapters()
    allow_mock = bool(getattr(settings, "SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS", False))
    if check.provider == "efi":
        return allow_mock and "payment_mock" in str(adapters.get("pix") or "")
    if check.provider == "stripe":
        return allow_mock and "payment_mock" in str(adapters.get("card") or "")
    if check.provider == "manychat":
        sender = str((getattr(settings, "DOORMAN", {}) or {}).get("MESSAGE_SENDER_CLASS") or "")
        return bool(getattr(settings, "SHOPMAN_EXPOSE_DEBUG_OTP", False)) or sender.endswith("LogSender")
    return False


def _manual_qa_check(evidence_path: str, *, profile: ReadinessProfile = "pilot") -> ReadinessCheck:
    evidence = (evidence_path or os.environ.get("SHOPMAN_MANUAL_QA_EVIDENCE", "")).strip()
    if evidence and Path(evidence).expanduser().exists():
        path = Path(evidence).expanduser()
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="utf-8", errors="ignore")
        if "manual_qa_status: passed" not in content:
            if profile == "alpha":
                return ReadinessCheck(
                    id="omotenashi.manual",
                    title="Physical/staging Omotenashi QA evidence",
                    status="warning",
                    message="Manual QA evidence exists but is still pending for the alpha tester window.",
                    details={"evidence": str(path), "expected": "Set manual_qa_status: passed before production."},
                )
            return ReadinessCheck(
                id="omotenashi.manual",
                title="Physical/staging Omotenashi QA evidence",
                status="blocked_external",
                message="Manual QA evidence exists but is not marked as passed.",
                details={"expected": "Add manual_qa_status: passed after completing the device/staging checklist."},
            )
        return ReadinessCheck(
            id="omotenashi.manual",
            title="Physical/staging Omotenashi QA evidence",
            status="passed",
            message="Manual QA evidence file exists.",
                details={"evidence": str(path)},
            )
    if profile == "alpha":
        return ReadinessCheck(
            id="omotenashi.manual",
            title="Physical/staging Omotenashi QA evidence",
            status="warning",
            message="Manual QA evidence is expected during the invited alpha tester window.",
            details={"expected": "Use docs/runbooks/manual-qa-evidence-template.md during the alpha wave."},
        )
    return ReadinessCheck(
        id="omotenashi.manual",
        title="Physical/staging Omotenashi QA evidence",
        status="blocked_external",
        message="Needs a human/device or staging evidence file before real release.",
        details={"expected": "Set SHOPMAN_MANUAL_QA_EVIDENCE=/path/to/report.md or pass --manual-qa-evidence."},
    )


def _preprod_check(preprod_url: str) -> ReadinessCheck:
    url = (preprod_url or os.environ.get("SHOPMAN_PREPROD_URL", "")).strip()
    if url:
        return ReadinessCheck(
            id="preprod.environment",
            title="Pre-prod environment",
            status="passed",
            message="Pre-prod URL is declared for release playbook execution.",
            details={"url": url},
        )
    return ReadinessCheck(
        id="preprod.environment",
        title="Pre-prod environment",
        status="blocked_external",
        message="Needs real pre-prod/staging URL, secrets and provider configuration.",
        details={"expected": "Set SHOPMAN_PREPROD_URL=https://staging.example.com for strict release checks."},
    )


def print_human(report: ReadinessReport) -> None:
    print(f"release-readiness[{report.profile}]: {report.status}")
    print(
        "counts: "
        f"passed={report.counts['passed']} failed={report.counts['failed']} "
        f"blocked_external={report.counts['blocked_external']} warning={report.counts['warning']}"
    )
    for check in report.checks:
        marker = {
            "passed": "OK",
            "failed": "FAIL",
            "blocked_external": "BLOCKED",
            "warning": "WARN",
        }[check.status]
        print(f"- [{marker}] {check.id}: {check.message}")
        if check.details:
            print(f"  details={json.dumps(check.details, ensure_ascii=False, sort_keys=True)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Shopman release/pilot readiness.")
    parser.add_argument(
        "--profile",
        choices=("pilot", "alpha", "production"),
        default=os.environ.get("SHOPMAN_READINESS_PROFILE", "pilot"),
        help="Readiness contract to apply: pilot, alpha technical staging, or production go-live.",
    )
    parser.add_argument("--strict-external", action="store_true", help="Fail when external readiness is blocked.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--manual-qa-evidence", default="", help="Path to a physical/staging QA evidence report.")
    parser.add_argument("--preprod-url", default="", help="Staging/pre-prod URL declared for release playbook.")
    args = parser.parse_args(argv)
    strict_external = bool(args.strict_external or args.profile == "production")

    with _process_lock():
        report = build_report(
            profile=args.profile,
            strict_external=strict_external,
            manual_qa_evidence=args.manual_qa_evidence,
            preprod_url=args.preprod_url,
        )
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print_human(report)
    return 1 if report.blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
