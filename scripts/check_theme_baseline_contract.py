#!/usr/bin/env python3
"""O tema compartilhado do operator-kit mudou? Então as baselines foram regeradas?

## O defeito que este gate existe para impedir

O operator-kit é uma layer Nuxt consumida por extends. O tema que ele define
(app/app.config.ts e os CSS de token em app/assets/css/) não pertence ao kit:
pertence a TODA app que o herda. Quando o tema muda, a mesma alteração reaparece
nas baselines visuais das consumidoras (Marketing, POS) sem que ninguém tenha
tocado nelas. Medido em 2026-10-05/06: um app.config.ts novo no kit deixou 4
baselines de Marketing diferentes e o job "Marketing — cadeia completa" vermelho
por um PR que não era de Marketing.

E o inverso é pior: baseline regenerada "para o CI voltar a ficar verde", sem
dono, sem antes/depois e sem entender o que mudou. Baseline cega esconde
regressão em vez de registrá-la.

## O que este gate faz

O aceite do tema vive versionado em
docs/reference/operator-theme-baseline-contract.json. O arquivo guarda o
fingerprint do tema e a lista de apps cujas baselines dependem dele. Este gate:

1. Reprova quando o conjunto de arquivos de tema em disco difere do contrato
   (arquivo novo de tema não pode entrar sem ser declarado);
2. Reprova quando o fingerprint do tema difere do aceito — ou seja, o tema mudou
   e as baselines das consumidoras precisam ser regeradas NO MESMO PR;
3. Reprova quando uma app consumidora declarada no contrato perdeu o diretório
   de baselines (consumidor fantasma).

O aceite é regravado com --accept --owner "<quem aceitou>", e SÓ depois de as
baselines afetadas terem sido regeradas e revisadas. O aceite não regenera
baseline: ele registra que um humano revisou o antes/depois. O processo está em
docs/reference/operator-visual-baselines.md.

## Uso

    python scripts/check_theme_baseline_contract.py            # gate
    python scripts/check_theme_baseline_contract.py --json     # saída para máquina
    python scripts/check_theme_baseline_contract.py --accept --owner "WP-UX-13E"

⚠️ --accept sem --owner é recusado. Aceite anônimo é a baseline cega de volta.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path("docs/reference/operator-theme-baseline-contract.json")

# Fontes do tema compartilhado. O glob de CSS é de propósito: arquivo novo em
# app/assets/css/ é tema até prova em contrário, e precisa entrar no contrato.
THEME_FILES = (
    Path("surfaces/operator-kit/app/app.config.ts"),
)
THEME_CSS_GLOB = "surfaces/operator-kit/app/assets/css/*.css"

# Apps que herdam a layer e mantêm baselines visuais. Derivado, não escrito à mão:
# uma app que passa a ter tests/visual/baselines entra sozinha.
CONSUMER_LOCKSTEP = "operator-kit"


def discovered_theme_sources() -> list[str]:
    sources = [str(path) for path in THEME_FILES]
    sources.extend(
        str(path.relative_to(ROOT)) for path in sorted(ROOT.glob(THEME_CSS_GLOB))
    )
    return sorted(sources)


def discovered_consumers() -> list[dict]:
    consumers: list[dict] = []
    for baselines in sorted(ROOT.glob("surfaces/*/tests/visual/baselines")):
        if not any(baselines.glob("*.png")):
            continue
        app = baselines.parents[2].name
        config = baselines.parents[2] / "nuxt.config.ts"
        if not config.is_file():
            continue
        if CONSUMER_LOCKSTEP not in config.read_text(encoding="utf-8"):
            continue
        consumers.append(
            {
                "app": app,
                "baselines": str(baselines.relative_to(ROOT)),
            }
        )
    return consumers


def fingerprint(sources: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in sources:
        path = ROOT / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if path.is_file():
            digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        else:
            digest.update(b"ABSENT")
        digest.update(b"\n")
    return "sha256:" + digest.hexdigest()


def load_contract() -> dict:
    if not CONTRACT.is_file():
        raise FileNotFoundError(
            f"contrato ausente: {CONTRACT}. Rode --accept --owner para criar."
        )
    return json.loads((ROOT / CONTRACT).read_text(encoding="utf-8"))


def write_contract(contract: dict) -> None:
    (ROOT / CONTRACT).write_text(
        json.dumps(contract, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def compare(contract: dict) -> dict:
    sources = discovered_theme_sources()
    consumers = discovered_consumers()
    current = fingerprint(sources)
    declared_sources = sorted(contract.get("themeSources") or [])
    declared_consumers = contract.get("consumers") or []
    return {
        "sources": sources,
        "declaredSources": declared_sources,
        "consumers": consumers,
        "declaredConsumers": declared_consumers,
        "current": current,
        "accepted": contract.get("themeFingerprint"),
        "sourcesDrift": sorted(set(sources) ^ set(declared_sources)),
        "consumersDrift": sorted(
            {item["app"] for item in consumers}
            ^ {item["app"] for item in declared_consumers}
        ),
        "fingerprintDrift": current != contract.get("themeFingerprint"),
    }


def report(state: dict) -> int:
    problems = []
    if state["sourcesDrift"]:
        problems.append(
            "arquivos de tema fora do contrato: " + ", ".join(state["sourcesDrift"])
        )
    if state["consumersDrift"]:
        problems.append(
            "apps consumidoras fora do contrato: " + ", ".join(state["consumersDrift"])
        )
    if state["fingerprintDrift"]:
        problems.append(
            "tema mudou desde o último aceite "
            f"({state['current']} != {state['accepted']})"
        )
    if not problems:
        consumers = ", ".join(item["app"] for item in state["consumers"])
        print(
            f"✓ Tema do operator-kit casado com o aceite das baselines "
            f"({state['current']}; consumidoras: {consumers})"
        )
        return 0

    print("── Tema compartilhado do operator-kit × baselines ──\n", file=sys.stderr)
    print("O contrato do tema reprovou:\n", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    print(
        "\n  O tema do kit é herdado por extends: mudá-lo repinta as baselines das\n"
        "  consumidoras. Regere as baselines afetadas NO MESMO PR, revise o antes/depois\n"
        "  com o dono e regrave o aceite:\n\n"
        '    make theme-baselines-accept owner="<quem aceitou>"\n\n'
        "  Baseline não se regenera cega: sem o antes/depois revisado, o aceite é a\n"
        "  regressão escondida. Processo em docs/reference/operator-visual-baselines.md.\n",
        file=sys.stderr,
    )
    return 1


def accept(owner: str, date: str) -> int:
    if not owner.strip():
        print('uso: --accept --owner "<quem aceitou>"', file=sys.stderr)
        return 2
    contract = load_contract()
    sources = discovered_theme_sources()
    contract["themeSources"] = sources
    contract["consumers"] = discovered_consumers()
    contract["themeFingerprint"] = fingerprint(sources)
    contract["acceptedOn"] = date
    contract["owner"] = owner.strip()
    write_contract(contract)
    print(f"aceite do tema regravado: {contract['themeFingerprint']} ({contract['acceptedOn']})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accept", action="store_true")
    parser.add_argument("--owner", default="")
    parser.add_argument("--date", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.date:
        date = args.date
    else:
        from datetime import date as _date

        date = _date.today().isoformat()

    if args.accept:
        return accept(args.owner, date)

    try:
        contract = load_contract()
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    state = compare(contract)
    if args.json:
        print(json.dumps(state, indent=2, ensure_ascii=False))
        return 1 if (
            state["sourcesDrift"] or state["consumersDrift"] or state["fingerprintDrift"]
        ) else 0
    return report(state)


if __name__ == "__main__":
    raise SystemExit(main())
