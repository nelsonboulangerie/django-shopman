#!/usr/bin/env python3
"""Trava do custo dos testes: o que deixa a fila lenta não entra calado.

DEV-2026-098. Pedido do dono (25/11/2026): "NÃO DEIXAR que esse tipo de
'sacada' se perca... daqui a pouco termos shards, seeds e seja lá o que for
que esteja dado de um jeito que o trabalho fique lento". Até aqui as decisões
de desempenho da suíte viviam em comentário do Makefile e eram refeitas depois
do estrago (o shard `rest` foi rebalanceado à mão em 30/09 e 06/11, sempre
DEPOIS de estourar o teto e tirar PR da fila).

Três regras, todas determinísticas (nada de relógio, que oscila; o relógio é da
vigia agendada, `ci-time-watch.yml`, contra `scripts/ci-time-budget.json`):

1. **Seed completo é caro e contado.** Cada `call_command("seed", ...)` em
   teste custa de 25 a 75 s (dois anos de histórico). A contagem por arquivo
   fica congelada em `scripts/test-cost-baseline.json`: CRESCER reprova (use o
   catálogo/fixture que já existe, ou divida UM seed entre os testes que só
   leem; os de `--flush`/idempotência são os que precisam semear do zero) e,
   quando é mesmo necessário, se declara com `--update` no mesmo PR, onde o
   revisor vê. Diminuir passa e pede `--update` para a folga não ser reusada.
2. **Teste que semeia mora no shard dos que semeiam.** Arquivo que chama o
   seed completo dentro de `shopman/backstage/tests` precisa estar em
   `BACKSTAGE_SEED_TESTS` ou `BACKSTAGE_HEAVY_TESTS` (Makefile): no `rest`, ele
   vira o caminho crítico de novo.
3. **Shards equilibrados e completos.** Os shards partidos por peso
   (`scripts/test_shards.py`) cobrem cada arquivo exatamente uma vez, e a parte
   mais pesada não passa de `BALANCE_LIMIT` vezes a mais leve pelos pesos
   medidos em `scripts/test-shard-weights.json`. Peso de arquivo que não existe
   mais reprova (medição velha mente sobre o equilíbrio).

    python3 scripts/check_test_cost.py            # confere
    python3 scripts/check_test_cost.py --update   # regrava a baseline do seed
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from test_shards import WEIGHTS, expand, load_weights, partition  # noqa: E402

BASELINE = ROOT / "scripts" / "test-cost-baseline.json"
SEED_CALL = re.compile(r"""call_command\(\s*["']seed["']""")
SCAN = ("shopman", "packages", "config", "tools")
#: Parte mais pesada / mais leve, pelos pesos. 1,35 e não 1,25: medido em
#: 25/11, `test_nelson_seed_operational.py` sozinho é 56% do shard `seed`
#: (1.341 de 2.372 s), e a divisão é por arquivo — 1,30 é o piso. Passar disso
#: é arquivo novo pesado demais para a partição: mais partes, ou o `heavy`.
BALANCE_LIMIT = 1.35
BACKSTAGE_TESTS = "shopman/backstage/tests"


def test_files() -> list[Path]:
    out = []
    for top in SCAN:
        for p in (ROOT / top).rglob("*.py"):
            if "node_modules" in p.parts or ".venv" in p.parts:
                continue
            if p.name.startswith("test_") or p.name.endswith("_test.py") or "tests" in p.parts:
                out.append(p)
    return sorted(out)


def seed_calls() -> dict[str, int]:
    counts = {}
    for p in test_files():
        n = len(SEED_CALL.findall(p.read_text(errors="replace")))
        if n:
            counts[str(p.relative_to(ROOT))] = n
    return counts


def make_list(var: str) -> list[str]:
    """Lê uma lista do Makefile pelo próprio make (fonte única)."""
    out = subprocess.run(
        ["make", "-s", "--no-print-directory", f"print-{var}"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if out.returncode:
        raise SystemExit(f"check_test_cost: `make print-{var}` falhou:\n{out.stderr}")
    return out.stdout.split()


def shard_specs() -> list[tuple[str, list[str], list[str], int]]:
    """(nome, entradas, exclusões, partes) dos shards partidos por peso."""
    seed, heavy = make_list("BACKSTAGE_SEED_TESTS"), make_list("BACKSTAGE_HEAVY_TESTS")
    return [
        ("backstage-seed", seed, [], int(make_list("BACKSTAGE_SEED_PARTS")[0])),
        ("backstage-heavy", heavy, [], int(make_list("BACKSTAGE_HEAVY_PARTS")[0])),
        ("backstage-rest", [BACKSTAGE_TESTS], seed + heavy, int(make_list("BACKSTAGE_REST_PARTS")[0])),
        ("shop-rest", ["shopman/shop/tests"], make_list("SHOP_HEAVY_TESTS"), int(make_list("SHOP_REST_PARTS")[0])),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()

    problems: list[str] = []
    notes: list[str] = []

    # 1. seed completo contado
    now = seed_calls()
    if args.update:
        BASELINE.write_text(json.dumps({
            "_leia": [
                "Chamadas de call_command('seed', ...) por arquivo de teste (25 a 75 s cada).",
                "Crescer reprova em scripts/check_test_cost.py; só se regrava com --update, no PR, à vista do revisor.",
            ],
            "seed_calls": now,
        }, ensure_ascii=False, indent=1) + "\n")
        print(f"baseline regravada: {sum(now.values())} chamadas em {len(now)} arquivos")
        return 0
    base = json.loads(BASELINE.read_text())["seed_calls"] if BASELINE.exists() else {}
    for f in sorted(set(now) | set(base)):
        a, b = base.get(f, 0), now.get(f, 0)
        if b > a:
            problems.append(
                f"{f}: {b} chamada(s) do seed completo, a baseline tem {a}. Cada uma custa 25–75 s na fila. "
                "Reaproveite o catálogo/fixture que já existe; se for mesmo preciso semear do zero, "
                "declare com `python3 scripts/check_test_cost.py --update` neste PR."
            )
        elif b < a:
            notes.append(f"{f}: {a} → {b} chamadas do seed; rode `--update` para guardar a folga")

    # 2. quem semeia no backstage mora no shard de quem semeia
    seed_list, heavy_list = make_list("BACKSTAGE_SEED_TESTS"), make_list("BACKSTAGE_HEAVY_TESTS")
    for f in sorted(now):
        if f.startswith(BACKSTAGE_TESTS + "/") and f not in seed_list and f not in heavy_list:
            problems.append(
                f"{f} chama o seed completo mas está no shard `rest`: ponha em BACKSTAGE_SEED_TESTS "
                "ou BACKSTAGE_HEAVY_TESTS no Makefile (no `rest` ele volta a ser o caminho crítico)."
            )

    # 3. shards partidos: completos, disjuntos, equilibrados, pesos vivos
    weights = load_weights(WEIGHTS)
    for name, inputs, exclude, parts in shard_specs():
        files = expand(inputs, exclude)
        split = partition(files, parts, weights)
        flat = [f for p in split for f in p]
        if sorted(flat) != files or len(flat) != len(set(flat)):
            problems.append(f"{name}: a partição não cobre cada arquivo exatamente uma vez")
        known = [f for f in files if f in weights]
        if parts > 1 and known:
            loads = [sum(weights.get(f, 0) for f in p) for p in split]
            ratio = max(loads) / max(min(loads), 0.001)
            if ratio > BALANCE_LIMIT:
                problems.append(
                    f"{name}: partes {', '.join(f'{x:.0f}s' for x in loads)} (razão {ratio:.2f} > {BALANCE_LIMIT}). "
                    "Um arquivo ficou pesado demais para a divisão: aumente as partes no Makefile "
                    "ou mova o arquivo para o shard `heavy`."
                )
            unknown = len(files) - len(known)
            if unknown > len(files) * 0.2:
                notes.append(f"{name}: {unknown} de {len(files)} arquivos sem peso medido; meça de novo")
    stale = sorted(f for f in weights if not (ROOT / f).exists())
    if stale:
        problems.append(
            "pesos de arquivos que não existem mais em scripts/test-shard-weights.json: "
            + ", ".join(stale[:5]) + ("…" if len(stale) > 5 else "")
            + ". Apague as entradas (ou meça de novo com `test_shards.py --measure`)."
        )

    for n in notes:
        print(f"ℹ️ {n}")
    if problems:
        print("✗ custo dos testes:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"✓ custo dos testes: {sum(now.values())} chamadas do seed em {len(now)} arquivos (baseline), shards completos e equilibrados")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
