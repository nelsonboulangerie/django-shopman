#!/usr/bin/env python3
"""Parte uma lista de arquivos de teste em N shards equilibrados pelo tempo.

DEV-2026-098. O benchmark de 25/11 (`evidence/ci-dx-098/`) mediu que
`backstage seed` e `backstage rest` são os dois jobs da fila que aceleram com
mais núcleo (1,95x e 1,47x no passo de teste com 8 vCPU). Dois runners grátis
de 4 vCPU somam os 8 de um pago: dividir esses shards dá o ganho sem custo.

Garantias, por construção:

* **união e disjunção** — as partes são uma PARTIÇÃO da mesma lista (cada
  arquivo vai para exatamente uma); nenhum teste some e nenhum roda duas vezes;
* **determinismo** — o mesmo conjunto e os mesmos pesos dão as mesmas partes
  em qualquer máquina (ordem por peso, desempate pelo caminho);
* **arquivo novo não some** — entra com o peso mediano e cai na parte mais
  leve; só o equilíbrio piora até alguém medir de novo;
* **parte vazia é erro** (código 2): `pytest` sem argumentos rodaria o
  `testpaths` do pyproject, outra suíte, verde e calado.

Entrada: arquivos e/ou diretórios (diretório = os ``test_*.py`` e
``*_test.py`` dele, recursivo, como o pytest coleta), ``--exclude`` para os
arquivos de outros shards. Pesos em segundos por arquivo
(``scripts/test-shard-weights.json``), medidos com ``--junitxml``.

    python3 scripts/test_shards.py --part 1/2 shopman/backstage/tests \\
        --exclude shopman/backstage/tests/test_a.py ...
    python3 scripts/test_shards.py --show 2 <mesma entrada>      # resumo das partes
    python3 scripts/test_shards.py --measure junit.xml ...        # atualiza os pesos
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEIGHTS = ROOT / "scripts" / "test-shard-weights.json"


def expand(inputs: list[str], exclude: list[str]) -> list[str]:
    files: set[str] = set()
    for item in inputs:
        path = ROOT / item
        if path.is_dir():
            for pattern in ("test_*.py", "*_test.py"):
                files.update(str(p.relative_to(ROOT)) for p in path.rglob(pattern))
        elif path.is_file():
            files.add(item)
        else:
            # Arquivo listado que não existe: o shard nomeado reprovaria alto no
            # pytest; aqui também (renomeou e esqueceu a lista do Makefile).
            raise SystemExit(f"test_shards: não existe: {item}")
    return sorted(files - set(exclude))


def load_weights(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    return {k: float(v) for k, v in json.loads(path.read_text()).get("seconds", {}).items()}


def partition(files: list[str], parts: int, weights: dict[str, float]) -> list[list[str]]:
    """LPT guloso: o mais pesado primeiro, sempre na parte mais leve."""
    if parts < 1:
        raise ValueError("parts >= 1")
    known = [weights[f] for f in files if f in weights]
    default = statistics.median(known) if known else 1.0
    load = [0.0] * parts
    out: list[list[str]] = [[] for _ in range(parts)]
    for f in sorted(files, key=lambda f: (-weights.get(f, default), f)):
        i = min(range(parts), key=lambda k: (load[k], k))
        out[i].append(f)
        load[i] += weights.get(f, default)
    return [sorted(p) for p in out]


def measure(junit_files: list[Path]) -> dict[str, float]:
    """Soma o tempo por arquivo a partir de ``--junitxml`` (classname → arquivo)."""
    totals: dict[str, float] = {}
    for junit in junit_files:
        for case in ET.parse(junit).getroot().iter("testcase"):
            cls = case.get("classname", "")
            parts = cls.split(".")
            # pytest: "shopman.backstage.tests.test_x.Classe" ou "...test_x"
            for i in range(len(parts), 0, -1):
                candidate = "/".join(parts[:i]) + ".py"
                if (ROOT / candidate).exists():
                    totals[candidate] = totals.get(candidate, 0.0) + float(case.get("time") or 0)
                    break
    return {k: round(v, 2) for k, v in sorted(totals.items())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("inputs", nargs="*")
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--weights", type=Path, default=WEIGHTS)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--part", help="K/N")
    group.add_argument("--show", type=int, metavar="N")
    group.add_argument("--measure", nargs="+", type=Path, metavar="JUNIT")
    args = parser.parse_args()

    if args.measure:
        data = json.loads(args.weights.read_text()) if args.weights.exists() else {}
        seconds = data.get("seconds", {})
        seconds.update(measure(args.measure))
        data["seconds"] = dict(sorted(seconds.items()))
        args.weights.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
        print(f"{len(seconds)} arquivos com peso em {args.weights}")
        return 0

    files = expand(args.inputs, args.exclude)
    weights = load_weights(args.weights)
    if args.show:
        for k, part in enumerate(partition(files, args.show, weights), 1):
            load = sum(weights.get(f, 0) for f in part)
            unknown = sum(f not in weights for f in part)
            print(f"parte {k}/{args.show}: {len(part)} arquivos, {load:.0f}s medidos, {unknown} sem peso")
        return 0
    k, n = (int(x) for x in args.part.split("/"))
    if not 1 <= k <= n:
        raise SystemExit(f"test_shards: parte {args.part} fora de 1..{n}")
    part = partition(files, n, weights)[k - 1]
    if not part:
        print(f"test_shards: parte {args.part} vazia", file=sys.stderr)
        return 2
    print(" ".join(part))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
