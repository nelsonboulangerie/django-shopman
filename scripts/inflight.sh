#!/usr/bin/env bash
#
# inflight.sh — o que está EM VOO e o que está DORMINDO neste repositório.
#
# `make audit-branches` olha só branch REMOTA. O trabalho que se perde aqui não
# está lá: mora em worktree suja (arquivo nunca commitado), em branch LOCAL nunca
# empurrada (`codex/*` com 10 a 77 commits e nenhum PR, medido em 16/09/2026) e
# em PR verde que ninguém enfileirou. As três coisas são invisíveis para
# `gh pr list`, para `git branch -r` e para o Pablo.
#
# Este script varre as três e classifica. Só 🔴 e 🟢-fora-da-fila pedem ação.
#
#   🔴 SUJA          worktree com arquivo não commitado
#   🔴 SEM PR        branch com delta real sobre o main e nenhum PR
#   🔴 NÃO EMPURRADA commits locais que o origin não tem
#   ⚠️ DELTA PÓS-PR  PR mergeado, mas o branch tem commits além dele
#   🟢 VERDE FORA DA FILA  PR limpo, checks verdes, auto-merge desligado → `gh pr merge <N>`
#   🚦 NA FILA       auto-merge ligado, a fila é dona
#   🔴 VERMELHO      check reprovado — nomeie a causa ou conserte
#   ⚠️ CONFLITO      PR não funde com o main — resolva no branch
#   ◷  RODANDO       check pendente
#   📝 DRAFT         WIP declarado (estado aceitável de fim de sessão)
#   ✓  ENTREGUE      branch mergeada ou merge no-op — não aparece, só conta
#
# Uso:  make inflight   (ou)   scripts/inflight.sh
# Env:  BASE=origin/main  REMOTE=origin  SHOW_DELIVERED=1 (lista as ✓ também)

set -uo pipefail
export PATH="$PATH:/opt/homebrew/bin:/usr/local/bin"

BASE="${BASE:-origin/main}"
REMOTE="${REMOTE:-origin}"
SHOW_DELIVERED="${SHOW_DELIVERED:-0}"
# Artefato de dev que não é trabalho: não conta como "sujo". Casa em qualquer
# subpasta (o .nuxtrc mora em surfaces/<app>/).
NOISE='^.. (.*/)?(\.nuxtrc|\.alpha-tmp/|\.claude/|\.codex/|\.local-tests/|\.artifacts/|\.orders-lab/|output/|\.env|\.env\.local)$'

bold=""; dim=""; red=""; green=""; yellow=""; reset=""
if [ -t 1 ]; then
  bold="$(printf '\033[1m')"; dim="$(printf '\033[2m')"
  red="$(printf '\033[31m')"; green="$(printf '\033[32m')"
  yellow="$(printf '\033[33m')"; reset="$(printf '\033[0m')"
fi

echo "${dim}Atualizando refs de ${REMOTE}...${reset}" >&2
git fetch "${REMOTE}" --prune --quiet 2>/dev/null || \
  echo "${yellow}aviso: git fetch falhou (offline?), usando refs locais${reset}" >&2
git rev-parse --verify --quiet "${BASE}" >/dev/null || { echo "erro: base '${BASE}' não existe" >&2; exit 1; }
BASE_TREE="$(git rev-parse "${BASE}^{tree}")"

# Uma consulta só para todos os PRs; a pergunta dirigida fica para quem escapar
# da janela (a janela é cache, não verdade — ver audit-branches.sh).
# Duas chamadas, de propósito: pedir statusCheckRollup de 400 PRs de uma vez
# devolve HTTP 504 do GraphQL (medido em 16/09/2026) e o script ficava cego
# para os PRs abertos. O mapa branch→PR é leve; os checks só dos abertos.
PRS="[]"; OPEN="[]"
if command -v gh >/dev/null 2>&1; then
  echo "${dim}Consultando PRs (gh)...${reset}" >&2
  PRS="$(gh pr list --state all --limit 500 --json number,state,isDraft,headRefName 2>/dev/null || echo '[]')"
  OPEN="$(gh pr list --state open --limit 100 \
    --json number,state,isDraft,headRefName,mergeStateStatus,autoMergeRequest,statusCheckRollup,author,title,updatedAt \
    2>/dev/null || echo '[]')"
else
  echo "${yellow}aviso: gh não encontrado; PRs não serão cruzados${reset}" >&2
fi

# "número\testado\tdraft" do PR de um branch, preferindo OPEN > MERGED > CLOSED.
pr_for() {
  local b="$1" hit
  hit="$(printf '%s' "${PRS}" | jq -r --arg b "$b" '
    map(select(.headRefName==$b)) as $m
    | ($m|map(select(.state=="OPEN"))[0]) // ($m|map(select(.state=="MERGED"))[0]) // $m[0]
    | if . then "\(.number)\t\(.state)\t\(.isDraft)" else "" end')"
  if [ -z "${hit}" ] && command -v gh >/dev/null 2>&1; then
    hit="$(gh pr list --head "$b" --state all --limit 5 \
      --json number,state,isDraft --jq '
        (map(select(.state=="OPEN"))[0]) // (map(select(.state=="MERGED"))[0]) // .[0]
        | if . then "\(.number)\t\(.state)\t\(.isDraft)" else "" end' 2>/dev/null || true)"
  fi
  printf '%s' "${hit}"
}

rows_red=""; rows_warn=""; rows_open=""; rows_ok=""
n_red=0; n_warn=0; n_open=0; n_ok=0; n_missing=0
base_short="${BASE#${REMOTE}/}"

while IFS=$'\t' read -r w b; do
  [ -n "${w}" ] || continue
  short="${w##*/}"
  if [ ! -d "${w}" ]; then
    n_missing=$((n_missing + 1)); continue   # worktree apagada do disco: `git worktree prune`
  fi
  dirty="$(git -C "${w}" status --porcelain 2>/dev/null | grep -Ev "${NOISE}" | grep -c . || true)"
  if [ "${b}" = "${base_short}" ] || [ "${b}" = "(detached)" ]; then
    if [ "${dirty}" -gt 0 ]; then
      lbl="checkout em ${b}"; [ "${b}" = "(detached)" ] && lbl="detached HEAD"
      rows_red+="${red}${bold}🔴 SUJA (${lbl})${reset}\t${b}\t${dirty} arquivo(s) não commitados\t${short}\n"; n_red=$((n_red + 1))
    fi
    continue
  fi
  ahead="$(git rev-list --count "${BASE}..${b}" 2>/dev/null || echo 0)"
  unpushed=""
  if up="$(git -C "${w}" rev-parse --abbrev-ref '@{u}' 2>/dev/null)"; then
    n="$(git rev-list --count "${up}..${b}" 2>/dev/null || echo 0)"
    [ "${n}" -gt 0 ] && unpushed="${n} commit(s) não empurrados"
  elif [ "${ahead}" -gt 0 ]; then
    unpushed="branch nunca empurrada"
  fi
  last="$(git log -1 --format='%cs' "${b}" 2>/dev/null || echo '?')"
  flags=""
  [ "${dirty}" -gt 0 ] && flags+="${dirty} arquivo(s) não commitados; "
  [ -n "${unpushed}" ] && flags+="${unpushed}; "

  if [ "${ahead}" -eq 0 ]; then
    if [ "${dirty}" -gt 0 ]; then
      rows_red+="${red}${bold}🔴 SUJA${reset}\t${b}\t${flags}\t${short}\n"; n_red=$((n_red + 1))
    else
      rows_ok+="${green}✓ ENTREGUE${reset}\t${b}\t${dim}${last}${reset}\t${short}\n"; n_ok=$((n_ok + 1))
    fi
    continue
  fi

  pr="$(pr_for "${b}")"
  prn="${pr%%$'\t'*}"; rest="${pr#*$'\t'}"; prstate="${rest%%$'\t'*}"; prdraft="${rest#*$'\t'}"
  merged_tree="$(git merge-tree --write-tree "${BASE}" "${b}" 2>/dev/null | head -1 || true)"
  case "${prstate}" in
    OPEN)
      tag="◷ PR #${prn}"; [ "${prdraft}" = "true" ] && tag="📝 PR #${prn} draft"
      if [ "${dirty}" -gt 0 ] || [ -n "${unpushed}" ]; then
        rows_red+="${red}${bold}🔴 ${tag}${reset}\t${b}\t${flags}\t${short}\n"; n_red=$((n_red + 1))
      else
        rows_open+="${bold}${tag}${reset}\t${b}\t${ahead} commit(s), ${last}\t${short}\n"; n_open=$((n_open + 1))
      fi ;;
    MERGED)
      if [ "${merged_tree}" = "${BASE_TREE}" ] && [ "${dirty}" -eq 0 ]; then
        rows_ok+="${green}✓ ENTREGUE (PR #${prn})${reset}\t${b}\t${dim}${last}${reset}\t${short}\n"; n_ok=$((n_ok + 1))
      elif [ "${dirty}" -gt 0 ]; then
        rows_red+="${red}${bold}🔴 SUJA (PR #${prn} já mergeado)${reset}\t${b}\t${flags}\t${short}\n"; n_red=$((n_red + 1))
      else
        rows_warn+="${yellow}⚠️  DELTA PÓS-PR #${prn}${reset}\t${b}\t${ahead} commit(s) além do PR, ${last} — PR de seguimento?\t${short}\n"; n_warn=$((n_warn + 1))
      fi ;;
    CLOSED)
      if [ "${dirty}" -gt 0 ]; then
        rows_red+="${red}${bold}🔴 SUJA (PR #${prn} fechado)${reset}\t${b}\t${flags}\t${short}\n"; n_red=$((n_red + 1))
      else
        rows_ok+="${dim}✗ DECIDIDO (PR #${prn} fechado)${reset}\t${b}\t${dim}${last}${reset}\t${short}\n"; n_ok=$((n_ok + 1))
      fi ;;
    *)
      if [ "${merged_tree}" = "${BASE_TREE}" ] && [ "${dirty}" -eq 0 ]; then
        rows_ok+="${green}✓ JÁ NO MAIN (merge no-op)${reset}\t${b}\t${dim}${last}${reset}\t${short}\n"; n_ok=$((n_ok + 1))
      else
        files="$(git diff --shortstat "${BASE}...${b}" 2>/dev/null | sed 's/^ *//')"
        rows_red+="${red}${bold}🔴 SEM PR${reset}\t${b}\t${ahead} commit(s), ${last}; ${flags}${files}\t${short}\n"; n_red=$((n_red + 1))
      fi ;;
  esac
done < <(git worktree list --porcelain | awk '
  /^worktree /{w=$2}
  /^branch /{b=$2; sub("refs/heads/","",b); print w"\t"b}
  /^detached$/{print w"\t(detached)"}')

echo
echo "${bold}Em voo — worktrees e branches locais (base ${BASE})${reset}"
echo "${dim}🔴 exige ação: commit por arquivo nomeado → push → gh pr create → gh pr merge <N>. ⚠️ pede olhar. ✓ só conta.${reset}"
echo
{
  printf 'STATUS\tBRANCH\tDETALHE\tWORKTREE\n'
  printf ' +++\t+++\t+++\t+++\n'
  printf '%b' "${rows_red}"
  printf '%b' "${rows_warn}"
  printf '%b' "${rows_open}"
  [ "${SHOW_DELIVERED}" = "1" ] && printf '%b' "${rows_ok}"
} | column -t -s $'\t' | sed 's/^+++.*/------------------------------------------------------------------------------------/'
echo
echo "${dim}${n_ok} entregue(s) ocultas (SHOW_DELIVERED=1 lista); ${n_missing} worktree(s) sem diretório (git worktree prune).${reset}"

# ---- PRs abertos, do ponto de vista da fila ---------------------------------
echo
echo "${bold}PRs abertos — quem está esperando o quê${reset}"
echo
printf '%s' "${OPEN}" | jq -r '
  map(. + {
      fail: ([.statusCheckRollup[]? | select(.conclusion=="FAILURE")] | length),
      # check em andamento vem com conclusion "" (string vazia), não null.
      pend: ([.statusCheckRollup[]? | select((.conclusion // "")=="")] | length),
      total: ([.statusCheckRollup[]?] | length),
      queued: (.autoMergeRequest != null),
      bot: ((.author.login // "") | test("dependabot"))
    })
  | (map(select(.bot)) | length) as $bots
  | (map(select(.bot|not))
     | sort_by(
         if .isDraft then 6
         elif .mergeStateStatus=="DIRTY" then 1
         elif .fail>0 then 0
         elif .queued then 4
         elif .mergeStateStatus=="CLEAN" or .mergeStateStatus=="BEHIND" or .mergeStateStatus=="UNSTABLE" then 2
         elif .pend>0 or .total==0 then 3
         else 5 end)
     | .[]
     | (if .isDraft then "📝 DRAFT"
        elif .mergeStateStatus=="DIRTY" then "⚠️  CONFLITO"
        elif .fail>0 then "🔴 VERMELHO (\(.fail) check)"
        elif .queued then "🚦 NA FILA"
        elif .total==0 or .pend>0 then "◷  RODANDO"
        elif .mergeStateStatus=="CLEAN" or .mergeStateStatus=="BEHIND" or .mergeStateStatus=="UNSTABLE" then "🟢 VERDE FORA DA FILA → gh pr merge \(.number)"
        else "?  \(.mergeStateStatus)" end) as $tag
     | "\($tag)\t#\(.number)\t\(.updatedAt[:10])\t\(.headRefName)\t\(.title[:56])"
    ),
    "\($bots) PR(s) do Dependabot omitidos (freeze, issue #574)\t\t\t\t"
' | { printf 'STATUS\tPR\tATUALIZADO\tBRANCH\tTÍTULO\n'; cat; } | column -t -s $'\t'

echo
if [ "${n_red}" -eq 0 ]; then
  echo "${green}${bold}✓ Nada dormindo em worktree/branch local.${reset}"
else
  echo "${red}${bold}🔴 ${n_red} frente(s) dormindo em worktree/branch local — publique ou decida (e diga qual).${reset}"
fi
