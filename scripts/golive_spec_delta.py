#!/usr/bin/env python
"""O que ainda falta virar no spec vivo para a loja ser produção (dia D).

A virada acontece no PRÓPRIO app vivo ``shopman-nelson``, no mesmo banco
(D-029, decisão do dono B1 = 1): nada de app novo, só chaves do spec trocadas
no painel. Este script lê o spec vivo, compara com a tabela :data:`DELTA` e
imprime, chave por chave, o que já está no valor do dia D e o que falta.

A tabela humana, com o porquê, a verificação e o caminho de volta de cada
chave, é ``docs/runbooks/go-live-delta-do-spec.md``; um teste prende as duas
listas juntas, para que uma não ande sem a outra.

    .venv/bin/python scripts/golive_spec_delta.py                         # dia D, spec vivo
    .venv/bin/python scripts/golive_spec_delta.py --baseline antes.yaml   # prova a troca dos segredos
    .venv/bin/python scripts/golive_spec_delta.py --etapa ensaio-pix      # D-031: Pix real em sandbox
    .venv/bin/python scripts/golive_spec_delta.py --live-spec vivo.yaml   # sem doctl

Somente leitura: nenhum ``apps update``, nenhum valor de segredo lido ou
impresso. Segredo vem cifrado no spec (``EV[...]``); o script só olha se ele
existe e, com ``--baseline`` (o spec guardado na abertura da janela), se o
cifrado MUDOU, que é o sinal de que o dono colou um valor novo. Mudar o
cifrado não prova que o valor é de produção: quem prova é o release job
(``check --deploy`` com SHOPMAN_E022 recusa chave de teste em produção).

Cada chave é conferida em CADA processo Django do app (serviços web, workers e
o job de release), com o env de componente por cima do env do app, que é como
o App Platform entrega. Assim um worker com ``SHOPMAN_ENVIRONMENT=staging``
esquecido no próprio componente aparece como pendência: virada pela metade.

Saída: 0 quando tudo o que é obrigatório está no valor da etapa; 1 quando
falta virar alguma chave; 2 quando o spec não pôde ser lido.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    import yaml
except ImportError as exc:  # pragma: no cover - o .venv da raiz tem PyYAML
    print("PyYAML ausente: rode com .venv/bin/python", file=sys.stderr)
    raise SystemExit(2) from exc

#: O app vivo (``shopman-nelson``) e o contexto do doctl que lê o spec inteiro.
DEFAULT_APP_ID = "40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f"
DEFAULT_CONTEXT = "shopman-do-app-admin"

ETAPAS = ("dia-d", "ensaio-pix")

#: Valores que o settings lê como "desligado" (``_env_bool`` liga só com
#: true/1/yes). Qualquer outro valor conta como LIGADO aqui: na dúvida, a
#: chave aparece como pendência, nunca como pronta.
_OFF_VALUES = {"", "0", "false", "no", "off"}
_TRUE_VALUES = {"true", "1", "yes"}

#: Componentes que rodam Django. Os Nuxt não leem estas chaves.
_DJANGO_MARKERS = ("manage.py", "config.asgi", "config.wsgi")

#: Valor longo (lista de origens, resolvers) é cortado na tela: a linha é para
#: ler de relance, e quem precisa do valor inteiro tem o spec.
_SHOWN_MAX = 60


@dataclass(frozen=True)
class Rule:
    """O valor que uma chave precisa ter numa etapa.

    ``kind``:
    - ``equals``: valor exato (``value``);
    - ``equals_or_absent``: valor exato, ou a chave ausente (default do settings já serve);
    - ``true`` / ``off``: booleano ligado / desligado ou ausente;
    - ``absent``: a chave não pode existir;
    - ``prefix``: valor (não secreto) começa com ``value``;
    - ``present``: a chave existe com valor (segredo ou não);
    - ``rotated``: segredo presente E com cifrado diferente do ``--baseline``.
    """

    kind: str
    value: str = ""

    def describe(self) -> str:
        return {
            "equals": f"{self.value}",
            "equals_or_absent": f"{self.value} (ou ausente)",
            "true": "true",
            "off": "ausente (ou false)",
            "absent": "ausente",
            "prefix": f"{self.value}… (o dono cola)",
            "present": "presente (não muda)",
            "rotated": "segredo NOVO (o dono cola no painel)",
        }[self.kind]


@dataclass(frozen=True)
class Row:
    key: str
    dia_d: Rule
    #: Regra na etapa ``ensaio-pix`` (D-031). ``None``: não se confere no ensaio.
    ensaio_pix: Rule | None = None
    #: ``False`` = limpeza: desejável no dia D, mas sem efeito em runtime.
    obrigatoria: bool = True
    #: Restringe a conferência a estes componentes (por nome). Vazio = todos os Django.
    componentes: tuple[str, ...] = field(default_factory=tuple)
    #: Check do ``production-readiness target=1`` que reúne esta linha:
    #: ``profile`` (interruptores de ensaio), ``money`` (cobrança e nota),
    #: ``cutover`` (só se liga no corte) ou ``in_place`` (já em dia, não pode sair).
    grupo: str = "in_place"

    def rule(self, etapa: str) -> Rule | None:
        return self.dia_d if etapa == "dia-d" else self.ensaio_pix


_PIX_EFI = "shopman.shop.adapters.payment_efi"
_STRIPE = "shopman.shop.adapters.payment_stripe"
_FOCUS = "shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend"
_HMAC_COMPONENTS = ("web-operator", "web-storefront", "release")

#: A tabela do dia D. Mesma ordem e mesmas chaves de
#: ``docs/runbooks/go-live-delta-do-spec.md`` (o teste confere).
DELTA: tuple[Row, ...] = (
    # ── O que vira ──────────────────────────────────────────────────────────
    Row("SHOPMAN_ENVIRONMENT", Rule("equals", "production"), Rule("equals", "staging"), grupo="profile"),
    Row("SHOPMAN_PIX_ADAPTER", Rule("equals", _PIX_EFI), Rule("equals", _PIX_EFI), grupo="profile"),
    Row("EFI_SANDBOX", Rule("equals", "false"), Rule("equals", "true"), grupo="money"),
    Row("EFI_CLIENT_ID", Rule("rotated"), Rule("present"), grupo="money"),
    Row("EFI_CLIENT_SECRET", Rule("rotated"), Rule("present"), grupo="money"),
    Row("EFI_CERTIFICATE_PEM_BASE64", Rule("rotated"), Rule("present"), grupo="money"),
    Row("EFI_PIX_KEY", Rule("present"), Rule("present"), grupo="money"),
    Row("EFI_WEBHOOK_TOKEN", Rule("rotated"), Rule("present"), grupo="money"),
    Row("SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS", Rule("off"), grupo="profile"),
    Row("SHOPMAN_EXPOSE_MOCK_CAPTURE", Rule("off"), Rule("off"), grupo="profile"),
    Row("SHOPMAN_MOCK_PIX_AUTO_CONFIRM", Rule("off"), Rule("off"), grupo="profile"),
    Row("SHOPMAN_MOCK_PIX_CONFIRM_DELAY_SECONDS", Rule("absent"), obrigatoria=False, grupo="profile"),
    Row("STRIPE_PUBLISHABLE_KEY", Rule("prefix", "pk_live_"), grupo="money"),
    Row("STRIPE_SECRET_KEY", Rule("rotated"), grupo="money"),
    Row("STRIPE_WEBHOOK_SECRET", Rule("rotated"), grupo="money"),
    Row("FOCUS_NFE_ENVIRONMENT", Rule("equals", "producao"), grupo="money"),
    Row("FOCUS_NFE_TOKEN", Rule("rotated"), grupo="money"),
    Row("SHOPMAN_ADMIN_REQUIRE_2FA", Rule("true"), grupo="cutover"),
    Row("SHOPMAN_GO_LIVE", Rule("true"), grupo="cutover"),
    # ── O que já está no valor de produção e não pode sair dele ─────────────
    Row("DJANGO_DEBUG", Rule("off"), grupo="profile"),
    Row("DJANGO_SECURE_SSL_REDIRECT", Rule("true")),
    Row("SHOPMAN_CARD_ADAPTER", Rule("equals", _STRIPE), grupo="profile"),
    Row("SHOPMAN_LINK_ADAPTER", Rule("equals_or_absent", _STRIPE), grupo="money"),
    Row("SHOPMAN_FISCAL_ADAPTER", Rule("equals", _FOCUS), grupo="money"),
    Row("SHOPMAN_FISCAL_EMISSION_RESOLVER", Rule("present"), grupo="money"),
    Row("FOCUS_NFE_BASE_URL", Rule("absent"), grupo="money"),
    Row("SHOPMAN_EXPOSE_DEBUG_OTP", Rule("off"), Rule("off"), grupo="profile"),
    Row("SHOPMAN_STAGING_AUTOPILOT", Rule("off"), Rule("off"), grupo="profile"),
    Row("SHOPMAN_ENABLE_CONSOLE_NOTIFICATION_ADAPTER", Rule("off"), grupo="profile"),
    Row("SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM", Rule("off"), grupo="profile"),
    Row("GOOGLE_MAPS_API_KEY", Rule("absent")),
    Row("GOOGLE_MAPS_BROWSER_API_KEY", Rule("present")),
    Row("GOOGLE_MAPS_SERVER_API_KEY", Rule("present")),
    Row("DJANGO_SECRET_KEY", Rule("present")),
    Row("DJANGO_ALLOWED_HOSTS", Rule("present")),
    Row("CSRF_TRUSTED_ORIGINS", Rule("present")),
    Row("DATABASE_URL", Rule("equals", "${postgres.shopman-staging-pool.DATABASE_URL}")),
    Row("REDIS_URL", Rule("present")),
    Row("SHOPMAN_OPERATOR_COOKIE_DOMAIN", Rule("present")),
    Row("DOORMAN_ACCESS_LINK_API_KEY", Rule("present")),
    Row("COMTELE_API_KEY", Rule("present")),
    Row("COMTELE_ROUTE", Rule("present")),
    Row("EMAIL_HOST", Rule("present")),
    Row("SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY", Rule("present"), componentes=_HMAC_COMPONENTS),
)


# ── Leitura ──────────────────────────────────────────────────────────────────


def django_components(spec: dict) -> dict[str, dict]:
    """Componentes que rodam Django, por nome (serviços, workers e jobs)."""
    out: dict[str, dict] = {}
    for kind in ("services", "workers", "jobs"):
        for component in spec.get(kind) or []:
            command = str(component.get("run_command") or "")
            if any(marker in command for marker in _DJANGO_MARKERS):
                out[component.get("name") or "?"] = component
    return out


def _runs_at_runtime(entry: dict) -> bool:
    return str(entry.get("scope") or "RUN_AND_BUILD_TIME").upper() in {"RUN_TIME", "RUN_AND_BUILD_TIME"}


def effective_envs(spec: dict, component: dict) -> dict[str, dict]:
    """Env que o processo recebe: o do app, com o do componente por cima."""
    envs: dict[str, dict] = {}
    for entry in [*(spec.get("envs") or []), *(component.get("envs") or [])]:
        if "key" in entry and _runs_at_runtime(entry):
            envs[entry["key"]] = entry
    return envs


def _is_secret(entry: dict) -> bool:
    if str(entry.get("value") or "").startswith("EV["):
        return True
    return str(entry.get("type") or "GENERAL").upper() == "SECRET"


def shown(entry: dict | None) -> str:
    """O valor para a tela. Segredo nunca: só ``<segredo>``."""
    if entry is None:
        return "ausente"
    if _is_secret(entry):
        return "<segredo>"
    value = str(entry.get("value", ""))
    return value if len(value) <= _SHOWN_MAX else value[: _SHOWN_MAX - 1] + "…"


# ── Comparação ───────────────────────────────────────────────────────────────


def satisfied(rule: Rule, entry: dict | None, baseline: dict | None) -> bool | None:
    """``True``/``False``; ``None`` quando não dá para afirmar (segredo que o spec não deixa ler)."""
    raw = None if entry is None else str(entry.get("value", ""))
    norm = (raw or "").strip().lower()
    if rule.kind == "equals":
        return raw is not None and raw.strip() == rule.value
    if rule.kind == "equals_or_absent":
        return entry is None or (raw or "").strip() == rule.value
    if rule.kind == "true":
        return entry is not None and norm in _TRUE_VALUES
    if rule.kind == "off":
        return entry is None or norm in _OFF_VALUES
    if rule.kind == "absent":
        return entry is None
    if rule.kind == "prefix":
        if entry is not None and _is_secret(entry):
            return None  # cifrado: não dá para ler o prefixo
        return entry is not None and (raw or "").strip().startswith(rule.value)
    if rule.kind == "present":
        return entry is not None and bool((raw or "").strip())
    if rule.kind == "rotated":
        if entry is None or not (raw or "").strip():
            return False
        if baseline is None:
            return None
        return str(baseline.get("value", "")) != raw
    raise ValueError(f"regra desconhecida: {rule.kind}")


@dataclass(frozen=True)
class Finding:
    row: Row
    rule: Rule
    #: ``ok`` | ``virar`` | ``sem_prova`` | ``limpeza``
    status: str
    #: componente → valor mostrado, só onde a regra NÃO se cumpre.
    where: dict[str, str]
    today: str
    #: ``True`` quando só PARTE dos processos Django descumpre (override de componente).
    partial: bool = False


def evaluate(spec: dict, *, etapa: str = "dia-d", baseline_spec: dict | None = None) -> list[Finding]:
    if etapa not in ETAPAS:
        raise ValueError(f"etapa desconhecida: {etapa}")
    components = django_components(spec)
    if not components:
        raise RuntimeError("o spec não tem nenhum componente Django (run_command com manage.py/config.asgi)")
    baseline_components = django_components(baseline_spec) if baseline_spec else {}

    findings: list[Finding] = []
    for row in DELTA:
        rule = row.rule(etapa)
        if rule is None:
            continue
        names = [name for name in components if not row.componentes or name in row.componentes]
        failing: dict[str, str] = {}
        unproven = False
        values: set[str] = set()
        for name in names:
            entry = effective_envs(spec, components[name]).get(row.key)
            values.add(shown(entry))
            base_entry = None
            if baseline_spec is not None:
                base_component = baseline_components.get(name)
                base_envs = effective_envs(baseline_spec, base_component) if base_component else {}
                base_entry = base_envs.get(row.key, {})
            verdict = satisfied(rule, entry, base_entry if baseline_spec is not None else None)
            if verdict is None:
                unproven = True
            elif not verdict:
                failing[name] = shown(entry)
        today = " | ".join(sorted(values)) if values else "ausente"
        if failing:
            status = "virar" if row.obrigatoria else "limpeza"
        elif unproven:
            status = "sem_prova"
        else:
            status = "ok"
        partial = bool(failing) and len(failing) < len(names)
        findings.append(Finding(row=row, rule=rule, status=status, where=failing, today=today, partial=partial))
    return findings


def paste_line(finding: Finding) -> str:
    """O que o dono faz no painel para esta chave."""
    key, rule = finding.row.key, finding.rule
    if rule.kind in {"equals", "equals_or_absent"}:
        return f"{key} = {rule.value}"
    if rule.kind == "true":
        return f"{key} = true"
    if rule.kind in {"off", "absent"}:
        return f"apagar {key}"
    if rule.kind == "prefix":
        return f"{key} = {rule.value}… (colar o valor do painel do provedor)"
    if rule.kind == "rotated":
        return f"{key} = valor novo, tipo Encrypt (colar o de produção do provedor)"
    return f"{key}: presente com valor (hoje falta)"


def render(findings: list[Finding], *, etapa: str, has_baseline: bool) -> tuple[str, int]:
    lines = [f"Delta do spec vivo para a etapa {etapa!r} (somente leitura)", ""]
    label = {"ok": "[OK]", "virar": "[VIRAR]", "sem_prova": "[SEM PROVA]", "limpeza": "[LIMPEZA]"}
    for finding in findings:
        where = ""
        if finding.partial:
            # Virada pela metade: só parte dos processos está fora do valor.
            where = " | só em: " + ", ".join(f"{name}={value}" for name, value in sorted(finding.where.items()))
        lines.append(
            f"{label[finding.status]:<12} {finding.row.key}: hoje {finding.today} → {finding.rule.describe()}{where}"
        )

    pending = [f for f in findings if f.status in {"virar", "sem_prova"}]
    cleanup = [f for f in findings if f.status == "limpeza"]
    lines.append("")
    if pending:
        lines.append(
            f"Falta virar {len(pending)} chave(s). No painel do app, Settings → App-Level Environment Variables:"
        )
        lines.extend(f"  - {paste_line(f)}" for f in pending)
    else:
        lines.append("Nada obrigatório pendente para esta etapa.")
    if cleanup:
        lines.append("Limpeza (sem efeito em runtime, apagar junto):")
        lines.extend(f"  - {paste_line(f)}" for f in cleanup)
    if any(f.status == "sem_prova" for f in findings) and not has_baseline:
        lines.append(
            "[SEM PROVA] = segredo presente, mas sem --baseline não há como saber se foi trocado. "
            "Rode com --baseline <spec guardado na abertura da janela>."
        )
    return "\n".join(lines), (1 if pending else 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--etapa", choices=ETAPAS, default="dia-d")
    parser.add_argument("--app-id", default=DEFAULT_APP_ID)
    parser.add_argument("--context", default=DEFAULT_CONTEXT, help="contexto do doctl ('' = o padrão)")
    parser.add_argument("--live-spec", help="ler o spec de um arquivo em vez do doctl")
    parser.add_argument("--baseline", help="spec guardado antes da troca, para provar que os segredos mudaram")
    args = parser.parse_args(argv)

    # Um leitor só: o mesmo do `production-readiness target=1`.
    from scripts import release_readiness_target as target

    try:
        spec = (
            target.load_spec_file(args.live_spec)
            if args.live_spec
            else target.fetch_live_spec(app=args.app_id, context=args.context or None)
        )
        baseline = target.load_spec_file(args.baseline) if args.baseline else None
        findings = evaluate(spec, etapa=args.etapa, baseline_spec=baseline)
    except (OSError, RuntimeError, yaml.YAMLError) as exc:
        print(f"golive-spec-delta: não consegui ler o spec: {exc}", file=sys.stderr)
        return 2

    text, code = render(findings, etapa=args.etapa, has_baseline=baseline is not None)
    print(text)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
