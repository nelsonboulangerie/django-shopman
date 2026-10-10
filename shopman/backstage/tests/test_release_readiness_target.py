"""Modo alvo do production-readiness: lê o spec vivo e as sondas, nada local."""

from __future__ import annotations

import json

from scripts import check_release_readiness as readiness
from scripts import release_readiness_target as target

_RELEASE = (
    "sh -c 'python manage.py check --deploy && python manage.py migration_safety "
    "&& python manage.py migrate --noinput && python manage.py setup_groups'"
)


def _spec(app_envs: dict[str, str], *, release: str = _RELEASE, service_envs=None) -> dict:
    return {
        "name": "shopman-nelson",
        "envs": [{"key": key, "value": value, "scope": "RUN_TIME"} for key, value in app_envs.items()],
        "services": [
            {
                "name": "web-storefront",
                "run_command": "daphne -b 0.0.0.0 -p 8000 config.asgi",
                "envs": [{"key": k, "value": v} for k, v in (service_envs or {}).items()],
            },
            # Nuxt não roda Django: o env dele não entra na regra.
            {"name": "storefront-nuxt", "envs": [{"key": "SHOPMAN_ENVIRONMENT", "value": "staging"}]},
        ],
        "workers": [{"name": "directive-worker", "run_command": "python manage.py process_directives --watch"}],
        "jobs": [{"name": "release", "kind": "PRE_DEPLOY", "run_command": release}],
    }


_TODAY = {
    "DJANGO_DEBUG": "false",
    "SHOPMAN_ENVIRONMENT": "staging",
    "SHOPMAN_PIX_ADAPTER": "shopman.shop.adapters.payment_mock",
    "SHOPMAN_CARD_ADAPTER": "shopman.shop.adapters.payment_stripe",
    "EFI_SANDBOX": "true",
    "SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS": "true",
    "SHOPMAN_EXPOSE_MOCK_CAPTURE": "true",
    "SHOPMAN_EXPOSE_DEBUG_OTP": "false",
    "STRIPE_PUBLISHABLE_KEY": "pk_test_abc",
    "DJANGO_SECRET_KEY": "EV[1:cifrado]",
}

_FLIPPED = {
    "DJANGO_DEBUG": "false",
    "SHOPMAN_ENVIRONMENT": "production",
    "SHOPMAN_PIX_ADAPTER": "shopman.shop.adapters.payment_efi",
    "SHOPMAN_CARD_ADAPTER": "shopman.shop.adapters.payment_stripe",
    "EFI_SANDBOX": "false",
    "FOCUS_NFE_ENVIRONMENT": "producao",
    "STRIPE_PUBLISHABLE_KEY": "pk_live_abc",
    "SHOPMAN_ADMIN_REQUIRE_2FA": "true",
    "SHOPMAN_GO_LIVE": "true",
}


def _healthy(url: str) -> tuple[int, str]:
    if url.endswith("/ready/"):
        return 200, json.dumps({"status": "ok", "checks": {"database": "ok", "cache": "ok", "migrations": "ok"}})
    return 200, "ok"


def _by_id(report) -> dict:
    return {check.id: check for check in report.checks}


def test_todays_live_spec_fails_with_every_rehearsal_key_named():
    report = target.build_target_report(_spec(_TODAY), fetch=_healthy)
    checks = _by_id(report)

    assert report.profile == "production" and report.read_only and report.strict_external
    assert report.blocking
    assert checks["production.profile"].status == "failed"
    change = checks["production.profile"].details["change"]
    assert "SHOPMAN_ENVIRONMENT=production (hoje staging)" in change
    assert "real_payment_adapter_for_pix (SHOPMAN_PIX_ADAPTER)" in change
    assert "remove_SHOPMAN_EXPOSE_MOCK_CAPTURE" in change
    assert checks["production.profile"].details["components"] == ["directive-worker", "release", "web-storefront"]
    money = checks["target.money_and_fiscal"].details["change"]
    assert any(item.startswith("EFI_SANDBOX=false") for item in money)
    assert any("default homologacao" in item for item in money)
    assert any(item.startswith("STRIPE_PUBLISHABLE_KEY") for item in money)
    assert checks["target.cutover_switches"].status == "failed"
    assert checks["target.release_job"].status == "passed"
    assert checks["target.health"].status == "passed"
    assert checks["target.ready"].status == "passed"


def test_flipped_spec_passes_the_target_gate():
    report = target.build_target_report(_spec(_FLIPPED), fetch=_healthy)

    assert not report.blocking, [check.as_dict() for check in report.checks if check.status != "passed"]
    assert report.status == "passed"


def test_absent_money_keys_fail_closed_because_the_settings_defaults_are_rehearsal():
    envs = {key: value for key, value in _FLIPPED.items() if key not in {"EFI_SANDBOX", "FOCUS_NFE_ENVIRONMENT"}}
    check = _by_id(target.build_target_report(_spec(envs), fetch=_healthy))["target.money_and_fiscal"]

    assert check.status == "failed"
    assert "EFI_SANDBOX=false (hoje ausente, default true)" in check.details["change"]


def test_component_override_is_judged_not_hidden_by_the_app_level_value():
    spec = _spec(_FLIPPED, service_envs={"SHOPMAN_EXPOSE_MOCK_CAPTURE": "true"})
    check = _by_id(target.build_target_report(spec, fetch=_healthy))["production.profile"]

    assert check.status == "failed"
    assert check.details["components"] == ["web-storefront"]


def test_secret_values_are_never_read_and_downgrade_to_warning():
    envs = {**_FLIPPED, "STRIPE_PUBLISHABLE_KEY": "EV[1:cifrado]"}
    report = target.build_target_report(_spec(envs), fetch=_healthy)
    check = _by_id(report)["target.money_and_fiscal"]

    assert check.status == "warning"
    assert "EV[" not in json.dumps(report.as_dict())


def test_release_job_without_migration_safety_before_migrate_fails():
    unguarded = "sh -c 'python manage.py migrate --noinput && python manage.py migration_safety'"
    check = _by_id(target.build_target_report(_spec(_FLIPPED, release=unguarded), fetch=_healthy))["target.release_job"]

    assert check.status == "failed"


def test_ready_with_a_failing_dependency_fails_even_on_200():
    def degraded(url: str) -> tuple[int, str]:
        if url.endswith("/ready/"):
            return 200, json.dumps({"checks": {"database": "ok", "queue": "stale"}})
        return 200, "ok"

    def offline(url: str) -> tuple[int, str]:
        raise OSError("sem rede")

    assert _by_id(target.build_target_report(_spec(_FLIPPED), fetch=degraded))["target.ready"].status == "failed"
    offline_checks = _by_id(target.build_target_report(_spec(_FLIPPED), fetch=offline))
    assert offline_checks["target.health"].status == "failed"
    assert offline_checks["target.ready"].status == "failed"


def test_main_target_reads_a_spec_file_and_never_sets_up_django(tmp_path, monkeypatch, capsys):
    import yaml

    spec_file = tmp_path / "vivo.yaml"
    spec_file.write_text(yaml.safe_dump(_spec(_TODAY)), encoding="utf-8")
    monkeypatch.setattr(target, "http_get", _healthy)
    monkeypatch.setattr(readiness, "setup_django", lambda: (_ for _ in ()).throw(AssertionError("Django local")))

    exit_code = readiness.main(["--target", "--target-spec", str(spec_file), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["target"] is True
    assert payload["profile"] == "production"
    assert {check["id"] for check in payload["checks"]} >= {"target.spec", "production.profile", "target.ready"}


def test_main_target_fails_closed_when_the_spec_cannot_be_read(monkeypatch, capsys):
    def broken(**kwargs):
        raise RuntimeError("doctl ausente")

    monkeypatch.setattr(target, "fetch_live_spec", broken)

    exit_code = readiness.main(["--target"])

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "[FAIL] target.spec" in out
    assert "doctl ausente" in out
