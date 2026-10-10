"""Prontidão de produção lida no ALVO: spec vivo do App Platform + sondas públicas.

O ``check_release_readiness.py`` sem este modo mede a árvore e o banco LOCAIS —
o ``settings`` que ele carrega é o do processo que o roda, não o do app vivo.
Para a linha ``production-readiness`` da matriz canônica a pergunta é outra:
*o app que atende a loja está configurado para dinheiro de verdade?* Isso se
responde lendo o que o app vivo de fato recebe:

- o spec vivo, via ``doctl apps spec get`` (só leitura; nenhum ``update``);
- ``/health/`` e ``/ready/`` do domínio da API.

Nada aqui importa Django nem toca banco. Valor de segredo nunca é lido nem
impresso: no spec ele vem cifrado (``EV[...]``) e aparece como ``<segredo>``;
uma regra que dependa de valor secreto vira ``warning`` (não dá para afirmar)
em vez de ``passed``.

As regras de chave são UMA tabela só, o ``DELTA`` de
``scripts/golive_spec_delta.py`` (o mesmo que lista o que colar no painel no
dia D, com o runbook ``docs/runbooks/go-live-delta-do-spec.md``). Aqui ela vira
quatro checks (perfil, dinheiro e nota, chaves do corte, chaves já em dia), e
este módulo acrescenta o que não é chave: o job de release e as sondas.
Ausência de ``EFI_SANDBOX``/``FOCUS_NFE_ENVIRONMENT`` reprova, porque os
defaults do settings são de ensaio.
"""

from __future__ import annotations

import json
import re
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from scripts import golive_spec_delta as delta

DEFAULT_APP_NAME = "shopman-nelson"
DEFAULT_TARGET_URL = "https://api.boulangerie.com.br"

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


# ── Regras (tabela única do delta) ───────────────────────────────────────────


def change_line(finding) -> str:
    """Uma linha por chave fora do valor de produção, sem valor de segredo."""
    key, rule, today = finding.row.key, finding.rule, finding.today
    if rule.kind in {"equals", "equals_or_absent"}:
        return f"{key}={rule.value} (hoje {today})"
    if rule.kind == "true":
        return f"{key}=true (hoje {today})"
    if rule.kind in {"off", "absent"}:
        return f"apagar {key} (hoje {today})"
    if rule.kind == "prefix":
        return f"{key} {rule.value}… (hoje {today[:8]})"
    if rule.kind == "rotated":
        return f"{key}: colar o valor de produção"
    return f"{key}: falta"


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


def _delta_check(check_id: str, title: str, ok_message: str, fail_message: str, findings, grupo: str):
    """Um check do relatório = um grupo de linhas da tabela do delta.

    ``virar`` reprova; ``sem_prova`` (segredo que o spec não deixa ler, ou
    troca de segredo sem ``--target-baseline``) vira aviso: não dá para
    afirmar, então não passa calado nem reprova o que pode estar certo.
    Limpeza não entra no gate.
    """
    from scripts.check_release_readiness import ReadinessCheck

    group = [finding for finding in findings if finding.row.grupo == grupo]
    failing = [finding for finding in group if finding.status == "virar"]
    unknown = [finding for finding in group if finding.status == "sem_prova"]
    if failing:
        details: dict[str, object] = {
            "change": [change_line(finding) for finding in failing],
            "components": sorted({name for finding in failing for name in finding.where}),
        }
        if unknown:
            details["unknown"] = [change_line(finding) for finding in unknown]
        return ReadinessCheck(id=check_id, title=title, status="failed", message=fail_message, details=details)
    if unknown:
        return ReadinessCheck(
            id=check_id,
            title=title,
            status="warning",
            message="Sem como afirmar pelo spec: segredo que não se lê, ou troca sem --target-baseline.",
            details={"unknown": [change_line(finding) for finding in unknown]},
        )
    return ReadinessCheck(id=check_id, title=title, status="passed", message=ok_message)


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
    baseline_spec: dict | None = None,
):
    """Relatório ``production`` sobre o alvo. Sempre estrito: é o gate do corte."""
    from scripts.check_release_readiness import ReadinessCheck, ReadinessReport

    components = delta.django_components(spec)
    findings = delta.evaluate(spec, baseline_spec=baseline_spec) if components else []
    checks = [
        ReadinessCheck(
            id="target.spec",
            title="Target spec read",
            status="passed" if components else "failed",
            message=f"Spec do app {spec.get('name') or '?'} lido ({source or 'arquivo'}); {len(components)} componentes Django.",
            details={"components": sorted(components)},
        ),
        _delta_check(
            "production.profile",
            "Production flip profile (target)",
            "Nenhum interruptor de ensaio ligado no app vivo.",
            "O app vivo ainda roda com interruptores de ensaio.",
            findings,
            "profile",
        ),
        _delta_check(
            "target.money_and_fiscal",
            "Real money and real invoices",
            "Efí, Focus e Stripe apontam para produção no app vivo.",
            "Cobrança ou nota ainda em ambiente de ensaio no app vivo.",
            findings,
            "money",
        ),
        _delta_check(
            "target.cutover_switches",
            "Cutover switches",
            "2FA do Admin e SHOPMAN_GO_LIVE ligados no app vivo.",
            "Faltam as chaves que só se ligam no corte.",
            findings,
            "cutover",
        ),
        _delta_check(
            "target.in_place",
            "Production keys already in place",
            "As chaves que os checks de produção exigem seguem no valor.",
            "Uma chave que já estava no valor de produção saiu dele.",
            findings,
            "in_place",
        ),
        release_job_check(spec),
        *probe_checks(base_url, fetch or http_get),
    ]
    return ReadinessReport(checks=tuple(checks), strict_external=True, profile="production", read_only=True)
