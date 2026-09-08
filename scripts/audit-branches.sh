#!/usr/bin/env bash
#
# audit-branches.sh — Garante que nenhum trabalho relevante fique esquecido
# fora do main.
#
# Contexto: squash-merge faz um branch mergeado continuar "à frente" do main
# (os SHAs originais somem no squash). Um `git log origin/main..origin/<branch>`
# ingênuo, portanto, marca branches JÁ ENTREGUES como se tivessem trabalho
# pendente. Este script separa os dois casos com verificação de conteúdo real:
#
#   1. gh pr list --state merged  → conjunto de head-branches de PRs mergeados
#      (entregues, mesmo que pareçam à frente).
#   2. Para cada origin/<branch> com commits à frente de origin/main:
#        - `git merge-tree --write-tree origin/main origin/<branch>` produz a
#          árvore do merge hipotético. Se ela == árvore do origin/main, o
#          conteúdo do branch JÁ ESTÁ NO MAIN (merge no-op) → redundante.
#        - Caso contrário há delta real. Cruza com o conjunto de PRs mergeados:
#          delta real + SEM PR mergeado = ⚠️ UNMERGED, um humano precisa agir.
#
# ⚠️ O cruzamento com PRs NÃO pode depender de uma janela fixa. Este script
# listava os 300 PRs mergeados mais recentes e decidia por ali; em 08/09/2026 o
# PR #135 — mergeado — já tinha caído para fora da janela, e o branch
# `feat/badge-issue-screen` apareceu como ⚠️ UNMERGED. Falso positivo de
# auditoria é pior que ruído: ele manda um humano procurar trabalho que não
# existe, e ensina a ignorar a coluna ⚠️, que é a única que importa.
#
# A janela continua, mas só como CACHE de consulta rápida. Quem decide é a
# pergunta DIRIGIDA ao branch (`gh pr list --head <branch>`), que não tem
# janela: só ela pode dizer "não há PR nenhum".
#
# Saída: tabela status | branch | última data | resumo de arquivos.
# Só as linhas ⚠️ exigem ação humana. `◷ PR ABERTO` está em revisão e
# `✗ PR FECHADO` é decisão registrada do dono (supersedido, recusado) — nenhum
# dos dois é esquecimento, e por isso nenhum é ⚠️.
#
# Uso:  make audit-branches   (ou)   scripts/audit-branches.sh
# Env:  BASE=origin/main  REMOTE=origin  MERGED_PR_LIMIT=300 (só o cache)

set -euo pipefail

BASE="${BASE:-origin/main}"
REMOTE="${REMOTE:-origin}"
MERGED_PR_LIMIT="${MERGED_PR_LIMIT:-300}"

bold=""; dim=""; red=""; green=""; yellow=""; reset=""
if [ -t 1 ]; then
  bold="$(printf '\033[1m')"; dim="$(printf '\033[2m')"
  red="$(printf '\033[31m')"; green="$(printf '\033[32m')"
  yellow="$(printf '\033[33m')"; reset="$(printf '\033[0m')"
fi

echo "${dim}Atualizando refs de ${REMOTE}...${reset}" >&2
git fetch "${REMOTE}" --prune --quiet 2>/dev/null || \
  echo "${yellow}aviso: git fetch falhou (offline?), usando refs locais${reset}" >&2

if ! git rev-parse --verify --quiet "${BASE}" >/dev/null; then
  echo "${red}erro: base '${BASE}' não existe${reset}" >&2
  exit 1
fi

BASE_TREE="$(git rev-parse "${BASE}^{tree}")"

# Conjunto de head-branches de PRs já mergeados (uma por linha).
OPEN_PRS=""
MERGED_PRS=""
if command -v gh >/dev/null 2>&1; then
  OPEN_PRS="$(gh pr list --state open --limit 200 \
      --json headRefName --jq '.[].headRefName' 2>/dev/null || true)"
  echo "${dim}Consultando PRs mergeados (gh)...${reset}" >&2
  MERGED_PRS="$(gh pr list --state merged --limit "${MERGED_PR_LIMIT}" \
      --json headRefName --jq '.[].headRefName' 2>/dev/null || true)"
else
  echo "${yellow}aviso: gh não encontrado; cruzamento com PRs mergeados desativado${reset}" >&2
fi

# Estado do PR de UM branch: "MERGED", "CLOSED" ou "" (nenhum PR).
#
# O cache responde na hora quando acerta. Quando erra — e ele erra por
# construção, porque é uma janela — a pergunta dirigida decide. Ela custa uma
# chamada por branch, e só é feita para os poucos branches com delta real.
pr_state_for() {
  local branch="$1"
  # ⚠️ PR ABERTO vem primeiro, e vem de uma consulta própria. Um head de PR
  # aberto — os sete do Dependabot, por exemplo — não é branch esquecida: é
  # trabalho EM REVISÃO. Listá-lo em ⚠️ UNMERGED enche a única coluna que exige
  # ação humana de linhas que não exigem nada, e uma coluna assim se aprende a
  # ignorar. Foi o mesmo erro da janela fixa de PRs mergeados, por outra porta.
  if [ -n "${OPEN_PRS}" ] && printf '%s\n' "${OPEN_PRS}" | grep -qxF "${branch}"; then
    printf 'OPEN'
    return 0
  fi
  if [ -n "${MERGED_PRS}" ] && printf '%s\n' "${MERGED_PRS}" | grep -qxF "${branch}"; then
    printf 'MERGED'
    return 0
  fi
  command -v gh >/dev/null 2>&1 || { printf ''; return 0; }
  gh pr list --head "${branch}" --state all --limit 1 \
      --json state --jq '.[0].state // ""' 2>/dev/null || printf ''
}

# Coleta as linhas em buffers para poder ordenar (⚠️ primeiro) e contar.
unmerged_rows=""
open_rows=""
merged_rows=""
closed_rows=""
redundant_rows=""
unmerged_count=0

base_short="${BASE#${REMOTE}/}"

while IFS= read -r ref; do
  branch="${ref#refs/remotes/${REMOTE}/}"
  # pula o próprio base e o HEAD simbólico
  [ "${branch}" = "${base_short}" ] && continue
  [ "${branch}" = "HEAD" ] && continue

  ahead="$(git rev-list --count "${BASE}..${ref}" 2>/dev/null || echo 0)"
  [ "${ahead}" -gt 0 ] || continue   # nada à frente → totalmente no main

  # Árvore do merge hipotético BASE + branch. Primeira linha = OID da árvore
  # (mesmo quando há conflito, caso em que o exit code é != 0).
  merged_tree="$(git merge-tree --write-tree "${BASE}" "${ref}" 2>/dev/null | head -1 || true)"

  last_date="$(git log -1 --format='%cs' "${ref}" 2>/dev/null || echo '?')"
  files_changed="$(git diff --name-only "${BASE}...${ref}" 2>/dev/null | wc -l | tr -d ' ')"
  files_summary="$(git diff --shortstat "${BASE}...${ref}" 2>/dev/null | sed 's/^ *//')"
  [ -n "${files_summary}" ] || files_summary="${files_changed} arquivo(s)"

  if [ "${merged_tree}" = "${BASE_TREE}" ]; then
    # merge é no-op: conteúdo já está no main (squash/cherry-pick redundante)
    redundant_rows+="${green}✓ JÁ NO MAIN${reset}\t${branch}\t${last_date}\t${dim}${files_summary} (merge no-op)${reset}\n"
  else
    # Uma pergunta por branch, e só para os poucos com delta real.
    case "$(pr_state_for "${branch}")" in
      OPEN)
        open_rows+="${bold}◷ PR ABERTO${reset}\t${branch}\t${last_date}\t${dim}${files_summary}${reset}\n"
        ;;
      MERGED)
        merged_rows+="${green}✓ PR MERGEADO${reset}\t${branch}\t${last_date}\t${dim}${files_summary}${reset}\n"
        ;;
      CLOSED)
        # Fechado é DECISÃO registrada (supersedido, recusado), não
        # esquecimento — o dono já olhou. Aparece na tabela para ficar
        # rastreável, mas não conta como ação humana pendente.
        closed_rows+="${dim}✗ PR FECHADO${reset}\t${branch}\t${last_date}\t${dim}${files_summary}${reset}\n"
        ;;
      *)
        unmerged_rows+="${red}${bold}⚠️  UNMERGED${reset}\t${bold}${branch}${reset}\t${last_date}\t${yellow}${files_summary}${reset}\n"
        unmerged_count=$((unmerged_count + 1))
        ;;
    esac
  fi
done < <(git for-each-ref --format='%(refname)' "refs/remotes/${REMOTE}")

echo
echo "${bold}Auditoria de branches — à frente de ${BASE}${reset}"
echo "${dim}⚠️ = delta real + nenhum PR mergeado. Só essas exigem ação humana.${reset}"
echo

{
  printf 'STATUS\tBRANCH\tÚLTIMO COMMIT\tRESUMO\n'
  printf ' +++\t+++\t+++\t+++\n'
  # ⚠️ primeiro, depois entregues
  printf '%b' "${unmerged_rows}"
  printf '%b' "${open_rows}"
  printf '%b' "${merged_rows}"
  printf '%b' "${closed_rows}"
  printf '%b' "${redundant_rows}"
} | column -t -s $'\t' | sed 's/^+++.*/--------------------------------------------------------------------------/'

echo
if [ "${unmerged_count}" -eq 0 ]; then
  echo "${green}${bold}✓ Nenhum branch com trabalho não mergeado. Tudo relevante está no ${BASE}.${reset}"
else
  echo "${red}${bold}⚠️  ${unmerged_count} branch(es) com trabalho potencialmente não mergeado — revise acima.${reset}"
fi
