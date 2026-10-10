"""Prontidão de produção lida no ALVO: spec vivo do App Platform + sondas públicas.

O ``check_release_readiness.py`` sem este modo mede a árvore e o banco LOCAIS —
o ``settings`` que ele carrega é o do processo que o roda, não o do app vivo.
Para a linha ``production-readiness`` da matriz canônica a pergunta é outra:
*o app que atende a loja está configurado para dinheiro de verdade?* Isso se
responde lendo o que o app vivo de fato recebe:

- o spec vivo, via ``doctl apps spec get`` (só leitura; nenhum ``update``);
- ``/health/`` e ``/ready/`` do domínio da API.

Nada aqui importa Django nem toca banco. Valor de segredo nunca é lido nem
impresso: no spec ele vem cifrado (``EV[...]``) e entra no relatório como
``<secret>``; uma regra que dependa de valor secreto vira ``warning`` (não dá
para afirmar) em vez de ``passed``.

As regras espelham o perfil ``production`` do relatório local
(``_production_profile_check``) e acrescentam as chaves de dinheiro e de nota
que o settings decide por default (``EFI_SANDBOX`` nasce ``true``,
``FOCUS_NFE_ENVIRONMENT`` nasce ``homologacao``) — ausência no spec é, por
isso, reprovação, não neutralidade.
"""

from __future__ import annotations

import json
import re
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

DEFAULT_APP_NAME = "shopman-nelson"
DEFAULT_TARGET_URL = "https://api.boulangerie.com.br"

_TRUE = {"1", "true", "yes", "on"}
_PRODUCTION_ENVIRONMENTS = {"production", "prod", "live"}
_SECRET = "<secret>"

#: Interruptores de ensaio que não podem chegar ligados à produção. Mesma lista
#: do ``_production_profile_check`` local.
_TEST_SWITCHES = (
    "SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS",
    "SHOPMAN_EXPOSE_MOCK_CAPTURE",
    "SHOPMAN_MOCK_PIX_AUTO_CONFIRM",
    "SHOPMAN_EXPOSE_DEBUG_OTP",
    "SHOPMAN_STAGING_AUTOPILOT",
)

Fetcher = Callable[[str], tuple[int, str]]

_MIGRATION_SAFETY = re.compile(r"manage\.py\s+migration_safety\b")
_MIGRATE = re.compile(r"manage\.py\s+migrate\b")


# ── Leitura do alvo ──────────────────────────────────────────────────────────


def _doctl(*args: str, context: str | None) -> list[str]:
    return ["doctl", *(["--context", context] if context else []), *args]


def fetch_live_spec(*, app: str = DEFAULT_APP_NAME, context: str | None = None) -> dict:
    """Spec vivo pelo ``doctl``. Aceita nome do app ou UUID. Só leitura."""
    import yaml

    app_id = app
    if len(app) != 36 or app.count("-") != 4:
        listing = subprocess.run(
            _doctl("apps", "list", "--format", "ID,Spec.Name", "--no-header", context=context),
            capture_output=True,
            text=True,
            check=False,
        )
        if listing.returncode != 0:
            raise RuntimeError(f"doctl apps list falhou: {listing.stderr.strip()}")
        matches = [line.split()[0] for line in listing.stdout.splitlines() if line.split()[1:2] == [app]]
        if not matches:
            raise RuntimeError(f"app {app!r} não encontrado via doctl (contexto {context or 'padrão'})")
        app_id = matches[0]
    result = subprocess.run(
        _doctl("apps", "spec", "get", app_id, "--format", "yaml", context=context),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"doctl apps spec get falhou: {result.stderr.strip()}")
    return yaml.safe_load(result.stdout) or {}


def load_spec_file(path: str | Path) -> dict:
    import yaml

    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def http_get(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "shopman-release-readiness/target"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - URL https declarada
            return response.status, response.read(4096).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(4096).decode("utf-8", "replace")


# ── Ambiente efetivo por componente ──────────────────────────────────────────


def _runs_at_runtime(entry: dict) -> bool:
    return str(entry.get("scope") or "RUN_AND_BUILD_TIME").upper() in {"RUN_TIME", "RUN_AND_BUILD_TIME"}


def _value(entry: dict) -> str:
    raw = str(entry.get("value") if entry.get("value") is not None else "")
    if raw.startswith("EV[") or str(entry.get("type") or "").upper() == "SECRET":
        return _SECRET
    return raw


def _env_map(entries) -> dict[str, str]:
    return {entry["key"]: _value(entry) for entry in entries or [] if entry.get("key") and _runs_at_runtime(entry)}


def django_components(spec: dict) -> dict[str, dict[str, str]]:
    """Ambiente efetivo (app + componente) de cada componente que roda Django."""
    base = _env_map(spec.get("envs"))
    components: dict[str, dict[str, str]] = {}
    for section in ("services", "workers", "jobs"):
        for component in spec.get(section) or []:
            command = str(component.get("run_command") or "")
            if "manage.py" not in command and "config.asgi" not in command and "config.wsgi" not in command:
                continue
            components[component["name"]] = {**base, **_env_map(component.get("envs"))}
    return components


def _is_true(value: str | None) -> bool:
    return str(value or "").strip().lower() in _TRUE


# ── Regras ───────────────────────────────────────────────────────────────────


def profile_violations(env: dict[str, str]) -> list[str]:
    """Mesmas regras do perfil ``production`` local, sobre o env do spec."""
    failures: list[str] = []
    debug = _is_true(env.get("DJANGO_DEBUG"))
    if debug:
        failures.append("DJANGO_DEBUG=false")
    # Ausente fora de DEBUG, o settings cai em production (falha fechado).
    environment = (env.get("SHOPMAN_ENVIRONMENT") or ("development" if debug else "production")).strip().lower()
    if environment not in _PRODUCTION_ENVIRONMENTS:
        failures.append(f"SHOPMAN_ENVIRONMENT=production (hoje {environment})")
    for switch in _TEST_SWITCHES:
        if _is_true(env.get(switch)):
            failures.append(f"remove_{switch}")
    for method, key in (("pix", "SHOPMAN_PIX_ADAPTER"), ("card", "SHOPMAN_CARD_ADAPTER")):
        if "payment_mock" in str(env.get(key) or ""):
            failures.append(f"real_payment_adapter_for_{method} ({key})")
    return failures


def money_and_fiscal_violations(env: dict[str, str]) -> tuple[list[str], list[str]]:
    """Chaves cujo default no settings é de ensaio: ausência reprova."""
    failures: list[str] = []
    unknown: list[str] = []
    efi_sandbox = env.get("EFI_SANDBOX")
    if efi_sandbox is None or efi_sandbox.strip().lower() in {"true", "1", "yes"}:
        failures.append(f"EFI_SANDBOX=false (hoje {efi_sandbox or 'ausente, default true'})")
    focus = env.get("FOCUS_NFE_ENVIRONMENT")
    if (focus or "homologacao").strip().lower() != "producao":
        failures.append(f"FOCUS_NFE_ENVIRONMENT=producao (hoje {focus or 'ausente, default homologacao'})")
    stripe = env.get("STRIPE_PUBLISHABLE_KEY")
    if stripe == _SECRET:
        unknown.append("STRIPE_PUBLISHABLE_KEY é secreta no spec: não dá para ler se é pk_live_")
    elif not str(stripe or "").startswith("pk_live_"):
        failures.append(f"STRIPE_PUBLISHABLE_KEY pk_live_ (hoje {str(stripe or 'ausente')[:8]})")
    return failures, unknown


def cutover_switch_violations(env: dict[str, str]) -> list[str]:
    failures: list[str] = []
    if not _is_true(env.get("SHOPMAN_ADMIN_REQUIRE_2FA")):
        failures.append("SHOPMAN_ADMIN_REQUIRE_2FA=true (cadastrar o 2FA de todo staff antes)")
    if not _is_true(env.get("SHOPMAN_GO_LIVE")):
        failures.append("SHOPMAN_GO_LIVE=true (arma a trava de migração do ADR-015)")
    return failures


def release_job_check(spec: dict):
    from scripts.check_release_readiness import ReadinessCheck

    jobs = [job for job in spec.get("jobs") or [] if str(job.get("kind") or "").upper() == "PRE_DEPLOY"]
    guarded = []
    for job in jobs:
        command = str(job.get("run_command") or "")
        safety = _MIGRATION_SAFETY.search(command)
        migrate = _MIGRATE.search(command)
        if safety and migrate and safety.start() < migrate.start():
            guarded.append(job.get("name"))
    if guarded:
        return ReadinessCheck(
            id="target.release_job",
            title="Release job guarded by migration_safety",
            status="passed",
            message="O job de release roda migration_safety antes do migrate.",
            details={"jobs": guarded},
        )
    return ReadinessCheck(
        id="target.release_job",
        title="Release job guarded by migration_safety",
        status="failed",
        message="Nenhum job PRE_DEPLOY roda migration_safety antes do migrate.",
        details={"jobs": [job.get("name") for job in jobs]},
    )


def _component_rule_check(check_id: str, title: str, ok_message: str, fail_message: str, components, rule):
    from scripts.check_release_readiness import ReadinessCheck

    per_component = {name: rule(env) for name, env in components.items()}
    offending = {name: failures for name, failures in per_component.items() if failures}
    if not components:
        return ReadinessCheck(
            id=check_id,
            title=title,
            status="failed",
            message="O spec não tem componente Django para avaliar.",
        )
    if not offending:
        return ReadinessCheck(id=check_id, title=title, status="passed", message=ok_message)
    distinct = sorted({failure for failures in offending.values() for failure in failures})
    return ReadinessCheck(
        id=check_id,
        title=title,
        status="failed",
        message=fail_message,
        details={"change": distinct, "components": sorted(offending)},
    )


def _money_check(components):
    from scripts.check_release_readiness import ReadinessCheck

    failures: set[str] = set()
    unknown: set[str] = set()
    for env in components.values():
        component_failures, component_unknown = money_and_fiscal_violations(env)
        failures.update(component_failures)
        unknown.update(component_unknown)
    if failures:
        return ReadinessCheck(
            id="target.money_and_fiscal",
            title="Real money and real invoices",
            status="failed",
            message="Cobrança ou nota ainda em ambiente de ensaio no app vivo.",
            details={"change": sorted(failures), **({"unknown": sorted(unknown)} if unknown else {})},
        )
    if unknown:
        return ReadinessCheck(
            id="target.money_and_fiscal",
            title="Real money and real invoices",
            status="warning",
            message="Cobrança e nota em produção, com chave que o spec não deixa ler.",
            details={"unknown": sorted(unknown)},
        )
    return ReadinessCheck(
        id="target.money_and_fiscal",
        title="Real money and real invoices",
        status="passed",
        message="Efí, Focus e Stripe apontam para produção no app vivo.",
    )


def probe_checks(base_url: str, fetch: Fetcher) -> tuple:
    from scripts.check_release_readiness import ReadinessCheck

    base = base_url.rstrip("/")
    checks = []
    try:
        health_status, _ = fetch(f"{base}/health/")
    except Exception as exc:  # noqa: BLE001 - qualquer falha de rede reprova a sonda
        health_status = f"erro: {exc.__class__.__name__}"
    checks.append(
        ReadinessCheck(
            id="target.health",
            title="Target /health/",
            status="passed" if health_status == 200 else "failed",
            message=f"{base}/health/ respondeu {health_status}.",
        )
    )
    try:
        ready_status, body = fetch(f"{base}/ready/")
    except Exception as exc:  # noqa: BLE001
        ready_status, body = f"erro: {exc.__class__.__name__}", ""
    try:
        ready_checks = json.loads(body).get("checks") or {}
    except (ValueError, AttributeError):
        ready_checks = {}
    not_ok = sorted(name for name, value in ready_checks.items() if value != "ok")
    ready_passed = ready_status == 200 and bool(ready_checks) and not not_ok
    checks.append(
        ReadinessCheck(
            id="target.ready",
            title="Target /ready/",
            status="passed" if ready_passed else "failed",
            message=f"{base}/ready/ respondeu {ready_status}.",
            details={"checks": ready_checks} if ready_checks else {},
        )
    )
    return tuple(checks)


def build_target_report(
    spec: dict,
    *,
    base_url: str = DEFAULT_TARGET_URL,
    fetch: Fetcher | None = None,
    source: str = "",
):
    """Relatório ``production`` sobre o alvo. Sempre estrito: é o gate do corte."""
    from scripts.check_release_readiness import ReadinessCheck, ReadinessReport

    components = django_components(spec)
    checks = [
        ReadinessCheck(
            id="target.spec",
            title="Target spec read",
            status="passed",
            message=f"Spec do app {spec.get('name') or '?'} lido ({source or 'arquivo'}); {len(components)} componentes Django.",
            details={"components": sorted(components)},
        ),
        _component_rule_check(
            "production.profile",
            "Production flip profile (target)",
            "Nenhum interruptor de ensaio ligado no app vivo.",
            "O app vivo ainda roda com interruptores de ensaio.",
            components,
            profile_violations,
        ),
        _money_check(components),
        _component_rule_check(
            "target.cutover_switches",
            "Cutover switches",
            "2FA do Admin e SHOPMAN_GO_LIVE ligados no app vivo.",
            "Faltam as chaves que só se ligam no corte.",
            components,
            cutover_switch_violations,
        ),
        release_job_check(spec),
        *probe_checks(base_url, fetch or http_get),
    ]
    return ReadinessReport(checks=tuple(checks), strict_external=True, profile="production", read_only=True)
