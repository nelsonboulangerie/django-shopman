#!/usr/bin/env python3
"""Escolhe o runner dos jobs de NAVEGADOR, com teto de gasto que não trava a fila.

DEV-2026-098, plano §9.3. Benchmark de 26/11: a Ubicloud (`ubicloud-standard-4`,
na prática o Ryzen 7950X3D) acelera o job de navegador 1,6–1,7x e as suítes
Python nada. O piloto manda SÓ a classe de navegador para lá, e só no
`merge_group`.

O dono, 26/11: "não quero levar susto de gasto". Dois sustos possíveis:

* **gastar além do teto** — a Ubicloud tem corte de gasto (US$ 10/mês), mas o
  corte não é rígido e é checado de 5 em 5 minutos;
* **travar a fila** — com o corte atingido, a Ubicloud RECUSA máquina nova, e o
  job fica esperando um runner que não vem (como o 4-core em 18/11).

Por isso a escolha é feita AQUI, a cada grupo, antes de pedir a máquina:
conta os grupos da fila desde o início do piloto (`CI_BROWSER_SINCE`),
multiplica por um custo por grupo de propósito ALTO
(`CI_BROWSER_COST_PER_GROUP_USD`, padrão 0,30; medido ~0,17) e, ao chegar no
orçamento do piloto (`CI_BROWSER_BUDGET_USD`, padrão 8, abaixo do corte de 10),
devolve o runner grátis. Sem variável, fora da fila, ou qualquer erro: grátis.
Nunca falha o job: errar aqui custa no máximo velocidade, nunca a fila.

Saída (para o ``$GITHUB_OUTPUT``): ``runner=<rótulo>``, ``alert=true|false`` e
``reason=<texto>``.

A queda NÃO é silenciosa (dono, 26/11: "tem como eu saber sempre se deveria estar
usando o pago mas não está?"). ``alert=true`` quando o piloto está LIGADO e mesmo
assim foi para o grátis (orçamento esgotado ou erro ao medir); desligar o piloto
(apagar a variável) é decisão e não alarma. O modo ``notify`` abre UMA issue
"Piloto da Ubicloud voltou ao grátis" (sem duplicar nem comentar a cada grupo) e
a comenta e fecha quando o piloto volta ao pago.

    python3 scripts/ci_browser_runner.py            # escolhe (passo do workflow)
    python3 scripts/ci_browser_runner.py notify     # abre/fecha a issue (passo seguinte)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request


def fallback() -> str:
    return os.environ.get("CI_LINUX_RUNNER") or "ubuntu-latest"


def groups_since(repo: str, since: str, token: str) -> int:
    query = urllib.parse.urlencode({"event": "merge_group", "created": f">={since}", "per_page": 1})
    url = f"https://api.github.com/repos/{repo}/actions/workflows/surfaces-gate.yml/runs?{query}"
    request = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(request, timeout=15) as response:
        return int(json.load(response)["total_count"])


def choose(env: dict, count_groups) -> tuple[str, str]:
    """(runner, motivo). ``count_groups(since) -> int`` é injetado (teste)."""
    if env.get("EVENT") != "merge_group":
        return fallback(), "fora da fila: grátis"
    runner, since = env.get("CI_BROWSER_RUNNER", ""), env.get("CI_BROWSER_SINCE", "")
    if not runner or not since:
        return fallback(), "piloto desligado (sem CI_BROWSER_RUNNER/CI_BROWSER_SINCE)"
    try:
        budget = float(env.get("CI_BROWSER_BUDGET_USD") or 8)
        cost = float(env.get("CI_BROWSER_COST_PER_GROUP_USD") or 0.30)
        groups = count_groups(since)
    except Exception as exc:  # noqa: BLE001 — qualquer dúvida vira grátis
        return fallback(), f"erro ao medir o piloto ({exc.__class__.__name__}): grátis"
    spent = groups * cost
    if spent >= budget:
        return fallback(), (
            f"orçamento do piloto esgotado: {groups} grupos × US$ {cost:.2f} = US$ {spent:.2f} "
            f"≥ US$ {budget:.2f}; voltou ao grátis"
        )
    return runner, f"piloto: {groups} grupos × US$ {cost:.2f} = US$ {spent:.2f} de US$ {budget:.2f}"


ISSUE_TITLE = "Piloto da Ubicloud voltou ao grátis"


def notify(env: dict, gh) -> str:
    """Abre/fecha a issue conforme ``ALERT``. ``gh(*args) -> str`` é injetado (teste)."""
    if env.get("EVENT") != "merge_group" or not env.get("CI_BROWSER_RUNNER"):
        return "piloto desligado ou fora da fila: nada a avisar"
    # Passo de escolha que falhou não deixa saída: também é queda não pedida.
    alert = env.get("ALERT", "") != "false"
    reason = env.get("REASON") or "o passo que escolhe o runner falhou (sem motivo registrado)"
    found = gh("issue", "list", "--state", "open", "--search", f'in:title "{ISSUE_TITLE}"',
               "--json", "number", "--jq", ".[0].number").strip()
    if alert and not found:
        body = (
            f"O piloto da Ubicloud está LIGADO (`CI_BROWSER_RUNNER={env.get('CI_BROWSER_RUNNER')}`), "
            f"mas os jobs de navegador voltaram ao runner grátis.\n\n**Motivo:** {reason}\n\n"
            f"Run: {env.get('RUN_URL', '?')}\n\n"
            "Nada travou: a fila segue no grátis, só mais devagar. Para voltar ao pago:\n"
            "- orçamento esgotado: subir `CI_BROWSER_BUDGET_USD` (variável do repositório) E o corte "
            "de gasto no console da Ubicloud (Billing › Spending Cutoff), ou recomeçar a contagem "
            "trocando `CI_BROWSER_SINCE` no mês novo;\n"
            "- erro ao medir: ver o passo \"Runner dos jobs de navegador\" no run acima.\n\n"
            "Esta issue fecha sozinha quando um grupo voltar a usar o pago. DEV-2026-098, plano §9.3."
        )
        gh("issue", "create", "--title", ISSUE_TITLE, "--body", body)
        return "issue aberta"
    if not alert and found:
        gh("issue", "comment", found, "--body", f"Voltou ao pago neste grupo: {env.get('RUN_URL', '?')} ({reason}). Fechando.")
        gh("issue", "close", found)
        return f"issue #{found} fechada"
    return "estado já registrado: nada a fazer"


def main() -> int:
    env = dict(os.environ)
    if sys.argv[1:] == ["notify"]:
        def gh(*args: str) -> str:
            import subprocess
            return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout
        print(notify(env, gh))
        return 0
    token, repo = env.get("GH_TOKEN", ""), env.get("GITHUB_REPOSITORY", "")
    runner, reason = choose(env, lambda since: groups_since(repo, since, token))
    # Ligado = runner do piloto definido. Faltar CI_BROWSER_SINCE com o runner definido
    # também é "deveria estar no pago e não está": alarma, em vez de calar.
    pilot_on = env.get("EVENT") == "merge_group" and bool(env.get("CI_BROWSER_RUNNER"))
    print(f"runner={runner}")
    print(f"alert={'true' if pilot_on and runner != env.get('CI_BROWSER_RUNNER') else 'false'}")
    print(f"reason={reason}")
    level = "warning" if "esgotado" in reason or "erro" in reason else "notice"
    print(f"::{level} title=Runner dos jobs de navegador::{runner} — {reason}", file=sys.stderr)
    summary = env.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as fh:
            fh.write(f"Runner dos jobs de navegador: `{runner}` — {reason}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
