#!/usr/bin/env python
"""Confere o spec VERSIONADO contra o app VIVO na DigitalOcean, antes do update.

A armadilha que este script existe para desarmar, medida em 05/09/2026: o
``.do/app.alpha-subdomains.yaml`` tinha 73 envs e o app vivo tinha 95. As 22 de
diferença estavam configuradas só no painel — entre elas TODO o e-mail, a
emissão fiscal inteira e o NF-e de Compras com o certificado e-CNPJ.

``doctl apps update --spec`` não faz merge: o spec que você manda **passa a ser
o spec**. Chave que existe só no vivo é apagada, em silêncio, sem confirmação e
sem linha no log. O deploy sobe verde e o e-mail para de sair.

Este script não conserta nada e não escreve em lugar nenhum — ele **lê os dois
lados e mostra a diferença**, para que a decisão de rodar o update seja tomada
com a lista na frente. É de propósito somente-leitura: um script que
"sincroniza sozinho" seria uma segunda forma de perder configuração.

    python scripts/check_do_spec_drift.py                        # detecta o app pelo nome
    python scripts/check_do_spec_drift.py --app-id <uuid>
    python scripts/check_do_spec_drift.py --spec .do/app.subdomains.yaml
    python scripts/check_do_spec_drift.py --live-spec /tmp/vivo.yaml   # sem doctl

Saída: chaves só no vivo (**as que sumiriam**), chaves só no versionado (as que
nasceriam), e divergência de valor/escopo/tipo nas que existem dos dois lados.
Sai com 1 quando há qualquer diferença — é gate de conferência manual, não de
CI: a CI não tem (nem deve ter) credencial da DigitalOcean.

⚠️ Valor de segredo nunca é comparado nem impresso. No spec do vivo ele vem
cifrado (``EV[1:...]``) e no versionado não existe por política — comparar
produziria "divergente" sempre, e imprimir seria vazar.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover - o .venv da raiz tem PyYAML
    print("PyYAML ausente — rode com .venv/bin/python", file=sys.stderr)
    raise SystemExit(2) from exc

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Nome do app no App Platform por spec versionado. `doctl apps list` devolve
#: o `spec.name`, que é o campo `name:` do topo do próprio arquivo.
DEFAULT_SPEC = REPO_ROOT / ".do" / "app.alpha-subdomains.yaml"

#: Chaves que existem NO ARQUIVO e não no vivo **de propósito**, com a razão.
#:
#: Sem esta lista o drift nunca fecha: as duas apareceriam como "nasceriam" para
#: sempre, e um relatório que nunca fica limpo deixa de ser lido — a próxima
#: divergência de verdade chega no meio de um ruído que todo mundo já aprendeu a
#: ignorar. Uma diferença deliberada precisa ser *declarada* como deliberada,
#: não tolerada em silêncio.
#:
#: ⚠️ Só vale para o lado "nasceriam". Chave que existe no vivo e não no arquivo
#: **apaga** no update, e para essa direção não há allowlist nenhuma.
EXPECTED_ONLY_VERSIONED: dict[str, str] = {
    "FOCUS_NFE_ENVIRONMENT": (
        "declarada explícita no arquivo; o vivo não a tem e cai no default do "
        "settings.py, que é o mesmo `homologacao`. Aplicar não muda comportamento."
    ),
    "SENTRY_DSN": (
        "SECRET sem valor, esperando o opt-in de docs/runbooks/ativar-sentry.md. "
        "Sem DSN o settings.py não inicializa o Sentry."
    ),
}


def load_spec(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def app_id_for(name: str) -> str | None:
    result = subprocess.run(
        ["doctl", "apps", "list", "--format", "ID,Spec.Name", "--no-header"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == name:
            return parts[0]
    return None


def fetch_live_spec(app_id: str) -> dict:
    result = subprocess.run(
        ["doctl", "apps", "spec", "get", app_id],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"doctl apps spec get falhou: {result.stderr.strip()}")
    return yaml.safe_load(result.stdout) or {}


def env_index(spec: dict) -> dict[str, dict]:
    """Envs de nível de APP, por chave.

    Env de serviço (as ``NUXT_*`` de cada superfície) fica de fora de propósito:
    ela é comparada por serviço, e misturar as duas escalas faria toda chave
    homônima de dois serviços parecer divergente.
    """
    return {entry["key"]: entry for entry in spec.get("envs", []) if "key" in entry}


def service_env_index(spec: dict) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for service in spec.get("services", []) or []:
        name = service.get("name") or "?"
        out[name] = {entry["key"]: entry for entry in service.get("envs", []) or [] if "key" in entry}
    return out


def domain_index(spec: dict) -> dict[str, str]:
    """Domínios por hostname → `"<type> zone=<zone>"`.

    Env não é a única coisa que o update apaga. Medido em 08/09/2026: o arquivo
    trazia `alpha.nelsonboulangerie.com.br` como PRIMARY — um domínio **morto**
    desde o corte de 01/09 — e **não** trazia `backup.boulangerie.com.br`, que
    estava no ar. Um update teria ressuscitado o morto e apagado o vivo, e o
    drift-check, que só olhava env, teria dito "OK".
    """
    out: dict[str, str] = {}
    for entry in spec.get("domains", []) or []:
        name = entry.get("domain")
        if name:
            out[name] = f"{entry.get('type') or 'ALIAS'} zone={entry.get('zone') or '-'}"
    return out


def ingress_index(spec: dict) -> dict[str, str]:
    """Regras de ingress por autoridade → componente que a serve.

    Comparado como **conjunto**, não como lista ordenada: o painel acrescenta
    regra no fim e o arquivo agrupa por leitura, então a ordem diverge sem que
    nada de real mude. O que importa é *quem serve cada host* — e se a regra
    catch-all (sem autoridade) existe.
    """
    out: dict[str, str] = {}
    for rule in (spec.get("ingress") or {}).get("rules", []) or []:
        match = rule.get("match") or {}
        authority = match.get("authority") or {}
        host = authority.get("exact") or authority.get("prefix") or "<catch-all>"
        path = (match.get("path") or {}).get("prefix") or "/"
        out[f"{host} {path}"] = (rule.get("component") or {}).get("name") or "?"
    return out


def env_type(entry: dict) -> str:
    """`GENERAL` é o default do App Platform, e o `doctl` OMITE o campo quando
    é ele. Sem esta normalização, toda env comum do vivo apareceria como
    "type diverge — vivo=None versionado='GENERAL'": cinquenta linhas de ruído
    que enterrariam as poucas divergências de verdade.
    """
    return (entry.get("type") or "GENERAL").upper()


def is_secret(entry: dict) -> bool:
    return env_type(entry) == "SECRET"


def compare_plain(
    live: dict[str, str], versioned: dict[str, str], *, label: str, unit: str
) -> list[str]:
    """Compara mapa simples (domínio→tipo, autoridade→componente)."""
    problems: list[str] = []

    only_live = sorted(set(live) - set(versioned))
    if only_live:
        problems.append(f"  ⛔ SUMIRIAM no `apps update` — {unit} no vivo e NÃO no arquivo ({label}):")
        problems.extend(f"       {key} → {live[key]}" for key in only_live)

    only_versioned = sorted(set(versioned) - set(live))
    if only_versioned:
        problems.append(f"  ➕ nasceriam — {unit} no arquivo e não no vivo ({label}):")
        problems.extend(f"       {key} → {versioned[key]}" for key in only_versioned)

    for key in sorted(set(live) & set(versioned)):
        if live[key] != versioned[key]:
            problems.append(
                f"  ⚠️ {key}: diverge — vivo={live[key]!r} versionado={versioned[key]!r}"
            )
    return problems


def compare(
    live: dict[str, dict],
    versioned: dict[str, dict],
    *,
    label: str,
    expected_only_versioned: dict[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    """`(problemas, esperado)`. Problemas vazios significa "os dois lados batem"."""
    problems: list[str] = []
    expected: list[str] = []
    declared = expected_only_versioned or {}

    only_live = sorted(set(live) - set(versioned))
    only_versioned = sorted(key for key in set(versioned) - set(live) if key not in declared)
    for key in sorted(key for key in set(versioned) - set(live) if key in declared):
        expected.append(f"  ✅ {key}: só no arquivo, de propósito — {declared[key]}")

    if only_live:
        problems.append(
            f"  ⛔ SUMIRIAM no `apps update` — existem no vivo e NÃO no spec versionado ({label}):"
        )
        problems.extend(f"       {key}" for key in only_live)

    if only_versioned:
        problems.append(f"  ➕ nasceriam — existem no spec versionado e não no vivo ({label}):")
        problems.extend(f"       {key}" for key in only_versioned)

    for key in sorted(set(live) & set(versioned)):
        left, right = live[key], versioned[key]
        if is_secret(left) or is_secret(right):
            # Valor de segredo nunca é comparado nem impresso. Só o
            # enquadramento (é segredo dos dois lados?) importa aqui.
            if is_secret(left) != is_secret(right):
                problems.append(
                    f"  ⚠️ {key}: `type` diverge — vivo={env_type(left)} versionado={env_type(right)}"
                )
            continue
        if env_type(left) != env_type(right):
            problems.append(
                f"  ⚠️ {key}: `type` diverge — vivo={env_type(left)} versionado={env_type(right)}"
            )
        for field in ("value", "scope"):
            if left.get(field) != right.get(field):
                problems.append(
                    f"  ⚠️ {key}: `{field}` diverge — vivo={left.get(field)!r} "
                    f"versionado={right.get(field)!r}"
                )
    return problems, expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Drift entre o spec versionado e o app vivo")
    parser.add_argument("--spec", default=str(DEFAULT_SPEC), help="spec versionado a conferir")
    parser.add_argument("--app-id", default=None, help="UUID do app (default: acha pelo `name:` do spec)")
    parser.add_argument(
        "--live-spec",
        default=None,
        help="arquivo com o spec do vivo já baixado (pula o doctl)",
    )
    args = parser.parse_args(argv)

    spec_path = Path(args.spec)
    if not spec_path.is_absolute():
        spec_path = REPO_ROOT / spec_path
    if not spec_path.is_file():
        print(f"spec não encontrado: {spec_path}", file=sys.stderr)
        return 2

    versioned = load_spec(spec_path)

    if args.live_spec:
        live = load_spec(Path(args.live_spec))
        origin = args.live_spec
    else:
        app_id = args.app_id or app_id_for(versioned.get("name", ""))
        if not app_id:
            print(
                f"app '{versioned.get('name')}' não encontrado via doctl.\n"
                "Autentique (`doctl auth init`) ou passe --app-id / --live-spec.",
                file=sys.stderr,
            )
            return 2
        try:
            live = fetch_live_spec(app_id)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        origin = f"app {app_id}"

    # `relative_to` estoura para caminho fora do repo, e conferir um spec salvo
    # em /tmp é justamente o que se faz ao comparar duas versões do arquivo.
    try:
        shown = spec_path.relative_to(REPO_ROOT)
    except ValueError:
        shown = spec_path
    print(f"Spec versionado : {shown}")
    print(f"App vivo        : {origin}")
    print(
        f"envs de app     : vivo={len(env_index(live))} versionado={len(env_index(versioned))}"
    )
    print(
        f"domínios        : vivo={len(domain_index(live))} versionado={len(domain_index(versioned))}"
    )

    problems, expected = compare(
        env_index(live),
        env_index(versioned),
        label="envs de app",
        expected_only_versioned=EXPECTED_ONLY_VERSIONED,
    )

    live_services, versioned_services = service_env_index(live), service_env_index(versioned)
    for name in sorted(set(live_services) | set(versioned_services)):
        service_problems, service_expected = compare(
            live_services.get(name, {}),
            versioned_services.get(name, {}),
            label=f"serviço {name}",
        )
        problems.extend(service_problems)
        expected.extend(service_expected)

    problems.extend(
        compare_plain(
            domain_index(live), domain_index(versioned), label="domínios", unit="hostnames"
        )
    )
    problems.extend(
        compare_plain(
            ingress_index(live),
            ingress_index(versioned),
            label="ingress",
            unit="regras de roteamento",
        )
    )

    if expected:
        print("\nDiferenças declaradas como esperadas (não são drift):")
        for line in expected:
            print(line)
        print()

    if not problems:
        print("- [OK] spec_drift: o spec versionado descreve o app vivo inteiro.")
        return 0

    print("- [FAIL] spec_drift: o spec versionado NÃO descreve o app vivo.")
    for line in problems:
        print(line)
    print(
        "\n⛔ NÃO rode `doctl apps update --spec` enquanto houver linha em SUMIRIAM:\n"
        "   o update substitui o spec inteiro, não faz merge. Env, DOMÍNIO e regra\n"
        "   de ingress somem do mesmo jeito. Traga a coisa para o arquivo primeiro\n"
        "   (segredo entra como `type: SECRET` SEM `value` — o valor cifrado que já\n"
        "   está no painel permanece).\n"
        "   Ver docs/runbooks/conferir-spec-digitalocean.md."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
