#!/usr/bin/env python
"""As superfícies Nuxt compartilhadas estão todas na MESMA versão?

## Por que este guard existe

A decisão do dono (18/09/2026) é curta: **as versões estáveis mais recentes, e a
MESMA versão em todos os apps do ecossistema**. Alinhar uma vez não sustenta isso
— já derivou antes e voltaria a derivar no PR seguinte.

A medição de 19/09/2026 mostrou POR QUE deriva, e a causa não é descuido de quem
escreve código:

1. O `purchase-nuxt` nunca esteve em `.github/dependabot.yml`. Ele entra no
   `surfaces-gate.yml` (é testado) e não entra na cadência de atualização (nunca
   sobe). Resultado medido: atrasado em 16 pacotes ao mesmo tempo, com `vue`,
   `eslint`, `happy-dom`, `vue-router`, `@vue/test-utils`, `tailwind-merge`,
   `motion-v` e `@iconify-json/lucide` TRAVADOS em versão mais velha que os
   irmãos. Não foi uma escolha; foi ausência de mecanismo.
2. O pino exato do `operator-kit` (`@iconify-json/lucide`, sem `^`) tira o kit
   dos grupos do Dependabot, que passam a cobrir 9 diretórios em vez de 10 e
   produzem PRs parciais.

## O que este script confere — e por que confere DUAS coisas

Faixa declarada (`package.json`) **e** versão travada (`package-lock.json`).

Conferir só a faixa deixaria passar o defeito mais caro, e isto foi MEDIDO em
19/09/2026: `@nuxt/test-utils` está em `^4.0.3` nos dez apps — faixa idêntica,
nenhum alarme — e o lock tem `4.0.3` em três apps e `4.1.0` nos outros sete. O
mesmo vale para `@nuxt/eslint` (`^1.16.0` declarado em nove; lock com `1.16.0` e
`1.17.0`) e para o `@nuxt/icon`, que vai de `2.2.2` a `2.5.1` com faixa uniforme.
O `npm ci` do CI e do deploy instala o LOCK, não a faixa: é o lock que diz o que
roda no ar.

E conferir só o lock deixaria passar o inverso, que é a deriva de amanhã: o
`vitest` do `purchase-nuxt` declara `^4.0.14` contra `^4.1.11` dos irmãos, e o
lock coincide em 4.1.11 só porque a última resolução subiu junto. Faixa larga
demais é permissão para divergir no próximo `npm install`.

## Como a lista de pacotes compartilhados é montada

Não há lista escrita à mão. Lista à mão apodrece: um pacote novo entra em nove
apps e o guard não sabe que ele existe. O script deriva do que ESTÁ nos
`package.json`: todo pacote declarado por dois ou mais apps de `surfaces/` é
compartilhado e precisa concordar.

A `surfaces/operator-router` cai fora sozinha, sem exceção escrita: ela declara
zero dependências de propósito ("só a biblioteca padrão do Node", ADR-030), então
não compartilha pacote com ninguém e o script não tem o que comparar nela.

## Exceção é declarada, com motivo — nunca silenciosa

`EXCEPTIONS` exige motivo por escrito. Exceção sem motivo é a próxima deriva
travestida de decisão, então o próprio script recusa uma entrada com motivo
vazio. E exceção autoriza DIVERGIR, não FICAR PARA TRÁS: um app excetuado que
envelhece atrás dos irmãos volta a ser reportado.

## Uso

    python scripts/check_surface_versions.py          # falha se houver deriva
    python scripts/check_surface_versions.py --fix    # alinha as FAIXAS
    python scripts/check_surface_versions.py --json   # saída para máquina

⚠️ `--fix` mexe só no `package.json`. O lock é do npm: depois do `--fix`, rode
`npm install` no app tocado e verifique o `npm ci && npm run lint && npm test`
antes do PR. O `npm ci` é o que o CI roda e é mais rígido que o `npm install`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SURFACES = ROOT / "surfaces"

DEPENDENCY_FIELDS = ("dependencies", "devDependencies")


# ── Exceções declaradas ──────────────────────────────────────────────────────
#
# Chave: (app, pacote). Valor: o motivo, por extenso. Sem motivo, o script para.
#
# Quem adicionar uma entrada aqui está dizendo "esta divergência é deliberada e
# eu assino embaixo". Se o motivo não couber numa frase, provavelmente não é
# exceção — é deriva procurando permissão.
EXCEPTIONS: dict[tuple[str, str], str] = {
    ("operator-kit", "@iconify-json/lucide"): (
        "Pino EXATO (sem `^`) na layer compartilhada: o kit define o conjunto de "
        "ícones que os nove apps herdam por `extends`, e faixa aberta na layer "
        "deixaria o mesmo nome de ícone resolver para arquivos diferentes em "
        "apps diferentes na mesma leva. ⚠️ O preço está medido: pino exato tira "
        "o kit dos grupos do Dependabot, que passam a cobrir 9 diretórios em vez "
        "de 10 — é daí que vêm os PRs parciais (#723). Subir o kit é passo "
        "manual, e a versão dele nunca pode ficar ABAIXO da dos apps."
    ),
}


def missing_reason_message(key: tuple[str, str]) -> str:
    return (
        f"EXCEPTIONS[{key!r}] está sem motivo escrito.\n"
        f"    Exceção sem motivo vira a próxima deriva. Escreva por que este app "
        f"pode divergir, ou remova a entrada e alinhe a versão."
    )


def load_surfaces() -> dict[str, dict]:
    """Lê cada `surfaces/*/package.json` e o lock ao lado dele."""
    surfaces: dict[str, dict] = {}
    for manifest in sorted(SURFACES.glob("*/package.json")):
        name = manifest.parent.name
        data = json.loads(manifest.read_text())

        declared: dict[str, str] = {}
        for field in DEPENDENCY_FIELDS:
            declared.update(data.get(field) or {})

        locked: dict[str, str] = {}
        lockfile = manifest.parent / "package-lock.json"
        if lockfile.exists():
            packages = json.loads(lockfile.read_text()).get("packages") or {}
            for package in declared:
                entry = packages.get(f"node_modules/{package}")
                if entry and entry.get("version"):
                    locked[package] = entry["version"]

        surfaces[name] = {
            "manifest": manifest,
            "declared": declared,
            "locked": locked,
            "has_lockfile": lockfile.exists(),
        }
    return surfaces


def sort_key(specifier: str) -> tuple:
    """Ordena `^4.1.11` / `1.2.133` por número, não por string.

    Sem isto `^1.2.9` ganharia de `^1.2.11` na comparação textual.
    """
    numbers = re.findall(r"\d+", specifier)
    return tuple(int(n) for n in numbers[:4]) or (0,)


def reference_version(versions: dict[str, str]) -> str:
    """A versão de referência: a MAIS ALTA entre as presentes. Nunca a maioria.

    A primeira versão deste guard elegia a versão mais comum, e isso estava
    errado — a decisão do dono tem duas metades ("as versões estáveis mais
    recentes, E a mesma versão em todos os apps"), e maioria só atende a
    segunda. Na medição de 19/09/2026 a diferença era concreta: o `@nuxt/eslint`
    está em 1.17.0 no `bi-nuxt` e no `purchase-nuxt` contra 1.16.0 em sete
    irmãos, e o `@nuxt/icon` chega a 2.5.1 no `purchase-nuxt` contra 2.2.2 em
    cinco. Por maioria, o guard mandaria REBAIXAR os dois — alinhados e velhos,
    exatamente o oposto do que foi decidido.

    Alinhar para cima também é o único lado seguro: descer versão reintroduz
    correção já aplicada e some com API que o código irmão pode já usar.
    """
    return max(versions.values(), key=sort_key)


def audit(surfaces: dict[str, dict]) -> list[dict]:
    """Toda divergência entre apps que declaram o mesmo pacote."""
    shared: Counter = Counter()
    for data in surfaces.values():
        shared.update(data["declared"].keys())

    findings: list[dict] = []
    for package, surface_count in sorted(shared.items()):
        if surface_count < 2:
            continue  # não é compartilhado: nada com que concordar

        for dimension, key in (("faixa", "declared"), ("lock", "locked")):
            versions = {
                name: data[key][package]
                for name, data in surfaces.items()
                if package in data[key]
            }
            # Um app sem lock ainda não instalou; o gate de faixa já o cobre.
            if len(versions) < 2:
                continue

            # A referência sai dos apps SEM exceção. O app excetuado não pode
            # ditar a versão dos irmãos: o pino exato do `operator-kit`
            # (`1.2.133`, sem `^`) é deliberado NA LAYER, e deixá-lo entrar no
            # cálculo mandava os nove apps trocarem `^1.2.132` por um pino
            # literal que ninguém pediu — a exceção de um virando regra de todos.
            regular = {
                name: version
                for name, version in versions.items()
                if (name, package) not in EXCEPTIONS
            }
            if not regular:
                continue

            expected = reference_version(regular)
            for name, version in sorted(versions.items()):
                if version == expected:
                    continue

                # Exceção autoriza DIVERGIR, não FICAR PARA TRÁS. Um app
                # excetuado que envelhece atrás dos irmãos é a deriva usando a
                # exceção como esconderijo — e o motivo escrito para o kit diz
                # exatamente isto: a versão dele nunca fica abaixo da dos apps.
                excepted = (name, package) in EXCEPTIONS
                if excepted and sort_key(version) >= sort_key(expected):
                    continue

                findings.append(
                    {
                        "app": name,
                        "package": package,
                        "dimension": dimension,
                        "found": version,
                        "expected": expected,
                        "lagging_exception": excepted,
                        "agree": sorted(
                            n for n, v in regular.items() if v == expected
                        ),
                    }
                )
    return findings


def report(findings: list[dict]) -> None:
    by_app: dict[str, list[dict]] = {}
    for finding in findings:
        by_app.setdefault(finding["app"], []).append(finding)

    print("── Versões das superfícies ──\n")
    print(
        f"{len(findings)} divergência(s) em {len(by_app)} app(s). A regra é uma "
        f"versão só por pacote compartilhado, e é a mais alta.\n"
    )

    for app in sorted(by_app):
        print(f"  {app}")
        for finding in by_app[app]:
            where = (
                "package.json"
                if finding["dimension"] == "faixa"
                else "package-lock.json"
            )
            print(
                f"    {finding['package']}  ({where})\n"
                f"      tem     {finding['found']}\n"
                f"      deveria {finding['expected']}"
                f"   ← {', '.join(finding['agree'])}"
            )
            if finding["lagging_exception"]:
                print(
                    "      ⚠️ este app tem exceção declarada, mas exceção "
                    "autoriza divergir,\n         não ficar para trás. Suba-o."
                )
        print()

    declared_drift = sorted(
        {f["app"] for f in findings if f["dimension"] == "faixa"}
    )
    locked_drift = sorted({f["app"] for f in findings if f["dimension"] == "lock"})

    print("  O que fazer:\n")
    if declared_drift:
        print("    Faixa divergente (package.json) — alinhe e reinstale:")
        print("      python scripts/check_surface_versions.py --fix")
        for app in declared_drift:
            print(f"      (cd surfaces/{app} && npm install)")
        print()
    if locked_drift:
        print(
            "    Lock divergente (package-lock.json) — a faixa permite a versão "
            "certa,\n    mas o lock travou outra. Reinstale para ressincronizar:"
        )
        for app in locked_drift:
            targets = " ".join(
                f"{f['package']}@{f['expected'].lstrip('^~')}"
                for f in by_app[app]
                if f["dimension"] == "lock"
            )
            print(f"      (cd surfaces/{app} && npm install {targets})")
        print()
    print(
        "    Depois: `npm ci && npm run lint && npm test` no app tocado — o "
        "`npm ci`\n    é o que o CI roda e recusa lock inconsistente que o "
        "`npm install` aceita.\n"
    )
    print(
        "    Se a divergência for DELIBERADA, declare-a em EXCEPTIONS no topo "
        "de\n    scripts/check_surface_versions.py, COM o motivo escrito. "
        "Exceção sem\n    motivo o script recusa.\n"
    )


def apply_fix(surfaces: dict[str, dict], findings: list[dict]) -> int:
    """Reescreve as FAIXAS divergentes no package.json. Lock é com o npm."""
    targets = [f for f in findings if f["dimension"] == "faixa"]
    if not targets:
        print("Nada a corrigir nas faixas (divergência só no lock).")
        return 0

    by_app: dict[str, list[dict]] = {}
    for finding in targets:
        by_app.setdefault(finding["app"], []).append(finding)

    for app, items in sorted(by_app.items()):
        manifest = surfaces[app]["manifest"]
        data = json.loads(manifest.read_text())
        for item in items:
            for field in DEPENDENCY_FIELDS:
                if item["package"] in (data.get(field) or {}):
                    data[field][item["package"]] = item["expected"]
                    print(
                        f"  {app}: {item['package']} "
                        f"{item['found']} → {item['expected']}"
                    )
        manifest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    print(f"\n{len(targets)} faixa(s) alinhada(s).")
    print("⚠️ O lock NÃO foi tocado. Rode `npm install` em cada app acima.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix", action="store_true", help="alinha as faixas do package.json"
    )
    parser.add_argument("--json", action="store_true", help="saída para máquina")
    args = parser.parse_args()

    for key, reason in EXCEPTIONS.items():
        if not (reason or "").strip():
            print(missing_reason_message(key), file=sys.stderr)
            return 2

    surfaces = load_surfaces()
    if not surfaces:
        print(f"Nenhum package.json em {SURFACES}", file=sys.stderr)
        return 2

    findings = audit(surfaces)

    if args.json:
        print(json.dumps({"findings": findings}, indent=2, ensure_ascii=False))
        return 1 if findings else 0

    if args.fix:
        return apply_fix(surfaces, findings)

    if not findings:
        shared = {
            package
            for package, count in Counter(
                package for data in surfaces.values() for package in data["declared"]
            ).items()
            if count >= 2
        }
        print(
            f"✓ Versões das superfícies: {len(shared)} pacotes compartilhados "
            f"por {len(surfaces)} apps, faixa e lock concordando"
            + (f" ({len(EXCEPTIONS)} exceção declarada)" if EXCEPTIONS else "")
        )
        return 0

    report(findings)
    return 1


if __name__ == "__main__":
    sys.exit(main())
