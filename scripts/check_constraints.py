#!/usr/bin/env python
"""O `constraints.txt` cobre TUDO que a imagem de deploy instala?

## Por que este guard existe

`pyproject.toml` declara FAIXAS. Sem pin, a imagem instalava o que o PyPI tinha
no dia do build — e em 19/08/2026 isso eram 40 pacotes diferentes do que a suíte
validava, incluindo o `sentry-sdk`, que subia para produção sem nunca ter sido
exercitado por um teste. O `constraints.txt` fechou esse buraco.

Só que ele abriu de novo no mesmo dia: o `rapidfuzz` entrou como dependência de
runtime DEPOIS dos pins, e constraints não impede instalação — só limita versão.
Resultado: o pacote subia sem pin, e nada falhava. O arquivo apodrece em silêncio
porque o `make install` do CI não usa constraints; só o deploy sente.

Este script é o alarme que faltava. Ele resolve o MESMO conjunto que o Dockerfile
instala e exige que todo pacote resolvido tenha pin exato. Pega dependência nova
direta (o caso do rapidfuzz) e também transitiva.

## Uso

    python scripts/check_constraints.py           # falha se houver buraco
    python scripts/check_constraints.py --write   # regenera o constraints.txt

⚠️ `--write` só depois de `make test` VERDE no mesmo conjunto: o valor do pin é
ser a versão que a suíte viu, não a mais nova que existe.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONSTRAINTS = ROOT / "constraints.txt"

# A MESMA lista do Dockerfile, na mesma ordem. Se ela mudar lá, muda aqui —
# o guard só vale se resolver o conjunto que a imagem realmente instala.
PACKAGES = [
    "./packages/refs",
    "./packages/utils",
    "./packages/offerman",
    "./packages/stockman",
    "./packages/craftsman",
    "./packages/guestman",
    "./packages/doorman",
    "./packages/orderman",
    "./packages/payman",
    "./packages/buyman",
    "./packages/fiscalman",
    "./packages/cashman",
    ".",
]

HEADER = CONSTRAINTS.read_text().split("\n\n", 1)[0] if CONSTRAINTS.exists() else ""


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def read_pins() -> dict[str, str]:
    if not CONSTRAINTS.exists():
        return {}
    pins = {}
    for line in CONSTRAINTS.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "==" in line:
            name, version = line.split("==", 1)
            pins[normalize(name)] = version.strip()
    return pins


def resolve() -> dict[str, tuple[str, str]]:
    """Resolve o conjunto do Dockerfile.

    Devolve ``{nome_normalizado: (nome_como_o_pacote_se_chama, versão)}``. O nome
    original importa: pinar ``Django==`` em vez de ``django==`` mantém o arquivo
    legível e o diff honesto (pip trata os dois igual, PEP 503).

    Sem `-c constraints.txt` de propósito: queremos ver o que a resolução
    escolheria, para comparar com o que está pinado.
    """
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
        report_path = Path(handle.name)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--dry-run", "--ignore-installed",
             "--quiet", "--report", str(report_path), *PACKAGES],
            cwd=ROOT, capture_output=True, text=True,
        )
        if result.returncode != 0:
            sys.exit(f"pip não conseguiu resolver o conjunto do Dockerfile:\n{result.stderr}")
        report = json.loads(report_path.read_text())
    finally:
        report_path.unlink(missing_ok=True)

    resolved = {}
    for item in report["install"]:
        # Os 13 pacotes locais (shopman-*, django-shopman) instalam por caminho e
        # são versionados pelo próprio repo — pinar não faria sentido.
        if item.get("is_direct") and item["download_info"]["url"].startswith("file://"):
            continue
        meta = item["metadata"]
        resolved[normalize(meta["name"])] = (meta["name"], meta["version"])
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="regenera o constraints.txt (só com a suíte verde)")
    args = parser.parse_args()

    resolved = resolve()

    if args.write:
        body = "\n".join(
            f"{name}=={version}"
            for _, (name, version) in sorted(resolved.items())
        )
        CONSTRAINTS.write_text(f"{HEADER}\n\n{body}\n" if HEADER else f"{body}\n")
        print(f"✓ constraints.txt regenerado com {len(resolved)} pins")
        return 0

    pins = read_pins()
    missing = sorted(name for name in resolved if name not in pins)
    stale = sorted(
        (name, pins[name], version)
        for name, (_, version) in resolved.items()
        if name in pins and pins[name] != version
    )
    orphan = sorted(name for name in pins if name not in resolved)

    if missing:
        print("✖ Pacotes que a imagem instala SEM pin no constraints.txt:\n")
        for name in missing:
            print(f"    {name} (resolveria para {resolved[name][1]})")
        print(
            "\n  Uma dependência nova entrou depois dos pins. Constraints limita\n"
            "  versão, não impede instalação — então isto NÃO quebra o build:\n"
            "  sobe sem pin, e o drift volta em silêncio.\n"
            "\n  Para fechar:\n"
            "    1. python -m venv /tmp/v && /tmp/v/bin/pip install ./packages/* '.[dev]'\n"
            "    2. make test PYTHON=/tmp/v/bin/python        # tem de ficar VERDE\n"
            "    3. /tmp/v/bin/python scripts/check_constraints.py --write\n"
        )
        return 1

    # Pin diferente da resolução é ESPERADO e desejável: é o pin segurando uma
    # versão mais nova que ninguém testou. Só informamos.
    if stale:
        print(f"ℹ {len(stale)} pin(s) segurando versão mais nova (é o trabalho deles):")
        for name, pinned, latest in stale[:8]:
            print(f"    {name}: pin {pinned} · disponível {latest}")
        if len(stale) > 8:
            print(f"    … e mais {len(stale) - 8}")
        print()

    if orphan:
        print(f"ℹ {len(orphan)} pin(s) sem uso (dependência saiu do projeto): {', '.join(orphan[:6])}")
        print()

    print(f"✓ constraints.txt cobre os {len(resolved)} pacotes que a imagem instala")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
