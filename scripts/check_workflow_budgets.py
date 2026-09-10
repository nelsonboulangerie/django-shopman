#!/usr/bin/env python
"""Recusa workflow cujo teto de job não cabe a própria espera.

A armadilha que este gate existe para desarmar, medida em 08/09/2026: o
``alpha-smoke.yml`` tinha ``timeout-minutes: 5`` no job e ``sleep 420`` — sete
minutos — no primeiro passo. A conta não fecha, e não fechava desde 06/09.

O resultado não foi um gate vermelho. Foi um gate **cancelado**: dezesseis
execuções por ``workflow_run``, todas mortas aos cinco minutos no passo da
espera, com as quatro asserções saindo ``skipped``. Run cancelado não fica
vermelho — o alpha passou três dias sem guarda pós-deploy e a ausência de sinal
foi lida como sinal bom. Três tentativas de conserto atacaram a concorrência,
que nunca foi a causa.

Uma espera maior que o teto do job é **defeito aritmético**, visível sem rodar
nada. É exatamente o tipo de coisa que um humano confere uma vez e nunca mais, e
que a CI pode lembrar no lugar dele.

    python scripts/check_workflow_budgets.py

Sai com 1 na primeira violação. Não escreve em lugar nenhum.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover - o .venv da raiz tem PyYAML
    print("PyYAML ausente — rode com .venv/bin/python", file=sys.stderr)
    raise SystemExit(2) from exc

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

#: Folga mínima entre o teto da espera e o teto do job, em segundos. Cobre
#: setup do runner, checkout e as asserções que vêm DEPOIS da espera — que são
#: o motivo de o workflow existir. Sem folga declarada, "cabe por um segundo"
#: passaria no gate e morreria na primeira asserção lenta.
MARGIN_SECONDS = 300

#: Domínios que a casa cortou e que não podem voltar como default silencioso.
#: Um fallback para host morto ou é vermelho por motivo errado, ou — o modo que
#: já aconteceu aqui — verde sem testar nada. Ver o corte de 01/09/2026.
DEAD_HOST_FALLBACK = re.compile(
    r"\|\|\s*'https://(?:alpha|staging)\.[^']*'", re.IGNORECASE
)


def _fail(message: str) -> None:
    print(f"[FALHOU] {message}", file=sys.stderr)
    raise SystemExit(1)


def _job_timeout_seconds(job: dict, job_name: str, path: Path) -> int:
    timeout = job.get("timeout-minutes")
    if timeout is None:
        _fail(
            f"{path.name}: job '{job_name}' declara espera mas não declara "
            "`timeout-minutes`. Sem teto explícito vale o default de 360 min "
            "do GitHub, e a relação entre espera e teto deixa de ser legível."
        )
    return int(timeout) * 60


def _declared_wait_seconds(data: dict) -> int | None:
    raw = (data.get("env") or {}).get("DEPLOY_WAIT_MAX_SECONDS")
    return int(str(raw)) if raw is not None else None


def _literal_sleeps(job: dict) -> list[int]:
    """Maior `sleep N` literal por passo — a espera cega que sobrou no shell."""
    found: list[int] = []
    for step in job.get("steps") or []:
        run = step.get("run")
        if not isinstance(run, str):
            continue
        for match in re.finditer(r"(?m)^\s*sleep\s+(\d+)\s*$", run):
            found.append(int(match.group(1)))
    return found


def main() -> int:
    checked = 0
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")

        if DEAD_HOST_FALLBACK.search(text):
            _fail(
                f"{path.name}: default para um domínio que a casa cortou "
                "(alpha./staging.). Sem variável, o gate tem que PARAR e dizer "
                "por quê — não apontar para um host morto."
            )

        data = yaml.safe_load(text) or {}
        wait = _declared_wait_seconds(data)

        for job_name, job in (data.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            sleeps = _literal_sleeps(job)
            budget = max([*sleeps, wait or 0], default=0)
            if budget <= 0:
                continue

            timeout = _job_timeout_seconds(job, job_name, path)
            checked += 1
            if timeout < budget + MARGIN_SECONDS:
                _fail(
                    f"{path.name}: job '{job_name}' espera até {budget}s mas o "
                    f"teto do job é {timeout}s. O job morre DENTRO da espera e "
                    "as asserções saem `skipped` — cancelado, não vermelho, que "
                    "é a falha que ninguém vê. Exigido: teto >= espera + "
                    f"{MARGIN_SECONDS}s de folga (>= {budget + MARGIN_SECONDS}s)."
                )
            print(
                f"[OK] {path.name}: '{job_name}' espera <= {budget}s, "
                f"teto {timeout}s (folga {timeout - budget}s)"
            )

    if checked == 0:
        print("[OK] nenhum workflow com espera declarada")
    print("[OK] workflow_budgets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
